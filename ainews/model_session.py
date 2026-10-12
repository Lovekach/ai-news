"""A finite AI-owned Ollama session; never control a shared model service."""
from __future__ import annotations

import ctypes
import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen


class WindowsJob:
    """Close the job to terminate only its own Ollama process tree, even on timeout."""
    def __init__(self):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", w.DWORD), ("min_working", ctypes.c_size_t),
                        ("max_working", ctypes.c_size_t), ("active", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Limits(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.SetInformationJobObject.restype = w.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


@contextmanager
def model_session(config: dict, root: Path):
    # A separate address keeps any shared/default 11434 service independent.
    if config["ollama_url"].rstrip("/") != "http://127.0.0.1:11435":
        raise ValueError("Daily AI editor requires its independent Ollama endpoint on 11435")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 11435)) == 0:
            raise RuntimeError("AI model port is occupied; existing processes were left untouched")
    executable = shutil.which("ollama.exe") or shutil.which("ollama")
    if not executable:
        raise RuntimeError("Installed Ollama executable was not found")
    environment = dict(os.environ, OLLAMA_HOST="127.0.0.1:11435", OLLAMA_KEEP_ALIVE="0")
    log = root / ".state" / "ollama-daily.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    job = WindowsJob() if os.name == "nt" else None
    process = None
    try:
        with log.open("ab") as stream:
            process = subprocess.Popen([executable, "serve"], env=environment, cwd=root,
                                       stdout=stream, stderr=stream,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if job:
                job.assign(process)
            startup_deadline = min(time.monotonic() + 20, config.get("_deadline", float("inf")))
            while time.monotonic() < startup_deadline:
                if process.poll() is not None:
                    raise RuntimeError("AI-owned Ollama server exited during startup")
                try:
                    with urlopen(config["ollama_url"] + "/api/tags", timeout=1):
                        break
                except OSError:
                    time.sleep(0.25)
            else:
                raise TimeoutError("AI-owned Ollama server did not start")
            yield
    finally:
        # No global taskkill, no stop of Ollama app, no shared-model unload API.
        if job:
            job.close()
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
