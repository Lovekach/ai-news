from __future__ import annotations

import sqlite3
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .feeds import Entry


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                name TEXT PRIMARY KEY, initialized INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS items (
                url TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                published TEXT NOT NULL,
                summary TEXT NOT NULL,
                state TEXT NOT NULL,
                article TEXT,
                draft TEXT,
                error TEXT,
                telegram_message_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                send_started_at TEXT,
                sent_at TEXT
            );
            CREATE INDEX IF NOT EXISTS items_state_idx ON items(state, created_at);
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                old_text TEXT NOT NULL,
                new_text TEXT NOT NULL,
                corrected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS poll_state (
                source TEXT PRIMARY KEY,
                next_due_at REAL NOT NULL DEFAULT 0,
                last_success_at REAL,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                etag TEXT,
                last_modified TEXT,
                last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS digests (
                slot TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                text TEXT NOT NULL,
                telegram_message_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sent_at TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS digest_items (
                slot TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                PRIMARY KEY (slot, url)
            );
            CREATE TABLE IF NOT EXISTS digest_schedule (
                slot TEXT PRIMARY KEY,
                delay_minutes INTEGER NOT NULL CHECK(delay_minutes BETWEEN 1 AND 4)
            );
            CREATE TABLE IF NOT EXISTS daily_story_drafts (
                fingerprint TEXT PRIMARY KEY, draft TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS telegram_channels (
                handle TEXT PRIMARY KEY,
                last_id INTEGER NOT NULL,
                channel_id INTEGER,
                access_hash INTEGER,
                last_checked_at TEXT,
                last_error TEXT
            );
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def telegram_channel(self, handle: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM telegram_channels WHERE handle=?", (handle,)).fetchone()

    def save_telegram_channel(self, handle: str, last_id: int, *, channel_id: int | None = None, access_hash: int | None = None, error: str | None = None) -> None:
        with self.db:
            self.db.execute("""
                INSERT INTO telegram_channels(handle,last_id,channel_id,access_hash,last_checked_at,last_error)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP,?)
                ON CONFLICT(handle) DO UPDATE SET
                    last_id=MAX(telegram_channels.last_id,excluded.last_id),
                    channel_id=COALESCE(excluded.channel_id,telegram_channels.channel_id),
                    access_hash=COALESCE(excluded.access_hash,telegram_channels.access_hash),
                    last_checked_at=excluded.last_checked_at,
                    last_error=excluded.last_error
            """, (handle, last_id, channel_id, access_hash, error))

    def record_telegram_failure(self, handle: str, error: str) -> None:
        previous = self.telegram_channel(handle)
        self.save_telegram_channel(handle, int(previous["last_id"]) if previous else 0,
                                   error=error[:300])

    def retire_missing_telegram(self, source: str, handle: str, visible_ids: set[int]) -> int:
        """Hold unpublished posts deleted within the current public-page window."""
        if len(visible_ids) < 2:
            return 0
        lower, upper = min(visible_ids), max(visible_ids)
        prefix = f"https://t.me/{handle}/"
        rows = self.db.execute(
            "SELECT url FROM items WHERE source=? AND state IN ('pending','ready','needs_review')",
            (source,),
        ).fetchall()
        missing = []
        for row in rows:
            url = row["url"]
            if not url.startswith(prefix):
                continue
            suffix = url[len(prefix):]
            if suffix.isdigit() and lower <= int(suffix) <= upper and int(suffix) not in visible_ids:
                missing.append(url)
        with self.db:
            for url in missing:
                self.db.execute(
                    "UPDATE items SET state='skipped',error='Source post removed before publication' "
                    "WHERE url=? AND state IN ('pending','ready','needs_review')",
                    (url,),
                )
        return len(missing)

    def refresh_telegram_post(self, url: str, entry: Entry | None) -> bool:
        """Recheck visible edits before publication; old approved drafts become invalid."""
        row = self.db.execute(
            "SELECT summary,state FROM items WHERE url=?", (url,)
        ).fetchone()
        if row is None or row["state"] not in ("pending", "ready", "needs_review"):
            return False
        if entry is None:
            with self.db:
                self.db.execute(
                    "UPDATE items SET state='skipped',error='Source post became promotional or empty' "
                    "WHERE url=? AND state IN ('pending','ready','needs_review')", (url,),
                )
            return True
        if row["summary"] == entry.summary:
            return False
        with self.db:
            self.db.execute(
                "UPDATE items SET title=?,summary=?,published=?,state='pending',"
                "article=NULL,draft=NULL,error=NULL WHERE url=? "
                "AND state IN ('pending','ready','needs_review')",
                (entry.title, entry.summary, entry.published, url),
            )
        return True

    def add_feed(self, source: str, entries: list[Entry], *, include_existing: bool = False) -> int:
        row = self.db.execute("SELECT initialized FROM sources WHERE name=?", (source,)).fetchone()
        initial = row is None or not row["initialized"]
        state = "pending" if (include_existing or not initial) else "baseline"
        added = 0
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO sources(name,initialized) VALUES (?,1)", (source,))
            for entry in entries:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO items(url,source,title,published,summary,state) VALUES (?,?,?,?,?,?)",
                    (entry.url, entry.source, entry.title, entry.published, entry.summary, state),
                )
                added += cursor.rowcount
        return added

    def next_pending(self) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM items WHERE state='pending' ORDER BY created_at DESC, url DESC LIMIT 1").fetchone()

    def set_state(self, url: str, state: str, *, article: str | None = None, draft: str | None = None, error: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "UPDATE items SET state=?, article=COALESCE(?,article), draft=COALESCE(?,draft), error=? WHERE url=?",
                (state, article, draft, error, url),
            )

    def mark_sent(self, url: str, message_id: int) -> None:
        with self.db:
            self.db.execute(
                "UPDATE items SET state='sent', telegram_message_id=?, sent_at=CURRENT_TIMESTAMP WHERE url=? AND state='sending'",
                (message_id, url),
            )

    def ready(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM items WHERE state='ready' ORDER BY created_at, url").fetchall()

    def ready_before(self, cutoff_utc: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM items WHERE state='ready' AND created_at < ? ORDER BY created_at DESC, url DESC",
            (cutoff_utc,),
        ).fetchall()

    def recent_sent_titles(self) -> list[str]:
        return [row[0] for row in self.db.execute(
            "SELECT title FROM items WHERE state IN ('sent','send_uncertain') "
            "AND COALESCE(sent_at,send_started_at) >= datetime('now','-7 days')"
        )]

    def recent_sent_drafts(self) -> list[str]:
        return [row[0] for row in self.db.execute(
            "SELECT draft FROM items WHERE state IN ('sent','send_uncertain') AND draft IS NOT NULL "
            "AND COALESCE(sent_at,send_started_at) >= datetime('now','-7 days')"
        )]

    def digest(self, slot: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM digests WHERE slot=?", (slot,)).fetchone()

    def digest_delay(self, slot: str) -> int:
        """Choose a stable 1–4 minute delay, different from the prior scheduled hour."""
        with self.db:
            existing = self.db.execute("SELECT delay_minutes FROM digest_schedule WHERE slot=?", (slot,)).fetchone()
            if existing:
                return int(existing[0])
            previous = self.db.execute(
                "SELECT delay_minutes FROM digest_schedule WHERE slot<? ORDER BY slot DESC LIMIT 1", (slot,)
            ).fetchone()
            choices = [minute for minute in range(1, 5) if not previous or minute != previous[0]]
            selected = secrets.choice(choices)
            self.db.execute(
                "INSERT OR IGNORE INTO digest_schedule(slot,delay_minutes) VALUES (?,?)", (slot, selected)
            )
            return int(self.db.execute(
                "SELECT delay_minutes FROM digest_schedule WHERE slot=?", (slot,)
            ).fetchone()[0])

    def digest_posts_today(self) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM digests WHERE state IN ('sending','sent','send_uncertain') "
            "AND date(created_at,'localtime')=date('now','localtime')"
        ).fetchone()[0]

    def reserve_digest(self, slot: str, text: str, urls: list[str], discarded: list[tuple[str, str]]) -> bool:
        if not urls:
            return False
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.digest(slot):
                return False
            self.db.execute("INSERT INTO digests(slot,state,text) VALUES (?, 'sending', ?)", (slot, text))
            for url in urls:
                cursor = self.db.execute(
                    "UPDATE items SET state='sending',send_started_at=CURRENT_TIMESTAMP WHERE url=? AND state='ready'",
                    (url,),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Digest item no longer ready: {url}")
                self.db.execute("INSERT INTO digest_items(slot,url) VALUES (?,?)", (slot, url))
            for url, reason in discarded:
                self.db.execute(
                    "UPDATE items SET state='skipped',error=? WHERE url=? AND state='ready'",
                    (reason, url),
                )
        return True

    def finish_digest(self, slot: str, *, message_id: int | None = None, error: str | None = None) -> None:
        state = "sent" if message_id is not None else "send_uncertain"
        with self.db:
            self.db.execute(
                "UPDATE digests SET state=?,telegram_message_id=?,sent_at=CASE WHEN ?='sent' "
                "THEN CURRENT_TIMESTAMP ELSE NULL END,error=? WHERE slot=? AND state='sending'",
                (state, message_id, state, error, slot),
            )
            self.db.execute(
                "UPDATE items SET state=?,telegram_message_id=?,sent_at=CASE WHEN ?='sent' "
                "THEN CURRENT_TIMESTAMP ELSE NULL END,error=? "
                "WHERE url IN (SELECT url FROM digest_items WHERE slot=?) AND state='sending'",
                (state, message_id, state, error, slot),
            )

    def record_digest_correction(self, slot: str, old_text: str, new_text: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO corrections(url,old_text,new_text) VALUES (?,?,?)",
                (f"digest:{slot}", old_text, new_text),
            )
            self.db.execute("UPDATE digests SET text=? WHERE slot=? AND state='sent'", (new_text, slot))

    def claim_ready(self, url: str) -> bool:
        with self.db:
            cursor = self.db.execute("UPDATE items SET state='sending', send_started_at=CURRENT_TIMESTAMP WHERE url=? AND state='ready'", (url,))
        return cursor.rowcount == 1

    def posts_today(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM items WHERE state IN ('sent','sending','send_uncertain') AND date(COALESCE(sent_at,send_started_at),'localtime')=date('now','localtime')").fetchone()[0]

    def posts_last_hour(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM items WHERE state IN ('sent','sending','send_uncertain') AND COALESCE(sent_at,send_started_at)>=datetime('now','-1 hour')").fetchone()[0]

    def promote_baseline(self, source: str | None = None) -> str | None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        candidates: list[tuple[datetime, str]] = []
        for row in self.db.execute("SELECT url,published FROM items WHERE state='baseline' AND (? IS NULL OR source=?)", (source, source)):
            try:
                when = parsedate_to_datetime(row["published"])
            except (TypeError, ValueError, IndexError):
                try:
                    when = datetime.fromisoformat(row["published"].replace("Z", "+00:00"))
                except ValueError:
                    continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            when = when.astimezone(timezone.utc)
            if cutoff <= when <= datetime.now(timezone.utc):
                candidates.append((when, row["url"]))
        if not candidates:
            return None
        _, url = max(candidates)
        with self.db:
            self.db.execute("UPDATE items SET state='pending' WHERE url=? AND state='baseline'", (url,))
        return url

    def recent_titles(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT title FROM items WHERE state IN ('ready','sent') AND created_at >= datetime('now','-14 days')")]

    def counts(self) -> list[tuple[str, int]]:
        return [(r[0], r[1]) for r in self.db.execute("SELECT state,COUNT(*) FROM items GROUP BY state ORDER BY state")]

    def review_items(self, limit: int = 5) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM items WHERE state IN ('needs_review','send_uncertain') ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def retry_review(self, url: str) -> bool:
        with self.db:
            cursor = self.db.execute(
                "UPDATE items SET state='pending', article=NULL, draft=NULL, error=NULL WHERE url=? AND state='needs_review'",
                (url,),
            )
        return cursor.rowcount == 1

    def sent_item(self, url: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM items WHERE url=? AND state='sent'", (url,)).fetchone()

    def record_correction(self, url: str, old_text: str, new_text: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO corrections(url,old_text,new_text) VALUES (?,?,?)", (url, old_text, new_text))
            self.db.execute("UPDATE items SET draft=? WHERE url=? AND state='sent'", (new_text, url))

    def poll_state(self, source: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM poll_state WHERE source=?", (source,)).fetchone()

    def source_due(self, source: str, *, now: float | None = None) -> bool:
        row = self.poll_state(source)
        return row is None or row["next_due_at"] <= (time.time() if now is None else now)

    def record_poll_success(
        self, source: str, interval_seconds: int, *, etag: str | None = None,
        last_modified: str | None = None, now: float | None = None,
    ) -> None:
        current = time.time() if now is None else now
        with self.db:
            self.db.execute("""
                INSERT INTO poll_state(source,next_due_at,last_success_at,consecutive_failures,etag,last_modified,last_error)
                VALUES (?,?,?,0,?,?,NULL)
                ON CONFLICT(source) DO UPDATE SET
                    next_due_at=excluded.next_due_at,
                    last_success_at=excluded.last_success_at,
                    consecutive_failures=0,
                    etag=COALESCE(excluded.etag,poll_state.etag),
                    last_modified=COALESCE(excluded.last_modified,poll_state.last_modified),
                    last_error=NULL
            """, (source, current + interval_seconds, current, etag, last_modified))

    def record_poll_failure(self, source: str, error: str, *, now: float | None = None) -> int:
        current = time.time() if now is None else now
        row = self.poll_state(source)
        failures = min((row["consecutive_failures"] if row else 0) + 1, 5)
        delay = min(60 * (2 ** (failures - 1)), 900)
        with self.db:
            self.db.execute("""
                INSERT INTO poll_state(source,next_due_at,consecutive_failures,last_error)
                VALUES (?,?,?,?)
                ON CONFLICT(source) DO UPDATE SET
                    next_due_at=excluded.next_due_at,
                    consecutive_failures=excluded.consecutive_failures,
                    last_error=excluded.last_error
            """, (source, current + delay, failures, error[:300]))
        return delay
