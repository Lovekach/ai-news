"""Collect permitted public channel posts from Telegram's t.me/s pages."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from .feeds import Entry, download
from .store import Store

AD = re.compile(r"(?i)(?:^|\s)#?(?:реклама|промокод\w*|партн[её]рский\s+материал|на\s+правах\s+рекламы|скидк\w*|акци[яи]\b|оставить\s+заявку|бесплатн\w*\s+консультаци\w*|erid\s*:)")
CALL_TO_ACTION = re.compile(
    r"(?i)\b(?:подписывайтесь|подпишитесь|подписывайся|подпишись|переходите|переходи|"
    r"регистрируйтесь|регистрируйся|записывайтесь|запишитесь|успейте|"
    r"забирайте|забирай|купите|покупайте|закажите|оплатите)\b"
)
LINK = re.compile(r"(?i)(?:https?://|t\.me/|(?<!\w)@[a-z][a-z0-9_]{3,})")
PROMOTIONAL_OPPORTUNITY = re.compile(
    r"(?i)\b(?:подборк\w*\s+активност\w*|получаем\s+фиксированн\w*\s+выплат\w*|"
    r"подключаем\s+соцсет\w*|регистрируемся\s+участник\w*|пода[её]м\s+заявку)\b"
)
EDITORIAL_PROMOTION = re.compile(
    r"(?i)(?:\b(?:курс|специализаци\w*|обучени\w*)\b.{0,900}\b(?:цен\w*|оплат\w*|запис\w*|тариф\w*)\b|"
    r"\b(?:аренд\w*|каталог|выделенн\w* сервер\w*)\b.{0,800}\b(?:оплат\w*|сервер\w*|конфигураци\w*)\b|"
    r"\b(?:подобрать\s+конфигураци\w*|разверните\s+приватн\w*\s+инстанс)\b)"
)
EVERGREEN_ROUNDUP = re.compile(r"(?i)^\s*\d{2,}\s+(?:ии[- ]?)?(?:инструмент\w*|сервис\w*|модел\w*|сайт\w*|бот\w*)\b")


def promotional_post(text: str) -> bool:
    return bool(AD.search(text) or CALL_TO_ACTION.search(text) or PROMOTIONAL_OPPORTUNITY.search(text)
                or EDITORIAL_PROMOTION.search(text) or EVERGREEN_ROUNDUP.search(text))


@dataclass(frozen=True)
class Post:
    handle: str
    id: int
    date: datetime
    text: str


class PageParser(HTMLParser):
    """Keep only a post's own text; Telegram also renders quoted replies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[dict[str, object]] = []
        self.post: dict[str, object] | None = None
        self.depth = 0
        self.text_depth: int | None = None
        self.parts: list[str] | None = None
        self.primary: list[str] = []
        self.fallback: list[str] = []

    def handle_starttag(self, tag: str, raw: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in raw}
        classes = set(attrs.get("class", "").split())
        if self.post is None and tag == "div" and "tgme_widget_message" in classes:
            data_post = attrs.get("data-post", "")
            if "/" not in data_post:
                return
            self.post = {"data_post": data_post, "date": ""}
            self.depth = 1
            self.text_depth = None
            self.parts = None
            self.primary = []
            self.fallback = []
            return
        if self.post is None:
            return
        if tag == "div":
            self.depth += 1
            if "tgme_widget_message_text" in classes and "js-message_reply_text" not in classes:
                self.text_depth = self.depth
                self.parts = self.primary if "js-message_text" in classes else self.fallback
        elif tag == "br" and self.text_depth is not None and self.parts is not None:
            self.parts.append(" ")
        elif tag == "a" and self.text_depth is not None and self.parts is not None:
            # Telegram often hides the primary URL behind words such as
            # "исследование"; keep it internally for source verification.
            href = attrs.get("href", "")
            if href.startswith("https://"):
                self.parts.append(" " + href + " ")
        elif tag == "time" and attrs.get("datetime"):
            self.post["date"] = attrs["datetime"]

    def handle_endtag(self, tag: str) -> None:
        if self.post is None or tag != "div":
            return
        if self.text_depth == self.depth:
            self.text_depth = None
            self.parts = None
        self.depth -= 1
        if self.depth == 0:
            self.post["text"] = " ".join("".join(self.primary or self.fallback).split())
            self.posts.append(self.post)
            self.post = None

    def handle_data(self, data: str) -> None:
        if self.post is not None and self.text_depth is not None and self.parts is not None:
            self.parts.append(data)


def parse_page(html: str, handle: str) -> list[Post]:
    parser = PageParser()
    parser.feed(html)
    posts: list[Post] = []
    for item in parser.posts:
        channel, _, number = str(item["data_post"]).rpartition("/")
        if channel.casefold() != handle.casefold() or not number.isdigit() or not item["date"]:
            continue
        try:
            date = datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        posts.append(Post(handle, int(number), date.replace(tzinfo=date.tzinfo or timezone.utc), str(item["text"])))
    return posts


def entry_from_post(source: str, post: Post) -> Entry | None:
    body = " ".join(post.text.split())
    words = re.findall(r"[a-zа-яё0-9]+", body, flags=re.I)
    if len(body) < 45 or len(words) < 6 or promotional_post(body):
        return None
    # Public posts often contain links to a channel or an affiliate destination.
    # Keep source URLs internally, but never feed a link-only teaser to the LLM.
    without_links = LINK.sub(" ", body)
    if len(re.findall(r"[a-zа-яё0-9]+", without_links, flags=re.I)) < 6:
        return None
    title = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0][:160]
    if len(title) < 20:
        title = body[:160]
    return Entry(source, title, f"https://t.me/{post.handle}/{post.id}", post.date.isoformat(), body[:12_000])


def scan(config: dict, store: Store) -> list[str]:
    sources = [source for source in config["sources"] if source.get("type") == "telegram"]
    if not sources:
        return ["Нет Telegram-каналов для проверки."]
    report: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(config.get("digest_lookback_hours", 6)))
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        futures = {source["handle"]: pool.submit(download, f"https://t.me/s/{source['handle']}", max_bytes=3_000_000) for source in sources}
        for source in sources:
            handle = source["handle"]
            try:
                html, final_url = futures[handle].result()
                if final_url.rstrip("/").casefold() != f"https://t.me/s/{handle}".casefold():
                    raise ValueError("Telegram page redirected")
                posts = parse_page(html, handle)
                if not posts:
                    raise ValueError("No public posts parsed")
                state = store.telegram_channel(handle)
                selected = [post for post in posts if (post.id > state["last_id"] if state else post.date >= cutoff)]
                entries = [entry for post in selected if (entry := entry_from_post(source["name"], post))]
                added = store.add_feed(source["name"], entries, include_existing=True) if entries else 0
                revised = sum(store.refresh_telegram_post(
                    f"https://t.me/{handle}/{post.id}", entry_from_post(source["name"], post)
                ) for post in posts)
                retired = store.retire_missing_telegram(source["name"], handle, {post.id for post in posts})
                store.save_telegram_channel(handle, max(post.id for post in posts))
                report.append(f"@{handle}: {added} новых постов" +
                              (f", {revised} изменено" if revised else "") +
                              (f", {retired} снято автором" if retired else ""))
            except Exception as exc:
                from .security import safe_error
                store.record_telegram_failure(handle, safe_error(exc))
                report.append(f"@{handle}: ошибка {type(exc).__name__}")
    return report
