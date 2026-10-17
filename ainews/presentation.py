"""Public Telegram text only. Never use this on evidence or stored sources."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser


class _VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
        self.anchor = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.anchor += 1
        if tag in {'script', 'style'}:
            self.hidden += 1
        if tag in {'br', 'p', 'div', 'li'} and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor = max(0, self.anchor-1)
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {'p', 'div', 'li'} and not self.hidden:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(_display_label(data) if self.anchor else data)


# Bare hosts and arbitrary shorteners count too. Display labels with a domain
# spelling are preserved with a word joiner to prevent Telegram auto-linking.
_HOST = r'(?:[^\W_](?:[\w-]*[^\W_])?\.)+(?:xn--[a-z0-9-]+|[^\W\d_]{2,63})'
_URL = re.compile(r'(?i)(?:\b(?:https?|ftp|tg|mailto)\s*:\s*(?://)?[^\s<>]*|\bwww\.[^\s<>]*|\b[\w.+-]+@' + _HOST + r'\b|'
                  + r'(?://)?\b' + _HOST + r'(?:[/?#][^\s<>]*|\b))')
_SOURCE_PREFIX = re.compile(
    r'(?im)^[ \t]*(?:[#*_`]+[ \t]*)?(?:источники?|ссылки?|sources?|links?)'
    r'(?:[ \t]*[*_`]*[ \t]*:[ \t]*[*_`]*[ \t]*|[ \t]*[*_`]*[ \t]*$)')


def _close(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    for index in range(start, len(text)):
        if index and text[index-1] == '\\':
            continue
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _display_label(label: str) -> str:
    # A domain-shaped product label is useful text, not the hidden destination.
    # Break Telegram auto-linking without changing its visible spelling.
    return _URL.sub(lambda match: match[0].replace('.', '\u2060.')
                    if not any(char in match[0] for char in ':/@?#')
                    and any(char.isupper() or char.isdigit() for char in match[0].split('.')[0])
                    else '', label)


def _markdown(text: str) -> str:
    definitions = set(re.findall(r'^\s*\[([^]\n]+)\]:\s*\S+.*$', text, re.M))
    text = re.sub(r'^\s*\[[^]\n]+\]:\s*\S+.*$', '', text, flags=re.M)
    result = []
    index = 0
    while index < len(text):
        start = index + 1 if text[index:index+2] == '![' else index
        if text[start:start+1] == '[':
            end = _close(text, start, '[', ']')
            if end >= 0:
                following = end + 1
                if text[following:following+1] == '(':
                    tail = _close(text, following, '(', ')')
                    if tail < 0:
                        # Broken markup must not leave a half URL behind.
                        tail = text.find('\n', following)
                        tail = len(text)-1 if tail < 0 else tail-1
                    result.append(_display_label(_markdown(text[start+1:end])))
                    index = tail+1
                    continue
                if text[following:following+1] == '[':
                    tail = _close(text, following, '[', ']')
                    if tail >= 0:
                        result.append(_display_label(text[start+1:end]))
                        index = tail+1
                        continue
                if text[start+1:end] in definitions:
                    result.append(_display_label(text[start+1:end]))
                    index = end+1
                    continue
        result.append(text[index])
        index += 1
    return ''.join(result)


def public_text(text: str) -> str:
    """Remove destinations, retaining visible link labels and paragraph gaps."""
    # Decode first so encoded tags/schemes cannot escape the same checks.
    text = html.unescape(text)
    text = _markdown(text)
    # Autolinks are not HTML tags with visible data.
    text = re.sub(r'<\s*(?:https?://|tg://)[^>]*>', '', text, flags=re.I)
    parser = _VisibleHTML()
    parser.feed(text)
    parser.close()
    text = ''.join(parser.parts)
    # Keep explicit company/product display names such as Z.ai. A word joiner
    # makes the displayed name non-clickable; never retain a URL's path/query.
    text = re.sub(r'(?<![\w/])' + _HOST + r'\b(?![\w./?#])', lambda m: m[0].replace('.', '\u2060.')
                  if any(c.isupper() for c in m[0]) else m[0], text, flags=re.I)
    def remove(match):
        value = match[0]
        suffix = ''
        while value and value[-1] in '.,;!?)':
            if value[-1] == ')' and value.count(')') <= value.count('('):
                break
            suffix = value[-1] + suffix
            value = value[:-1]
        return suffix
    text = _URL.sub(remove, text)
    text = re.sub(r'[ \t]+([,.;!?])', r'\1', text)
    text = re.sub(r'\(\s*\)|\[\s*\]|<\s*>', '', text)
    lines = []
    for line in text.splitlines():
        indent = '  ' if line.startswith('  ') else ''
        line = re.sub(r'[ \t]+', ' ', line).strip()
        line = _SOURCE_PREFIX.sub('', line)
        # A removed link is not an extra sentence or a punctuation paragraph.
        lines.append(indent + line if re.search(r'\w', line) else '')
    return re.sub(r'\n{5,}', '\n\n\n\n', '\n'.join(lines)).strip()


def assert_public_text(text: str, limit: int = 3900) -> None:
    """Last transport boundary: validate, never silently change a saved post."""
    if not text.strip():
        raise ValueError('Empty public Telegram text')
    if len(text.encode('utf-16-le')) // 2 > limit:
        raise ValueError('Public Telegram text exceeds UTF-16 limit')
    if (_URL.search(text) or re.search(r'(?i)href\s*=|\]\s*\(|(?:https?|tg)\s*:', text)
            or _SOURCE_PREFIX.search(text)):
        raise ValueError('Public Telegram text contains a link or source block')
    from .quality import integrity_issues
    for item in text.split('\n\n\n\n'):
        if item.startswith(('- ', '🧠 ')) and integrity_issues(item):
            raise ValueError('Public Telegram news is incomplete or has an uninformative headline')
