"""Bounded source documents, without model calls or publication side effects.

HTTP content and metadata are untrusted evidence, never instructions. A public
address or a valid TLS certificate does not establish editorial authority.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit


@dataclass(frozen=True)
class Response:
    url: str
    body: bytes
    content_type: str
    observed_at: str


def source_host(url, allowed_hosts=None):
    """Validate syntax even when a source URL will be rewritten to an API."""
    if any(ord(c) < 33 or c == '\\' for c in url):
        raise ValueError('Control characters or ambiguous source URL')
    part = urlsplit(url)
    if part.scheme != 'https' or part.username is not None or part.password is not None:
        raise ValueError('Source requires HTTPS without credentials')
    host = (part.hostname or '').encode('idna').decode('ascii').lower()
    if not host or host.endswith('.') or part.port not in (None, 443):
        raise ValueError('Source requires a canonical host and HTTPS port')
    if host == 'localhost' or host.endswith(('.local', '.localhost', '.internal')):
        raise ValueError('Internal source host is prohibited')
    if allowed_hosts is not None and host not in allowed_hosts:
        raise ValueError('Source host is not configured')
    return host


def public_addresses(url, allowed_hosts=None):
    """Validate the URL and every resolved address, before opening a socket."""
    host = source_host(url, allowed_hosts)
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    def public_unicast(value):
        address = ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast or '%' in value:
            return False
        if isinstance(address, ipaddress.IPv6Address):
            # Transition mechanisms can route an apparently global IPv6 address
            # to an embedded private IPv4 destination. Native IPv6 remains usable.
            return not (address.ipv4_mapped or address.sixtofour or address.teredo or
                        address in ipaddress.ip_network('64:ff9b::/96'))
        return True
    if not addresses or not all(public_unicast(a) for a in addresses):
        raise ValueError('Source resolves to a non-public address')
    return host, addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connect to an already validated IP; TLS still verifies the source host."""
    def __init__(self, host, addresses, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.addresses = addresses

    def connect(self):
        last = None
        for address in self.addresses:
            raw = None
            try:
                raw = socket.create_connection((address, 443), self.timeout)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError as exc:
                last = exc
                if raw is not None:
                    raw.close()
        raise OSError('No validated source address could be reached') from last


def fetch(url, *, allowed_hosts=None, max_bytes=2_000_000, timeout=20):
    """No proxy inheritance, cookies, auth, scripts, or unvalidated redirects."""
    current = url
    for _ in range(5):
        host, addresses = public_addresses(current, allowed_hosts)
        part = urlsplit(current)
        target = quote(part.path or '/', safe='/%:@!$&\'()*+,;=-._~')
        if part.query:
            target += '?' + quote(part.query, safe='/%?:@!$&\'()*+,;=-._~')
        connection = PinnedHTTPS(host, addresses, timeout)
        try:
            connection.request('GET', target, headers={
                'User-Agent': 'PersonalAINewsReader/0.1', 'Accept-Encoding': 'identity',
                'Accept': 'text/html, application/json, text/plain;q=0.9'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Redirect has no destination')
                current = urljoin(current, location)
                continue  # Validate and resolve the new destination before GET.
            if response.status != 200:
                raise ValueError(f'Source HTTP status {response.status}')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Unexpected source encoding')
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError('Source exceeds byte budget')
            return Response(current, body, response.getheader('Content-Type', ''),
                            datetime.now(timezone.utc).isoformat())
        finally:
            connection.close()
    raise ValueError('Source redirect budget exhausted')


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)


VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'wbr'}
EXCLUDED = {'script', 'style', 'nav', 'aside', 'footer', 'form', 'button', 'noscript'}
BOILERPLATE = {'related', 'related-posts', 'related-articles', 'recommendations',
               'newsletter', 'comments', 'comment-list', 'share', 'social-share',
               'breadcrumbs', 'breadcrumb', 'article-card', 'post-card'}


def excluded(node):
    tokens = set((node.attrs.get('class', '') + ' ' + node.attrs.get('id', '')).lower().split())
    return node.tag in EXCLUDED or bool(tokens & BOILERPLATE) or node.attrs.get('aria-hidden') == 'true'


def plain(node):
    if isinstance(node, str):
        return node
    if excluded(node):
        return ''
    return ' '.join(plain(child) for child in node.children)


def clean(value):
    return ' '.join(value.split())


def descendants(node, tag):
    for child in node.children:
        if isinstance(child, Node):
            if child.tag == tag:
                yield child
            yield from descendants(child, tag)


class DocumentHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > 100_000 or len(self.stack) > 160:
            raise ValueError('HTML structure exceeds budget')
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for n in range(len(self.stack)-1, 0, -1):
            if self.stack[n].tag == tag:
                del self.stack[n:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


@dataclass(frozen=True)
class Block:
    kind: str
    text: str


def blocks(node):
    if isinstance(node, str) or excluded(node):
        return []
    text = clean(plain(node))
    if node.tag == 'table':
        def cell(c):
            spans = ', '.join(f'{key}={c.attrs[key]}' for key in ('rowspan', 'colspan')
                              if c.attrs.get(key, '1') != '1')
            return clean(plain(c)) + (f' [{spans}]' if spans else '')
        rows = [' | '.join(cell(c) for c in row.children
                           if isinstance(c, Node) and c.tag in {'th', 'td'})
                for row in descendants(node, 'tr')]
        captions = [clean(plain(c)) for c in descendants(node, 'caption')]
        value = '\n'.join(captions + [row for row in rows if row.strip(' |')])
        return [Block('table', value)] if value else []
    if node.tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
        return [Block('heading', '#' * int(node.tag[1]) + ' ' + text)] if text else []
    if node.tag in {'p', 'li', 'pre', 'figcaption', 'blockquote'}:
        # Nested paragraphs are represented once, in their enclosing block.
        kind = 'caption' if node.tag == 'figcaption' else 'paragraph'
        return [Block(kind, ('- ' if node.tag == 'li' else '') + text)] if text else []
    result = []
    for child in node.children:
        result.extend(blocks(child))
    return result


def article_metadata(root, url):
    """Prefer metadata for this document, not a related article in an LD graph."""
    meta = {}
    head = next(descendants(root, 'head'), None)
    for node in descendants(head or root, 'meta'):
        key = node.attrs.get('property') or node.attrs.get('name') or node.attrs.get('itemprop')
        if key and node.attrs.get('content'):
            meta[key] = node.attrs['content']
    articles = []
    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            kinds = value.get('@type', [])
            if isinstance(kinds, str):
                kinds = [kinds]
            if isinstance(kinds, list) and any(isinstance(k, str) and k in {
                    'Article', 'NewsArticle', 'BlogPosting', 'TechArticle', 'ScholarlyArticle'} for k in kinds):
                identity = value.get('url') or value.get('mainEntityOfPage')
                if isinstance(identity, dict):
                    identity = identity.get('@id')
                if not identity or str(identity).rstrip('/') == url.rstrip('/'):
                    articles.append(value)
            if '@graph' in value:
                visit(value['@graph'])
    for node in descendants(root, 'script'):
        if node.attrs.get('type') == 'application/ld+json':
            try:
                visit(json.loads(''.join(c for c in node.children if isinstance(c, str))))
            except (ValueError, TypeError):
                pass
    article = articles[0] if len(articles) == 1 else {}
    author = article.get('author') or meta.get('author') or []
    if not isinstance(author, list):
        author = [author]
    authors = tuple(str(a.get('name', '')) if isinstance(a, dict) else str(a) for a in author)
    published = article.get('datePublished') or meta.get('article:published_time') or meta.get('datePublished')
    modified = article.get('dateModified') or meta.get('article:modified_time')
    title = article.get('headline') or meta.get('og:title') or ''
    if not title:
        heading = next(descendants(root, 'h1'), None)
        title = clean(plain(heading)) if heading else ''
    return (str(title), tuple(a for a in authors if a),
            published if isinstance(published, str) else None,
            modified if isinstance(modified, str) else None)


@dataclass(frozen=True)
class Document:
    url: str
    title: str
    authors: tuple[str, ...]
    published: str | None
    modified: str | None
    observed_at: str
    sha256: str
    blocks: tuple[Block, ...]
    kind: str = 'article'

    @property
    def full_text(self):
        return '\n\n'.join(b.text for b in self.blocks)

    def available_at(self, cutoff: datetime):
        """An old publication label cannot backdate a newly captured body.

        Historical versions require an actual capture observed by the deadline.
        This checks evidence availability, not the age or truth of its event.
        """
        observed = datetime.fromisoformat(self.observed_at.replace('Z', '+00:00'))
        if observed.tzinfo is None or cutoff.tzinfo is None:
            raise ValueError('Evidence availability requires aware timestamps')
        return observed <= cutoff

    def context(self, limit=7000):
        """Whole blocks only; a table travels with its adjacent notes and heading.

        This is an explicit bounded projection, not a promise of full coverage.
        The complete document remains available to the private audit.
        """
        preamble = []
        if self.title:
            preamble.append('Заголовок документа: ' + self.title)
        if self.authors:
            preamble.append('Авторство документа: ' + ', '.join(self.authors))
        # Retrieval time is deliberately not supplied as a publication/event date.
        if self.published:
            preamble.append('Опубликовано в источнике: ' + self.published)
        prefix = '\n'.join(preamble)
        budget = limit - len(prefix) - 2
        if budget <= 0:
            raise ValueError('Source metadata exceeds context budget')
        selected = set()
        groups = []
        for n, block in enumerate(self.blocks):
            group = {n}
            if block.kind == 'table':
                if n and self.blocks[n-1].kind in {'heading', 'caption'}:
                    group.add(n-1)
                if n+1 < len(self.blocks):
                    following = n + 1
                    while following < len(self.blocks) and self.blocks[following].kind in {'paragraph', 'caption'}:
                        group.add(following)
                        following += 1
            groups.append((0 if block.kind == 'table' else 1 if n < 2 else 2, n, group))
        for _, n, group in sorted(groups):
            candidate = selected | group
            size = sum(len(self.blocks[i].text) for i in candidate) + 2*max(0, len(candidate)-1)
            if size <= budget:
                selected = candidate
        body = '\n\n'.join(self.blocks[i].text for i in sorted(selected))
        if not body:
            raise ValueError('No complete source block fits context')
        return prefix + '\n\n' + body


def parse_html(response: Response):
    parser = DocumentHTML()
    parser.feed(response.body.decode('utf-8', errors='replace'))
    candidates = list(descendants(parser.root, 'article')) or list(descendants(parser.root, 'main'))
    node = max(candidates, key=lambda n: len(clean(plain(n))), default=parser.root)
    title, authors, published, modified = article_metadata(parser.root, response.url)
    extracted = tuple(blocks(node))
    if not extracted or sum(len(b.text) for b in extracted) < 80:
        raise ValueError('Insufficient substantive source content')
    return Document(response.url, title, authors, published, modified, response.observed_at,
                    hashlib.sha256(response.body).hexdigest(), extracted)


def read_document(url, allowed_hosts=None, *, downloader=fetch):
    source_host(url, allowed_hosts)
    part = urlsplit(url)
    if allowed_hosts is not None and part.hostname not in allowed_hosts:
        raise ValueError('Requested source host is not configured')
    if part.hostname in {'x.com', 'twitter.com', 't.me'}:
        raise ValueError('Social evidence requires its captured collector text')
    path = part.path.strip('/').split('/')
    if part.hostname == 'github.com' and len(path) >= 5 and path[2:4] == ['releases', 'tag']:
        api = f'https://api.github.com/repos/{quote(path[0], safe="")}/{quote(path[1], safe="")}/releases/tags/{quote(unquote("/".join(path[4:])), safe="")}'
        response = downloader(api, allowed_hosts=['api.github.com'])
        release = json.loads(response.body)
        if release.get('draft'):
            raise ValueError('A draft is not public release evidence')
        text = str(release.get('body') or '')
        if not text.strip():
            raise ValueError('Release has no notes')
        return Document(url, str(release.get('name') or release.get('tag_name') or ''),
                        (str(release.get('author', {}).get('login') or ''),),
                        release.get('published_at'), release.get('updated_at'), response.observed_at,
                        hashlib.sha256(response.body).hexdigest(),
                        tuple(Block('paragraph', b) for b in re.split(r'\n\s*\n', text) if b.strip()), 'release')
    if part.hostname == 'github.com' and len(path) == 2:
        owner, project = path
        api = f'https://api.github.com/repos/{quote(owner, safe="")}/{quote(project, safe="")}/readme'
        response = downloader(api, allowed_hosts=['api.github.com'])
        value = json.loads(response.body)
        if value.get('encoding') != 'base64':
            raise ValueError('Unsupported repository document encoding')
        text = base64.b64decode(value['content'], validate=False).decode('utf-8')
        # An owner is neither necessarily the author nor a model developer.
        text = 'Repository owner/project: ' + owner + '/' + project + '\n\n' + text
        return Document(url, owner + '/' + project, (), None, None, response.observed_at,
                        hashlib.sha256(response.body).hexdigest(),
                        tuple(Block('table' if ' | ' in b else 'paragraph', b)
                              for b in re.split(r'\n\s*\n', text) if b.strip()), 'repository')
    response = downloader(url, allowed_hosts=allowed_hosts)
    if not any(kind in response.content_type.lower() for kind in ('html', 'xhtml')):
        raise ValueError('Source format requires a dedicated parser; no binary-as-text fallback')
    return parse_html(response)
