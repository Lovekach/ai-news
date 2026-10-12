"""Public X RSS collection; no account secrets needed."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request
from xml.etree import ElementTree as ET

from .feeds import Entry, strip_html, USER_AGENT, source_open
from .security import safe_error

MIRRORS = ("https://twiiit.com/{handle}/rss",
           "https://rss.xcancel.com/{handle}/rss",
           "https://nitter.net/{handle}/rss")
STATUS = re.compile(r"/status/(\d+)")
HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = dict(attrs).get("href") or ""
            if url.startswith("https://") and url not in self.urls:
                self.urls.append(url)


def parse_x_rss(xml: str, source: dict) -> list[Entry]:
    root = ET.fromstring(xml.lstrip("\ufeff \t\r\n"))
    if root.tag != "rss":
        raise ValueError("X mirror returned a non-RSS page")
    entries = []
    handle = source["handle"]
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        if title.casefold().startswith(("rt by @", "retweeted by @", "r to @")):
            continue
        link = item.findtext("link") or item.findtext("guid") or ""
        match = STATUS.search(link)
        # A repost from another account must not become this author's claim.
        if not match or urlparse(link).path.split("/")[1].casefold() != handle.casefold():
            continue
        post_id = match.group(1)
        description = item.findtext("description") or ""
        text = strip_html(description) or strip_html(title)
        links = _Links()
        links.feed(description)
        # Preserve full article URLs hidden behind shortened labels in RSS.
        text += " " + " ".join(url for url in links.urls if url not in text)
        text = re.sub(r"(?:https?://)?pic\.twitter\.com/\S+", "", text).strip()
        if not text:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError, OverflowError):
            published = datetime.fromtimestamp(((int(post_id) >> 22) + 1288834974657) / 1000, timezone.utc)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        entries.append(Entry(source["name"], strip_html(title or text)[:220],
                             f"https://x.com/{handle}/status/{post_id}",
                             published.astimezone(timezone.utc).isoformat(), text))
    return entries


def read_x_source(source: dict):
    handle = source["handle"]
    if not HANDLE.fullmatch(handle):
        raise ValueError("Invalid X handle")
    errors = []
    for template in MIRRORS:
        url = template.format(handle=handle)
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT,
                                           "Accept": "application/rss+xml, application/xml, text/xml, */*"})
            # Mirror dispatchers may redirect to another public HTTPS mirror.
            # Validate each hop before connecting, sharing the feed guard.
            with source_open(request, None, timeout=8) as response:
                if urlparse(response.geturl()).scheme != "https":
                    raise ValueError("Non-HTTPS mirror redirect")
                payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError("X RSS feed is too large")
                xml = payload.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            entries = parse_x_rss(xml, source)
            if not entries:
                raise ValueError("RSS feed contained no usable own posts")
            return entries, None, None
        except Exception as exc:
            errors.append(f"{urlparse(url).hostname}: {safe_error(exc)}")
    raise ValueError("; ".join(errors))
