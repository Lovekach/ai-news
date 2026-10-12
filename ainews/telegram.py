from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .security import redact


def read_token() -> str:
    script = Path(__file__).resolve().parent.parent / "scripts" / "read_token.ps1"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode or not token:
        raise RuntimeError("Токен не найден. Запустите scripts/store_token.ps1 от своего пользователя Windows.")
    return token


def call(token: str, method: str, data: dict[str, Any] | None = None) -> Any:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(data or {}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            description = str(json.loads(exc.read()).get("description", ""))
        except (ValueError, OSError):
            description = ""
        finally:
            exc.close()
        # Only the API description is logged; request URLs contain the token.
        raise RuntimeError(redact(f"Telegram HTTP {exc.code}: {description}".rstrip(": "), secrets=(token,))) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Telegram network error: {type(exc).__name__}") from None
    except Exception as exc:
        # Unexpected transport/parsing exceptions may also include the bot URL.
        raise RuntimeError(f"Telegram transport error: {type(exc).__name__}") from None
    if not result.get("ok"):
        raise RuntimeError(redact(f"Telegram API error: {result.get('description', 'unknown error')}", secrets=(token,)))
    return result["result"]


def find_channel(token: str) -> list[tuple[int, str]]:
    updates = call(token, "getUpdates", {"timeout": 0, "allowed_updates": ["channel_post"]})
    result: dict[int, str] = {}
    for update in updates:
        post = update.get("channel_post") or update.get("edited_channel_post")
        chat = post.get("chat", {}) if isinstance(post, dict) else {}
        if chat.get("type") == "channel" and isinstance(chat.get("id"), int):
            result[chat["id"]] = str(chat.get("title", ""))
    return sorted(result.items())


def check_channel_access(token: str, channel_id: int, *, expected_username: str = "ai_news_main_bot") -> str:
    bot = call(token, "getMe")
    if bot.get("username", "").casefold() != expected_username.lstrip("@").casefold():
        raise RuntimeError("Сохраненный токен принадлежит другому боту.")
    chat = call(token, "getChat", {"chat_id": channel_id})
    if chat.get("type") != "channel":
        raise RuntimeError("Указанный ID не принадлежит каналу.")
    member = call(token, "getChatMember", {"chat_id": channel_id, "user_id": bot["id"]})
    if member.get("status") != "administrator" or member.get("can_post_messages") is not True:
        raise RuntimeError("Бот не имеет права публиковать сообщения в канале.")
    return str(chat.get("title", ""))


def send_message(token: str, channel_id: int, text: str) -> int:
    result = call(token, "sendMessage", {
        "chat_id": channel_id,
        "text": text,
        "disable_web_page_preview": True,
    })
    return int(result["message_id"])


def edit_message(token: str, channel_id: int, message_id: int, text: str) -> None:
    call(token, "editMessageText", {
        "chat_id": channel_id,
        "message_id": message_id,
        "text": text,
        "disable_web_page_preview": True,
    })
