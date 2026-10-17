"""Source-bound sentence verdicts shared by the editor and final formatter."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

FIELDS = {'Что произошло: ': 'what', 'Простыми словами: ': 'simple',
          'Зачем это нужно: ': 'why', 'Что важно знать: ': 'caveat'}
FACT_FIELDS = ('entity', 'version', 'event', 'date', 'attribute', 'value', 'unit', 'conditions', 'basis', 'platform', 'kind')
IDENTIFIER = re.compile(r'\b[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*\b')
SCHEMA = {'type': 'object', 'properties': {'checks': {'type': 'array', 'items': {
    'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'status': {'type': 'string', 'enum': ['supported', 'unsupported', 'uncertain']},
        'source': {'type': 'integer', 'minimum': 0}, 'quote': {'type': 'array', 'minItems': 1, 'maxItems': 3,
            'items': {'type': 'string', 'minLength': 12, 'maxLength': 300}},
        **{field: {'type': 'string', 'maxLength': 120} for field in FACT_FIELDS},
    }, 'required': ['id', 'status', 'source', 'quote', *FACT_FIELDS]}, 'maxItems': 18}}, 'required': ['checks']}
SCHEMA['properties']['checks']['items']['properties'].update({
    'event': {'type': 'string', 'enum': ['release', 'support', 'availability', 'update', 'benchmark', 'opinion', 'other']},
    'basis': {'type': 'string', 'enum': ['source_claim', 'source_measurement', 'opinion']},
    'kind': {'type': 'string', 'enum': ['model', 'tool', 'company', 'person', 'standard', 'other']},
})


def normalized(value: str) -> str:
    return ' '.join(value.split())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def literal_span(source: str, quote: str) -> str | None:
    """Recover original typography, without repairing words or factual values."""
    typography = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'})
    chars, positions = [], []
    for index, char in enumerate(source):
        if char.isspace():
            if chars and chars[-1] != ' ':
                chars.append(' '); positions.append(index)
        else:
            chars.append(char.translate(typography)); positions.append(index)
    wanted = normalized(quote).translate(typography)
    at = ''.join(chars).find(wanted)
    if not wanted or at < 0:
        return None
    return source[positions[at]:positions[at + len(wanted) - 1] + 1]


def sentences(value: str) -> list[str]:
    # Share these boundaries with the formatter. Decimal dots have no space;
    # common numeric abbreviations must keep their following unit attached.
    boundary = r'(?<!тыс\.)(?<!млн\.)(?<!млрд\.)(?<!трлн\.)(?<=[.!?])\s+'
    return [part.strip() for part in re.split(boundary, value, flags=re.I) if part.strip()]


def claims(text: str) -> list[dict]:
    parts = text.split('\n\n')
    output = [{'id': 'c0', 'field': 'headline', 'text': parts[0].removeprefix('🧠 ').strip()}]
    for part in parts[1:]:
        for label, field in FIELDS.items():
            if part.startswith(label):
                start = len(output)
                output.extend([{'id': f'c{start+index}', 'field': field, 'text': sentence}
                               for index, sentence in enumerate(sentences(part[len(label):]))])
                break
    return output


def identifiers(text: str) -> set[str]:
    return {match[0].casefold() for match in IDENTIFIER.finditer(text)
            if len(match[0]) >= 2 and any(char.isdigit() for char in match[0])}


def identity_issues(source: str, text: str) -> list[str]:
    known = identifiers(source)
    errors = []
    for item in identifiers(text):
        if item in known or any(original.startswith(item + '-') for original in known):
            continue
        # Hyphens and spaces in a test/product label are typography; dots in
        # numeric versions and alphanumeric suffixes remain significant.
        spelling = r'[ -]*'.join(re.escape(part) for part in item.split('-'))
        if '-' in item and re.search(r'\b' + spelling + r'\b', source, re.I):
            continue
        split = re.fullmatch(r'([a-z]+)(\d[\w.-]*)', item)
        if split and re.search(r'\b' + re.escape(split[1]) + r'[ -]+' + re.escape(split[2]) + r'\b', source, re.I):
            continue
        errors.append('Identifier not present in corresponding evidence: ' + item)
    return errors


NUMBER = r'(?<![\w.-])([+−-]?\d+(?:[.,]\d+)?)\s*((?:[kmbt]|тыс|млн|млрд|трлн)\b\.?)?'
SCALE = {'k': 1000, 'тыс': 1000, 'm': 10**6, 'млн': 10**6,
         'b': 10**9, 'млрд': 10**9, 't': 10**12, 'трлн': 10**12}
QUANTITY = re.compile(NUMBER + r'\s*(?:(?:active|total|output|активн\w*|выходн\w*)\s+)?'
                      r'(tokens?|characters?|parameters?|milliseconds?|seconds?|ms\b|токен\w*|символ\w*|параметр\w*|мс\b|секунд\w*)', re.I)


def numbers(text: str) -> set[Decimal]:
    return {Decimal(match[1].replace(',', '.').replace('−', '-')) * SCALE.get((match[2] or '').casefold().rstrip('.'), 1)
            for match in re.finditer(NUMBER, text, re.I)}


def quantities(text: str) -> list[tuple[Decimal, str]]:
    result = []
    for match in QUANTITY.finditer(text):
        unit = match[3].casefold()
        kind = next((name for pattern, name in ((r'token|токен', 'tokens'), (r'character|символ', 'characters'),
                                                (r'parameter|параметр', 'parameters'), (r'ms|millisecond|мс', 'ms'),
                                                (r'second|секунд', 'seconds')) if re.match(pattern, unit)), unit)
        amount = Decimal(match[1].replace(',', '.').replace('−', '-')) * SCALE.get((match[2] or '').casefold().rstrip('.'), 1)
        result.append((amount, kind))
    return result


def documents(config: dict, source: str) -> list[dict]:
    supplied = config.get('_source_documents')
    if supplied:
        return [{'url': doc.get('url', ''), 'text': doc['text'],
                 'published': doc.get('published', '')} for doc in supplied]
    return [{'url': config.get('_source_url', ''), 'text': source,
             'published': config.get('_source_published', '')}]


def score_bindings(source: str) -> list[tuple[str, str]]:
    """Only explicit 'scores N on Metric' relations, never nearby table cells."""
    result = []
    for number, metric in re.findall(
        r'\bscor(?:es|ed|ing)\s+(\d+(?:\.\d+)?)\s+(?:points?\s+)?on\s+(?:the\s+)?'
        r'([A-Z][A-Za-z0-9_.-]*(?:\s+[A-Z][A-Za-z0-9_.-]*){0,4})', source):
        words = metric.split()
        end = next((index+1 for index, word in enumerate(words)
                    if word.rstrip('.') in {'Index', 'Benchmark', 'Test'}), len(words))
        result.append((number, ' '.join(words[:end]).rstrip('.')))
    return result


def score_in_text(number: str, text: str) -> bool:
    return bool(re.search(r'(?<![\d.])' + re.escape(number).replace(r'\.', '[.,]')
                          + r'\s*(?:балл|очк|пункт)', text, re.I))


def scope_score(source: str, text: str) -> str:
    bindings = {metric for number, metric in score_bindings(source) if score_in_text(number, text)}
    if (len(bindings) == 1 and not re.search(r'\b(?:тест\w*|бенчмарк\w*)\b', text, re.I)
            and next(iter(bindings)).casefold() not in text.casefold()):
        return next(iter(bindings)) + ': ' + text
    return text


def bound_issues(quote: str, text: str, fact: dict) -> list[str]:
    """Compare literal identities, explicit units and benchmark conditions."""
    from .quality import measurement_issues, derived_numbers
    # A quote may use a pronoun. Only the literal, source-validated entity
    # supplies its identity numbers; unrelated article numbers cannot help it.
    binding = quote + ' ' + fact.get('entity', '')
    errors = identity_issues(binding, text)
    derived = {Decimal(value) for value in derived_numbers(quote, text)}
    if numbers(text) - numbers(binding) - derived:
        errors.append('Numeric value absent from corresponding source quote')
    measured = score_bindings(quote)
    for number, metric in measured:
        if len({name for value, name in measured if Decimal(value) == Decimal(number)}) != 1:
            continue  # Coincident equal scores do not establish the metric.
        if not score_in_text(number, text):
            continue
        if metric.casefold() not in text.casefold():
            errors.append('Score must retain its corresponding named metric: ' + metric)
        for group in re.findall(r'\(([^)]{0,180})\)', text):
            labels = [part.strip() for part in re.split(r',|\s+(?:и|and|&)\s+', group)]
            labels = [part for part in labels if re.match(r'[A-Z][A-Za-z]', part)]
            if len(labels) > 1 and any(metric.casefold() in part.casefold() for part in labels):
                errors.append('Single benchmark score attributed to multiple named tests')
    source_quantities = quantities(quote)
    for amount, unit in quantities(text):
        kinds = {kind for value, kind in source_quantities if value == amount}
        if kinds and unit not in kinds:
            errors.append('Quantity unit contradicts the corresponding quoted value')
    if (re.search(r'\bстандарт\w*', text, re.I) and re.search(r'\bmodel\b', quote, re.I)
            and not re.search(r'\bstandards?\b|стандарт', quote, re.I)):
        errors.append('A source model was presented as a standard')
    # These checks use this claim's quote, not unrelated values elsewhere in
    # the article. Source-wide omission/attribution heuristics are not proof.
    errors.extend(issue for issue in measurement_issues(quote, text)
                  if ((issue.startswith(('Throughput', 'Aggregate throughput')))
                      or not any(word in issue for word in ('omits', 'needs source attribution',
                                                           'needs explicit measurement attribution'))))
    if re.search(r'tokens(?:/s| per second)|tok/s', quote, re.I) and re.search(r'токен\w*\s*(?:/с|в\s+секунд)', text, re.I):
        conditions = fact.get('conditions', '')
        for identifier in identifiers(conditions):
            if identifier not in identifiers(text):
                errors.append('Measured configuration identifier missing: ' + identifier)
        gpu_count = re.search(r'\b(\d+)\s*[×x]\s', conditions)
        words = {'2': 'двух|двумя|две', '4': 'четыр[её]х|четырьмя|четыре', '8': 'восьми|восемью|восемь'}
        if gpu_count and not re.search(r'\b(?:' + gpu_count[1] + '|' + words.get(gpu_count[1], gpu_count[1]) + r')\b', text, re.I):
            errors.append('Measured device count missing')
        if 'per user' in quote.casefold() and not re.search(r'на\s+(?:одного\s+)?пользовател', text, re.I):
            errors.append('Per-user scope missing')
        if 'high concurrency' in quote.casefold() and not re.search(r'суммарн|параллел|одновременн', text, re.I):
            errors.append('Aggregate concurrency condition missing')
    return errors


def validated_review(text: str, result: dict, sources: list[dict]) -> dict:
    """Reject incomplete contracts; prune individual unsupported sentences.

    A source quote is a necessary anchor, not independent proof of entailment.
    Semantic entailment is still the existing model's responsibility.
    """
    requested = claims(text)
    checks = result.get('checks')
    expected = {item['id'] for item in requested}
    if (not isinstance(checks, list) or any(not isinstance(row, dict) for row in checks)
            or len(checks) != len(expected) or {row.get('id') for row in checks} != expected):
        raise ValueError('Incomplete or duplicate claim verdicts')
    indexed = {row['id']: row for row in checks}
    kept, rejected = [], []
    for claim in requested:
        verdict = indexed[claim['id']]
        verdict = dict(verdict)
        record = {**claim, **{key: verdict.get(key) for key in FACT_FIELDS}}
        index, raw_quote = verdict.get('source'), verdict.get('quote')
        # A compound sentence may need separate literal spans. Never accept
        # an ellipsis-spliced quote as though it appeared in the original.
        spans = [raw_quote] if isinstance(raw_quote, str) else raw_quote
        valid_source = type(index) is int and 0 <= index < len(sources)
        valid_quote = (valid_source and isinstance(spans, list) and 1 <= len(spans) <= 3
                       and all(isinstance(span, str) and 12 <= len(span.strip()) <= 600 for span in spans))
        if valid_quote:
            originals = [literal_span(sources[index]['text'], span) for span in spans]
            valid_quote = all(span is not None for span in originals)
            if valid_quote:
                spans = originals
        quote = ' '.join(spans) if isinstance(spans, list) and all(isinstance(span, str) for span in spans) else ''
        errors = []
        if verdict.get('status') != 'supported':
            errors.append('Claim verdict: ' + str(verdict.get('status')))
        if not valid_quote:
            errors.append('Missing exact source evidence')
        valid_fields = all(isinstance(verdict.get(key), str) for key in FACT_FIELDS)
        if not valid_fields:
            errors.append('Invalid fact fields')
        if verdict.get('basis') not in {'source_claim', 'source_measurement', 'opinion'}:
            errors.append('Invalid evidence basis; independent confirmation cannot be invented')
        if valid_quote and valid_fields:
            repairs = []
            for key in ('version', 'value', 'unit', 'conditions', 'date', 'platform'):
                value = verdict.get(key)
                if isinstance(value, str) and value and normalized(value).casefold() not in normalized(quote).casefold():
                    # Metadata extraction is not prose. Clearing an invented
                    # metadata date must not reject an otherwise true sentence.
                    # Actual rendered numbers/units/identities are checked below.
                    verdict[key] = record[key] = ''
                    repairs.append(key)
            entity = verdict.get('entity')
            if entity and entity.casefold() not in normalized(sources[index]['text']).casefold():
                verdict['entity'] = record['entity'] = ''
                repairs.append('entity')
            elif entity:
                original = normalized(sources[index]['text'])
                at = original.casefold().find(entity.casefold())
                record['entity_quote'] = original[max(0, at-80):at+len(entity)+100]
            record['metadata_repairs'] = repairs
            scoped = scope_score(quote, claim['text'])
            if scoped != claim['text']:
                record['original_text'] = claim['text']
                record['text'] = scoped
            errors.extend(bound_issues(quote, record['text'], verdict))
        record.update(quote=quote, evidence_spans=spans if valid_quote else [], source_url=sources[index]['url'] if valid_source else '',
                      source=index, source_hash=digest(sources[index]['text']) if valid_source else '',
                      status='supported' if not errors else 'held', issues=errors)
        if errors:
            rejected.append(record)
        else:
            # Same source evidence and same explicit fact tuple can safely
            # collapse a repeated explanation. Empty tuples are not identity.
            key = (index, quote, *(record[field] for field in FACT_FIELDS))
            if (record['attribute'] and record['field'] != 'headline'
                    and any(row['field'] != 'headline' and row.get('_key') == key for row in kept)):
                rejected.append({**record, 'status': 'redundant', 'issues': ['Repeated source-bound fact']})
            else:
                kept.append({**record, '_key': key})
    body = [row for row in kept if row['field'] == 'what']
    main = next((row for row in requested if row['field'] == 'what'), None)
    if not body or not main or not any(row['id'] == main['id'] for row in body):
        problems = [issue for row in rejected if main and row['id'] == main['id'] for issue in row['issues']]
        raise ValueError('No supported main sentence; a local repair or review is required: ' + '; '.join(problems))
    headings = [row for row in kept if row['field'] == 'headline']
    if not headings:
        # Reuse an intact verified sentence when possible; otherwise a literal
        # source entity is a safe title. Do not invent a release/update label.
        first = body[0]
        title = first.get('entity', '') or (first['text'] if len(first['text']) <= 100 else '')
        if (not title or len(title) > 100
                or (title.casefold() not in normalized(sources[first['source']]['text']).casefold() and title != first['text'])):
            raise ValueError('No supported headline; a local repair or review is required')
        kept.insert(0, {**first, 'id': 'derived-headline', 'field': 'headline', 'text': title})
    for row in kept:
        row.pop('_key', None)
    # A source's benchmark statement is not independent confirmation. Scope
    # it once in the body and use a literal title when a claim-only headline
    # would make an unqualified comparative assertion.
    from .quality import comparison_attributed
    benchmarks = [row for row in body if row['event'] == 'benchmark'
                  and row['basis'] in {'source_claim', 'source_measurement'}]
    if benchmarks and not comparison_attributed('', render(kept)):
        first = body[0]
        first['original_text'] = first['text']
        first['text'] = 'По данным источника, ' + (first['text'][0].lower() if first['text'][0].isalpha()
                                                  and not first['text'][0].isascii() else first['text'][0]) + first['text'][1:]
        heading = next(row for row in kept if row['field'] == 'headline')
        entity = benchmarks[0]['entity']
        if entity:
            heading['original_text'] = heading['text']
            heading['text'] = entity
    return {'claims': kept, 'rejected': rejected, 'text': render(kept),
            'source_hashes': [digest(doc['text']) for doc in sources]}


def event_key(ledger: dict | None, title: str = ''):
    if not ledger:
        return None
    main = next((row for row in ledger['claims'] if row['field'] == 'what'), None)
    if not main or not main['entity'] or main['event'] not in {'release', 'support', 'availability', 'update', 'benchmark'}:
        return None
    subject = main
    heading = next((row for row in ledger['claims'] if row['field'] == 'headline'), None)
    if (heading and main['event'] in {'release', 'availability', 'update'}
            and heading['entity']
            and heading['entity'].casefold() in main['text'].casefold()):
        # A subordinate integration mentioned later in a compound sentence
        # must not replace the verified headline's primary product.
        subject = heading
    if subject['kind'] not in {'model', 'tool'}:
        # A company can announce several unrelated products on the same day.
        # Its name alone is not a product/event identity; use legacy title/link
        # evidence rather than merging all its announcements together.
        return None
    entity = re.sub(r'[\s-]+', ' ', subject['entity'].casefold()).strip()
    if title:
        from .quality import event_signature
        original = event_signature(title, '')
        if original:
            full = original[1]
            if (full == entity or full.startswith(entity + ' ') or full.endswith(' ' + entity)):
                entity = full
    version = re.sub(r'[\s-]+', ' ', subject['version'].casefold()).strip()
    if version and version in entity:
        version = ''  # Redundant extraction, not a different product version.
    # The event date is used only when explicit. Detection/publication dates
    # never silently become a model release date.
    return (entity, version, main['event'], main['date'], main['platform'].casefold())


def render(records: list[dict]) -> str:
    heading = next(row['text'] for row in records if row['field'] == 'headline')
    parts = ['🧠 ' + heading]
    for label, field in FIELDS.items():
        content = ' '.join(row['text'] for row in records if row['field'] == field)
        if content:
            parts.append(label + content)
    return '\n\n'.join(parts)


def load_ledger(store, row) -> dict | None:
    found = store.db.execute("SELECT details FROM editorial_audit WHERE url=? AND stage='claim_ledger' ORDER BY id DESC LIMIT 1",
                             (row['url'],)).fetchone()
    if not found:
        return None
    ledger = json.loads(found[0])
    if ledger.get('source_hash') != digest(row['article'] or row['summary']):
        return None
    return ledger


def final_issues(source: str, text: str, ledger: dict) -> list[str]:
    """Formatting can remove intact sentences; it cannot create new claims."""
    from .quality import relational_issues, check_semantic_claims
    approved = {normalized(row['text']) for row in ledger['claims']}
    body = text.removeprefix('🧠 ').removeprefix('- ')
    # Final cards have no internal labels; URLs are rendered separately.
    for label in FIELDS:
        body = body.replace(label, '')
    blocks = [part.strip() for part in body.split('\n\n') if part.strip() and not part.startswith('https://')]
    actual = [blocks[0]] if blocks else []
    actual.extend(sentence.strip() for part in blocks[1:] for sentence in sentences(part.strip()))
    errors = []
    if any(normalized(sentence) not in approved for sentence in actual):
        errors.append('Final text contains an unverified or changed sentence')
    errors.extend(identity_issues(source, '\n'.join(actual)))
    try:
        check_semantic_claims(source, text, check_measurements=False)
    except ValueError as exc:
        errors.append(str(exc))
    # Retain explicit arithmetic checks after shortening; source-global rules
    # about omitted details do not overrule a source-bound sentence verdict.
    errors.extend(issue for issue in relational_issues(source, text)
                  if any(word in issue for word in ('subtraction', 'Score difference', 'Cost ratio',
                                                     'Cost saving', 'comparison model')))
    return errors
