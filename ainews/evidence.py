"""Experimental source-first evidence packets. No publication or production state."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from .feeds import PublicationDateExtractor, download
from .quality import sentences


class ArticleText(HTMLParser):
    """Preserve headings and table columns instead of flattening away the table."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.current = []
        self.blocks = []
        self.row = None
        self.table = None
        self.active = False
        self.main = 0
        self.article = 0
        self.main_blocks = []
        self.article_blocks = []
        self.articles = []
        self.current_article = None

    def append(self, value):
        self.blocks.append(value)
        if self.main:
            self.main_blocks.append(value)
        if self.article:
            self.article_blocks.append(value)
            if self.current_article is not None:
                self.current_article.append(value)

    @property
    def text(self):
        article = max(self.articles, key=lambda blocks: sum(map(len, blocks)), default=[])
        blocks = (article if sum(map(len, article)) >= 300 else
                  self.main_blocks if sum(map(len, self.main_blocks)) >= 300 else self.blocks)
        return '\n\n'.join(blocks)

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.main += 1
        if tag == 'article':
            if not self.article:
                self.current_article = []
            self.article += 1
        if tag in {'script', 'style', 'nav', 'footer', 'header', 'aside'}:
            self.ignored += 1
        if self.ignored:
            return
        if tag == 'table':
            self.table = []
        if tag == 'tr':
            self.row = []
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'td', 'th'}:
            self.active = True
            self.current = []
        if tag == 'br' and self.active:
            self.current.append(' ')

    def handle_data(self, data):
        if self.active and not self.ignored:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'nav', 'footer', 'header', 'aside'}:
            self.ignored = max(0, self.ignored - 1)
            return
        if self.ignored:
            return
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'td', 'th'} and self.active:
            value = ' '.join(''.join(self.current).split())
            if value:
                if tag in {'td', 'th'} and self.row is not None:
                    self.row.append(value)
                else:
                    self.append(value)
            self.current = []
            self.active = False
        if tag == 'tr' and self.row is not None:
            if self.row:
                if self.table is not None:
                    self.table.append(' | '.join(self.row))
                else:
                    self.append(' | '.join(self.row))
            self.row = None
        if tag == 'table' and self.table is not None:
            self.append('\n'.join(self.table))
            self.table = None
        if tag == 'article':
            self.article = max(0, self.article - 1)
            if not self.article and self.current_article is not None:
                self.articles.append(self.current_article)
                self.current_article = None
        if tag == 'main':
            self.main = max(0, self.main - 1)


def primary_document(url: str) -> tuple[str, str | None]:
    """Fetch an exact release or a bounded primary page through existing guards."""
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')
    if parsed.hostname == 'github.com' and len(parts) >= 5 and parts[2:4] == ['releases', 'tag']:
        from urllib.parse import quote
        api = f'https://api.github.com/repos/{parts[0]}/{parts[1]}/releases/tags/{quote("/".join(parts[4:]), safe="")}'
        raw, _ = download(api, allowed_hosts=['api.github.com'])
        release = json.loads(raw)
        if release.get('draft'):
            raise ValueError('Draft release is not public evidence')
        return ('Release published_at: ' + str(release.get('published_at') or 'unknown') + '\n' +
                str(release.get('name', '')) + '\n' + str(release.get('body', ''))), release.get('published_at')
    if parsed.hostname == 'github.com' and len(parts) == 2:
        import base64
        raw, _ = download(f'https://api.github.com/repos/{parts[0]}/{parts[1]}/readme', allowed_hosts=['api.github.com'])
        readme = json.loads(raw)
        if readme.get('encoding') != 'base64':
            raise ValueError('Unsupported repository README encoding')
        return ('Repository owner: ' + parts[0] + '\n' +
                base64.b64decode(readme['content']).decode('utf-8')), None
    raw, _ = download(url, allowed_hosts=[parsed.hostname])
    text = ArticleText()
    text.feed(raw)
    date = PublicationDateExtractor()
    date.feed(raw)
    return text.text, date.dates[0] if date.dates else None


def linked_primary_urls(text: str, limit=2) -> list[str]:
    """Only bounded HTTPS destinations on the existing trusted primary policy."""
    from .pipeline import PRIMARY_HOSTS
    allowed = set(PRIMARY_HOSTS) | {'vllm.ai', 'docs.vllm.ai', 'ollama.com', 'docs.ollama.com'}
    found = []
    for value in re.findall(r'https://[^\s<>"\]]+', text):
        value = value.rstrip('.,);')
        parsed = urlparse(value)
        host = parsed.hostname or ''
        if any(host == domain or host.endswith('.' + domain) for domain in allowed) and parsed.path.strip('/') and value not in found:
            if host == 'arxiv.org' and parsed.path.startswith('/pdf/'):
                value = 'https://arxiv.org/abs/' + parsed.path.removeprefix('/pdf/')
            found.append(value)
            if len(found) == limit:
                break
    return found


def retrieve(row, source: dict, loader=primary_document, *, deadline=float('inf')) -> tuple[list[Document], list[dict]]:
    """Prefer captured primary articles, retaining the post's distinct timeline.

    A missing optional article does not invalidate a short official integration.
    A secondary title is never promoted to evidence. The caller owns caching.
    """
    documents, failures = [], []
    social = source.get('type') in {'x', 'telegram'}
    official = bool(source.get('primary_account')) if social else True
    links = linked_primary_urls(row['summary']) if social else [row['url']]
    for url in links:
        if time.monotonic() + 20 >= deadline:
            failures.append({'url': url, 'error_type': 'EditorialBudgetExhausted'})
            break
        try:
            text, published = loader(url)
            if text.strip():
                parsed = urlparse(url)
                parts = parsed.path.strip('/').split('/')
                owner, project = (parts[0], parts[1]) if parsed.hostname == 'github.com' and len(parts) >= 2 else ('', '')
                documents.append(Document(url, text, published, 'primary_article' if not official or not social
                                          else 'linked_background', owner, project))
        except Exception as exc:
            failures.append({'url': url, 'error_type': type(exc).__name__})
    if official and social:
        documents.append(Document(row['url'], row['summary'], row['published'], 'official_post', source.get('handle', '')))
    elif not official and not documents and source.get('type') == 'x':
        documents.append(Document(row['url'], row['summary'], row['published'], 'commentary', source.get('handle', '')))
    return documents, failures


@dataclass(frozen=True)
class Document:
    url: str
    text: str
    published: str | None = None
    role: str = 'primary'
    publisher: str = ''
    project: str = ''


@dataclass(frozen=True)
class Span:
    id: str
    document: int
    text: str


@dataclass(frozen=True)
class Packet:
    documents: tuple[Document, ...]
    spans: tuple[Span, ...]
    edition_date: str
    official: bool
    title: str = ''

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def context(self, spans=None):
        chosen = self.spans if spans is None else spans
        return {'documents': [{'id': i, 'url': d.url, 'published': d.published, 'role': d.role}
                              | {'publisher': d.publisher, 'project': d.project} for i, d in enumerate(self.documents)],
                'spans': [asdict(s) for s in chosen], 'edition_date': self.edition_date,
                'official': self.official, 'signal_title': self.title}


def packet(documents: list[Document], *, edition_date: str, official: bool, title='') -> Packet:
    seen, distinct, spans = set(), [], []
    # Fetch articles first, but establish the triggering integration/update from
    # its own official post before reading background about an older model.
    for document in sorted(documents, key=lambda d: d.role != 'official_post'):
        key = (document.url, document.text)
        if key in seen or not document.text.strip():
            continue
        seen.add(key)
        index = len(distinct)
        distinct.append(document)
        for block in re.split(r'\n\s*\n', document.text):
            # Keep table headers/rows together when possible. Long prose is split
            # at sentence boundaries; no source slice is silently discarded.
            chunks = sentences(block) if len(block) > 1400 and ' | ' not in block else [block]
            for value in chunks:
                value = ' '.join(value.split())
                if value:
                    spans.append(Span(f's{len(spans)}', index, value))
    if not spans:
        raise ValueError('No captured source evidence')
    return Packet(tuple(distinct), tuple(spans), edition_date, official, title)


def chunks(value: Packet, limit: int = 6000) -> list[tuple[Span, ...]]:
    """Read every span once; a large indivisible table remains intact or holds."""
    result, current, size = [], [], 0
    for span in value.spans:
        if len(span.text) > limit:
            raise ValueError('Source block exceeds bounded extraction context')
        if current and size + len(span.text) > limit:
            result.append(tuple(current))
            current, size = [], 0
        current.append(span)
        size += len(span.text)
    if current:
        result.append(tuple(current))
    return result
