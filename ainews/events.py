"""Evidence-bound event identity; source accounts are not product owners."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlparse

from .quality import event_signature


def normalized(value: str) -> str:
    return re.sub(r'[^a-zа-яё0-9.]', '', value.casefold())


def reference_ids(text: str) -> frozenset[str]:
    references = set()
    for url in re.findall(r'https?://[^\s<>]+', text):
        parsed = urlparse(url.rstrip('.,)'))
        post = re.fullmatch(r'/([\w]+)/status/(\d+)(?:/.*)?', parsed.path)
        if post:
            references.add('post:' + post[1].casefold() + '/' + post[2])
        elif (parsed.hostname and parsed.path.strip('/')
              and parsed.hostname not in {'t.me', 'x.com', 'twitter.com'}
              and not (parsed.hostname == 'github.com' and len(parsed.path.strip('/').split('/')) == 2)):
            references.add(parsed.hostname.casefold() + parsed.path.rstrip('/'))
    return frozenset(references)


@dataclass(frozen=True)
class Event:
    company: str
    product: str
    kind: str
    platform: str
    day: str
    explicit_day: str
    references: frozenset[str]


def identity(row, *, event_date: str = '') -> Event | None:
    original = row['title'] + '\n' + (row['article'] or row['summary'])
    headline = (row['draft'] or '').split('\n\n')[0].removeprefix('🧠 ').removeprefix('- ')
    signature = event_signature(headline, row['summary']) or event_signature(row['title'], row['summary'])
    # Repository identity is explicit primary provenance, including link-preview
    # text in social posts. A quoted announcement and its author share this ID.
    repo_pairs = re.findall(r'https?://github\.com/([\w-]+)/([\w.-]+)', original)
    repo_pairs += re.findall(r'(?<![\w/.:])([A-Za-z][\w-]*)/([A-Za-z][\w.-]*)', original)
    repositories = [(owner.casefold(), repo.rstrip('.').casefold()) for owner, repo in repo_pairs
                    if re.search(r'(?<!\w)' + re.escape(repo.rstrip('.')) + r'(?!\w)', headline, re.I)]
    if repositories:
        owner, repo = max(repositories, key=lambda pair: len(pair[1]))
        company, product, kind = owner, 'repo:' + owner + '/' + repo, 'announcement'
        tag = re.search(r'/releases/tag/([^\s/?#]+)', row['url'])
        if tag:
            product += '@' + tag[1].casefold()
        if re.search(r'\bbenchmark\b|бенчмарк|\bтест\w*|рейтинг|\branking\b', row['title'], re.I):
            kind = 'benchmark'
    elif signature:
        company, product, kind, _ = signature
        source_signature = event_signature(row['title'], row['summary'])
        if source_signature:
            kind = source_signature[2]
        # Preserve explicit variants/date revisions after a recognized version.
        expression = r'[ -]+'.join(re.escape(part) for part in product.split())
        subject_text = row['title'] + '\n' + headline
        match = re.search(expression, subject_text, re.I)
        if match:
            suffix = re.match(r'(?:[- ](?:[A-Z][a-zA-Z]*|\d{6,8})){0,3}', subject_text[match.end():])
            if suffix:
                product += suffix[0].casefold()
    else:
        return None  # Unknown subject needs stronger source/duplicate evidence.

    top = (row['article'] or row['summary']).split('[Начало цитируемого поста]')[0]
    availability = r'available|\bfree\b|\bsupport\b|\b(?:is|now) on\b|\blive\b|доступ|бесплат|поддержк|интеграц'
    platform = ''
    available = bool(re.search(availability, headline + ' ' + row['title'] + ' ' + top[:350], re.I))
    if available or kind in {'benchmark', 'ranking'}:
        for title in (headline, row['title'], top[:350]):
            for match in re.finditer(r'(?:\bon|\bin|\bvia|\bthrough|\bна|\bв|\bчерез)\s+@?'
                                     r'((?:[A-Z][A-Za-z0-9]*|[a-z]+[A-Z][A-Za-z0-9]*)(?:[ -][A-Z][a-zA-Z]+)?)', title):
                name = match[1]
                if normalized(name) in {'the', 'us', 'api'} or normalized(name) in normalized(product):
                    continue
                if normalized(name) not in normalized(original):
                    continue
                platform = normalized(name)
                # Cloud/local are different deployments; never infer local use
                # from an installed client that calls a cloud model.
                if re.search(re.escape(name.split()[0]) + r"(?:'s)?\s+Cloud\b", original, re.I):
                    platform = normalized(name.split()[0]) + ':cloud'
                break
            if platform:
                break
        if platform and available and kind not in {'benchmark', 'ranking'}:
            kind = 'availability'
    # Explicit updates/benchmarks remain separate from release announcements.
    if re.search(r'price (?:cut|change|increase)|цен\w*\s+(?:снижен|измен|вырос)', headline, re.I):
        kind = 'pricing'
    elif not platform and re.search(r'\bupdate\b|обновлен|обновлён|исправлен', row['title'], re.I):
        kind = 'update'
    try:
        try:
            date = parsedate_to_datetime(row['published'])
        except (TypeError, ValueError, IndexError):
            date = datetime.fromisoformat(row['published'].replace('Z', '+00:00'))
        day = (date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date).astimezone(
            timezone(timedelta(hours=3))).date().isoformat()
    except (TypeError, ValueError):
        day = ''
    return Event(company, normalized(product), kind, platform, day, event_date or '',
                 reference_ids(original + '\n' + row['url']))


def same_event(left: Event | None, right: Event | None) -> bool:
    if left is None or right is None:
        return False
    if (left.company, left.product, left.kind, left.platform) != (right.company, right.product, right.kind, right.platform):
        return False
    if left.explicit_day and right.explicit_day and left.explicit_day != right.explicit_day:
        return False
    linked = bool(left.references & right.references)
    if left.day and right.day:
        distance = abs((datetime.fromisoformat(left.day)-datetime.fromisoformat(right.day)).days)
        return distance == 0 or (distance <= 1 and linked)
    return linked
