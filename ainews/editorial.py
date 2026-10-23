"""Cheap, auditable editorial ordering; never a substitute for verification."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from .quality import event_signature


def value(row, key):
    return row[key] if key in row.keys() and row[key] else ''


def event_key(row):
    """Conservative identity: full version, event kind and integration target.

    Shared company names alone are insufficient. Exact release URLs identify
    patch versions even when the feed headline contains only a tag.
    """
    url = urlparse(value(row, 'url'))
    if url.hostname == 'github.com' and '/releases/tag/' in url.path:
        owner, repo, _, _, tag = url.path.strip('/').split('/', 4)
        return ('release', owner.casefold(), repo.casefold(), unquote(tag))
    title = row['title']
    signature = event_signature(title, row['summary'])
    # Keep the ENTIRE versioned identifier, including date/size/flavour suffixes.
    # Do not infer the subject from competitors later in the body.
    match_product = re.search(r'\b[A-Za-z][A-Za-z0-9]*[ -]V?\d+(?:\.\d+)+'
                        r'(?:-[A-Za-z0-9]+)*(?: (?:Flash|Pro|Max|Mini|Ultra|\d{4,}|\d+B)\b)*', title, re.I)
    if match_product:
        raw = match_product.group()
        entity = re.sub(r'[\s-]+', '', raw).casefold()
        if signature:
            signature = (signature[0], entity, signature[2], signature[3])
        else:
            signature = (entity, entity, 'announcement', '')
    if signature is None:
        return None
    company, product, kind, target = signature
    # An explicit release remains a release when its headline mentions cost.
    # A pricing-only notice without a release assertion remains separate.
    opening = title
    article = value(row, 'article')[:300]
    if match_product and entity in re.sub(r'[\s-]+', '', article).casefold():
        opening += ' ' + article
    if not target and kind not in {'support', 'ranking', 'benchmark'} and re.search(
            r'\bis here\b|\bnew model\b|\bmodel release\b|новая модель|вышла модель', opening, re.I):
        kind = 'announcement'
        target = ''
    return company, product, kind, target


def decision(row, source=None):
    """Separate event eligibility, available evidence and editorial importance.

    These signals schedule work only. Unknown/brief evidence is not a refusal;
    the existing retrieval, freshness and writer/verifier still decide readiness.
    No company ranking or information from future articles is used.
    """
    source = source or {}
    title = row['title']
    summary = row['summary']
    key = event_key(row)
    host = (urlparse(value(row, 'url')).hostname or '').casefold()
    official = bool(source.get('primary_account')) or host == 'github.com' and '/releases/tag/' in row['url']
    recap = bool(re.search(r'\bthis week\b|\bweekly (?:roundup|recap)\b|итоги недели|'
                           r'дайджест\s+(?:за\s+)?недел\w*|недельн\w+\s+дайджест', title, re.I))
    if re.search(r'today.{0,40}(?:launch|release|is out|updat)|'
                 r'сегодня.{0,40}(?:выпуст|запуст|анонс|обнов)', title + ' ' + summary, re.I):
        recap = False  # The claimed current development still needs normal verification.
    integration = bool(re.search(r'\bintegrat\w*|\bsupport\w*|\bis (?:now )?on\b|поддержк|интеграц', title, re.I))
    release = bool(key and key[0] == 'release') or bool(re.search(
        r'\bis here\b|\bis out\b|\bnew model\b|\blaunch\w*|\breleas\w*|\bintroduc\w*|\bupgrade\b|\bupdate\b|выпуст|обновл|вышла|новая модель', title, re.I))
    ranking = bool(re.search(r'\bbenchmark\b|\barena\b|\brank\w*|\bindex\b|бенчмарк|рейтинг', title, re.I))
    workflow = bool(re.search(r'\bengineers use\b|\bmaintenance backlog\b|\bworkflow\b|рабочий процесс', title, re.I))
    if recap:
        kind, score = 'recap_without_distinct_event', 0
    elif integration:
        kind, score = 'integration', 70
    elif release:
        kind, score = 'release_or_update', 80
    elif ranking:
        kind, score = 'evaluation', 60
    elif workflow:
        kind, score = 'documented_workflow', 45
    else:
        kind, score = 'unclassified', 20
    evidence = 'primary_post' if official else ('linked_source' if re.search(r'https?://', summary) else 'unresolved')
    return {'eligibility': 'needs_event_evidence' if recap else 'pending_existing_checks',
            'verifiability': evidence, 'priority': score, 'event_kind': kind,
            'primary': official, 'event_key': key,
            'reason': 'Event type schedules review; primary status never approves claims'}


def queue(rows, sources):
    """One representative per identifiable event first, alternatives afterwards.

    Alternatives remain pending until the representative has a verified card.
    Failed representatives never make an event permanently disappear.
    """
    ranked = sorted(rows, key=lambda row: (
        decision(row, sources.get(row['source']))['priority'],
        decision(row, sources.get(row['source']))['primary'], row['published']), reverse=True)
    # Choose a primary representative over a repost of the same exact event.
    representatives, alternatives, seen = [], [], set()
    for row in sorted(ranked, key=lambda r: decision(r, sources.get(r['source']))['primary'], reverse=True):
        key = event_key(row)
        if key is not None and key in seen:
            alternatives.append(row)
        else:
            representatives.append(row)
            if key is not None:
                seen.add(key)
    order = {row['url']: index for index, row in enumerate(ranked)}
    return sorted(representatives, key=lambda r: order[r['url']]) + alternatives
