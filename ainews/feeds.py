from __future__ import annotations

import html
import ipaddress
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

USER_AGENT = "PersonalAINewsReader/0.1 (+local Telegram digest)"
ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass(frozen=True)
class Entry:
    source: str
    title: str
    url: str
    published: str
    summary: str
    updated: str | None = None
    date_kind: str = "published"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.blocks: list[str] = []
        self.main_blocks: list[str] = []
        self.article_blocks: list[str] = []
        self.current: list[str] = []
        self.in_block = 0
        self.in_main = 0
        self.in_article = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main":
            self.in_main += 1
        if tag == "article":
            self.in_article += 1
        if tag in {"script", "style", "nav", "footer", "header", "aside"}:
            self.skip += 1
        if tag in {"h1", "h2", "h3", "p", "li"} and not self.skip:
            self.in_block += 1
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "p", "li"} and self.in_block:
            value = " ".join(" ".join(self.current).split())
            if len(value) >= 25:
                self.blocks.append(value)
                if self.in_main:
                    self.main_blocks.append(value)
                if self.in_article:
                    self.article_blocks.append(value)
            self.current = []
            self.in_block -= 1
        if tag in {"script", "style", "nav", "footer", "header", "aside"} and self.skip:
            self.skip -= 1
        if tag == "article" and self.in_article:
            self.in_article -= 1
        if tag == "main" and self.in_main:
            self.in_main -= 1

    def handle_data(self, data: str) -> None:
        if self.in_block and not self.skip:
            self.current.append(data)


class PublicationDateExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.dates: list[str] = []
        self.in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and (values.get("property") in {"article:published_time", "og:published_time"}
                              or values.get("name") in {"datePublished", "pubdate", "parsely-pub-date"}
                              or values.get("itemprop") == "datePublished"):
            if values.get("content"):
                self.dates.append(values["content"])
        if tag == "time" and values.get("itemprop") == "datePublished" and values.get("datetime"):
            self.dates.append(values["datetime"])
        self.in_json_ld = tag == "script" and values.get("type") == "application/ld+json"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_json_ld = False

    def handle_data(self, data: str) -> None:
        if not self.in_json_ld:
            return
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            return
        def collect(value: object) -> None:
            if isinstance(value, dict):
                kinds = value.get("@type", [])
                if isinstance(kinds, str):
                    kinds = [kinds]
                if (any(kind in {"Article", "NewsArticle", "BlogPosting", "ScholarlyArticle", "TechArticle"}
                        for kind in kinds) and isinstance(value.get("datePublished"), str)):
                    self.dates.append(value["datePublished"])
                if "@graph" in value:
                    collect(value["@graph"])
            elif isinstance(value, list):
                for nested in value:
                    collect(nested)
        collect(payload)


def strip_html(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    result = " ".join(parser.article_blocks)
    if len(result) < 300:
        result = " ".join(parser.main_blocks)
    if len(result) < 300:
        result = " ".join(parser.blocks)
    if result:
        return result
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def validate_source_url(url: str, allowed_hosts: list[str] | None) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS sources are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials in source URLs are not allowed")
    host = (parsed.hostname or "").lower()
    if not host or host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError("Public source hostname is required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Non-public source address is not allowed")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise ValueError("Source host is not allowed")


class SourceRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate redirect destinations before any request to the new host."""
    def __init__(self, allowed_hosts: list[str] | None):
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def source_open(request, allowed_hosts: list[str] | None, *, timeout: int = 20):
    validate_source_url(request.full_url, allowed_hosts)
    return urllib.request.build_opener(SourceRedirectHandler(allowed_hosts)).open(request, timeout=timeout)


def download(url: str, *, max_bytes: int = 2_000_000, allowed_hosts: list[str] | None = None) -> tuple[str, str]:
    allowed_hosts = allowed_hosts if allowed_hosts is not None else [(urlparse(url).hostname or "").lower()]
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with source_open(request, allowed_hosts) as response:
        final_url = response.geturl()
        if urlparse(final_url).scheme != "https":
            raise ValueError("Redirected to a non-HTTPS URL")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Source is too large")
        charset = response.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace"), final_url


def download_feed(
    url: str, *, etag: str | None = None, last_modified: str | None = None,
    max_bytes: int = 2_000_000, allowed_hosts: list[str] | None = None,
) -> tuple[str | None, str, str | None, str | None]:
    allowed_hosts = allowed_hosts if allowed_hosts is not None else [(urlparse(url).hostname or "").lower()]
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    request = urllib.request.Request(url, headers=headers)
    try:
        response = source_open(request, allowed_hosts)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, url, etag, last_modified
        raise
    with response:
        final_url = response.geturl()
        if urlparse(final_url).scheme != "https":
            raise ValueError("Redirected to a non-HTTPS URL")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Source is too large")
        charset = response.headers.get_content_charset() or "utf-8"
        return (
            data.decode(charset, errors="replace"), final_url,
            response.headers.get("ETag"), response.headers.get("Last-Modified"),
        )


def parse_feed(xml: str, source: str) -> list[Entry]:
    root = ET.fromstring(xml)
    entries: list[Entry] = []
    if root.tag == "rss" or root.tag.endswith("}RDF"):
        nodes = root.findall(".//item")
        for node in nodes:
            title = (node.findtext("title") or "").strip()
            url = (node.findtext("link") or node.findtext("guid") or "").strip()
            published = (node.findtext("pubDate") or "").strip()
            summary = strip_html(node.findtext("description") or "")
            if title and url:
                entries.append(Entry(source, title, url, published, summary))
    elif root.tag == f"{ATOM}feed":
        for node in root.findall(f"{ATOM}entry"):
            title = (node.findtext(f"{ATOM}title") or "").strip()
            url = ""
            for link in node.findall(f"{ATOM}link"):
                if link.get("rel", "alternate") == "alternate":
                    url = (link.get("href") or "").strip()
                    break
            published = (node.findtext(f"{ATOM}published") or node.findtext(f"{ATOM}updated") or "").strip()
            summary = strip_html(node.findtext(f"{ATOM}summary") or node.findtext(f"{ATOM}content") or "")
            if title and url:
                entries.append(Entry(source, title, url, published, summary,
                                     (node.findtext(f"{ATOM}updated") or "").strip() or None,
                                     "published" if node.findtext(f"{ATOM}published") else "updated"))
    elif root.tag == f"{SITEMAP}urlset":
        for node in root.findall(f"{SITEMAP}url"):
            url = (node.findtext(f"{SITEMAP}loc") or "").strip()
            published = (node.findtext(f"{SITEMAP}lastmod") or "").strip()
            title = unquote(urlparse(url).path.rstrip("/").split("/")[-1]).replace("-", " ").strip()
            if title and url:
                entries.append(Entry(source, title, url, published, "", published, "updated"))
    else:
        raise ValueError("Unsupported feed format")
    return entries


def article_text(url: str, allowed_hosts: list[str]) -> str:
    return article_details(url, allowed_hosts)[0]


def article_details(url: str, allowed_hosts: list[str]) -> tuple[str, str | None]:
    host = (urlparse(url).hostname or "").lower()
    if host not in allowed_hosts:
        raise ValueError(f"Article host is not allowed: {host}")
    page, final_url = download(url, allowed_hosts=allowed_hosts)
    final_host = (urlparse(final_url).hostname or "").lower()
    if final_host not in allowed_hosts:
        raise ValueError(f"Article redirect host is not allowed: {final_host}")
    text = strip_html(page)
    if len(text) < 300:
        raise ValueError("Article text is too short")
    parser = PublicationDateExtractor()
    parser.feed(page)
    return text[:12_000], parser.dates[0] if parser.dates else None
