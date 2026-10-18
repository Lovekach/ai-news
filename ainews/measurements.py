"""Small, source-bound measurement vocabulary; unknown metrics stay with the verifier."""
from __future__ import annotations

import re
from decimal import Decimal

_NUMBER = r'(?P<number>[+-]?(?:\d{1,3}(?:[, \u00a0\u202f]\d{3})+(?!\d)|\d+(?:[.,]\d+)?))\s*(?P<scale>(?:billion|million|thousand|k|m|b|тысяч[аи]?|миллиард(?:а|ов)?|миллион(?:а|ов)?|тыс\.?|млн\.?|млрд\.?)(?!\w))?'
_TOKEN = r'(?:tokens?|toks?|токен\w*)'
_RATE = re.compile(_NUMBER + r'\s*' + _TOKEN + r'\s*(?:/\s*s\b|per second\b|в\s+секунд\w*|/\s*с\b)', re.I)
_EFFICIENCY = re.compile(_NUMBER + r'\s*' + _TOKEN + r'\s*(?:per\s+(?:dollar|\$)|/\s*\$|(?:за|на)\s+(?:(?:один|1)\s+)?(?:доллар|\$))', re.I)
_POINTS = re.compile(_NUMBER + r'\s*(?:points?|пункт\w*)\b', re.I)
_SCALE = {'k': 1000, 'тыс': 1000, 'thousand': 1000, 'm': 1000000, 'млн': 1000000,
          'million': 1000000, 'b': 1000000000, 'млрд': 1000000000, 'billion': 1000000000}
_COUNT_WORDS = dict(zip('one two three four five six seven eight nine ten eleven twelve'.split(),range(1,13)))
_COUNT_WORDS.update({'один':1,'одна':1,'два':2,'две':2,'двух':2,'три':3,'трёх':3,'трех':3,
                     'четыре':4,'четырёх':4,'четырех':4,'пять':5,'пяти':5,'шесть':6,'шести':6})
_COUNT = re.compile(r'(?<![\w.+-])(?P<n>\d+|'+'|'.join(_COUNT_WORDS)+r')\s+(?P<new>new\s+|нов\w*\s+)?'
                    r'(?P<entity>labs?|laboratories|companies|teams?|models?|лаборатор\w*|компани\w*|команд\w*|модел\w*)\b',re.I)


def _scale(value: str | None) -> int:
    value = (value or '').lower().rstrip('.')
    return (1000000000 if value.startswith('миллиард') else 1000000 if value.startswith('миллион')
            else 1000 if value.startswith('тысяч') else _SCALE.get(value, 1))


def numeric_key(value: str) -> str:
    return str(Decimal(value.replace(',', '.')).normalize())


def _decimal(value: str, context: str) -> Decimal:
    # English numeric grouping differs from Russian decimal commas. Keep the
    # untouched quotation in the binding; this is normalization, not a fact.
    value = re.sub(r'[ \u00a0\u202f]', '', value)
    english = sum(c.isascii() and c.isalpha() for c in context) > len(re.findall('[а-яё]', context, re.I))
    if english and re.fullmatch(r'[+-]?[1-9]\d{0,2}(?:,\d{3})+', value):
        return Decimal(value.replace(',', ''))
    return Decimal(value.replace(',', '.'))


def numeric_values(text: str) -> set[str]:
    text = re.sub(r'\b\d{1,3}(?:,\d{3})+(?=\s+(?:pull requests?|PRs?|lines?|tokens?)\b)',
                  lambda m: m[0].replace(',', ''), text, flags=re.I)
    values = set()
    for match in re.finditer(_NUMBER, text, re.I):
        scale = _scale(match['scale'])
        values.add(str((abs(_decimal(match['number'], text)) * scale).normalize()))
    words = 'one two three four five six seven eight nine ten eleven twelve'.split()
    for index, word in enumerate(words, 1):
        if re.search(r'\b' + word + r'\s+(?:new\s+)?(?:engineers?|people|developers?|weeks?|days?|tasks?|requests?|lines?|labs?|models?|teams?|companies)\b', text, re.I):
            values.add(numeric_key(str(index)))
    return values


def _scope(tail: str, *, preceding: bool = False) -> str:
    matches = [(m.start(), name) for name, pattern in [
        ('gpu', r'(?:per\s+|/\s*|на\s+(?:один\s+)?)gpu\b'),
        ('user', r'(?:per\s+|/\s*)user\b|(?:на|для)\s+(?:одного\s+)?пользовател'),
        ('mw', r'(?:per\s+|/\s*|на\s+)(?:mw\b|мвт\b|мегаватт\w*)')]
        for m in re.finditer(pattern, tail, re.I)]
    return (max(matches) if preceding else min(matches))[1] if matches else ''


def _rate_scope(sentence: str, match) -> str:
    prefix = re.split(r'[,;:]', sentence[max(0,match.start()-65):match.start()])[-1]
    return (_scope(sentence[match.end():match.end()+100])
            or _scope(prefix, preceding=True))


def bindings(text: str, *, subject: str = '', source: str = '') -> list[dict]:
    """Keep the tuple, scope and verbatim context together; never infer hardware."""
    from .quality import sentences
    result = []
    for sentence in sentences(text.replace('\n', ' ')):
        for match in _COUNT.finditer(sentence):
            noun=match['entity'].casefold()
            unit=next(name for name,pattern in [('lab',r'lab|лаборатор'),('company',r'compan|компани'),
                      ('team',r'team|команд'),('model',r'model|модел')] if re.match(pattern,noun))
            number=match['n'].casefold()
            result.append({'metric':'entity_count','value':numeric_key(str(_COUNT_WORDS.get(number,number))),
                'unit':unit,'scope':'new' if match['new'] else '', 'conditions':{'components':[], 'hardware':[],
                'concurrency':[], 'user_rate':[]},'object':subject,'source':source,'quote':sentence})
        for kind, pattern in [('rate', _RATE), ('efficiency', _EFFICIENCY), ('points', _POINTS)]:
            for match in pattern.finditer(sentence):
                prefix = sentence[max(0, match.start()-65):match.start()].casefold().rstrip(' \t:=-—–')
                value = _decimal(match['number'], sentence) * _scale(match['scale'])
                scope = _rate_scope(sentence, match) if kind == 'rate' else ''
                folded = sentence.casefold()
                metric = 'unspecified_rate'
                unit = 'tokens/s'
                if kind == 'efficiency':
                    metric = ('tco_efficiency' if re.search(r'tco|совокупн\w*\s+стоимост\w*\s+владени', folded)
                              else 'token_efficiency')
                    if re.search(r'цен\w*\s+api|стоимост\w*\s+(?:api|токен)|api\s+(?:price|pricing)', folded):
                        metric = 'api_price'
                    unit = 'tokens/USD'
                elif kind == 'points':
                    if re.search(r'praise\s*(?:vs\.?|versus|/)\s*complaint|предпочтен|похвал', folded):
                        metric = 'preference'
                    elif re.search(r'жалоб|complaints?', folded):
                        metric = 'complaints'
                    else:
                        continue  # Other scores are not interchangeable with preferences.
                    unit = 'points'
                elif re.search(r'(?:генерац\w*|выходн\w*|output)(?:\s+(?:token|tokens|rate|throughput|до|of|up to))*\s*[:=]?\s*$', prefix):
                    metric = 'output_rate'
                elif re.search(r'(?:входн\w*|input|prefill)(?:\s+(?:token|tokens|rate|throughput|до|of|up to))*\s*[:=]?\s*$', prefix):
                    metric = 'input_rate'
                elif re.search(r'(?:кэш\w*|кеш\w*|cached)(?:\s+(?:token|tokens|rate|throughput|до|of|up to))*\s*[:=]?\s*$', prefix):
                    metric = 'cached_rate'
                elif scope == 'user':
                    metric = 'user_rate'
                elif re.search(r'throughput|суммарн|совокупн|cached.*input.*output', folded):
                    metric = 'aggregate_rate'
                components = [name for name, pattern in [('cached', r'cached|кэш|кеш'),
                              ('input', r'\binput\b|\bввод|входн'), ('output', r'\boutput\b|\bвывод|выходн')]
                              if re.search(pattern, folded)] if kind == 'rate' else []
                conditions = {'components': components,
                    'hardware': [h.upper() for h in re.findall(r'\b(?:[ABH]\d{3}|MI\d{3}X?|GB\d{3}|NVFP\d+|BF16|FP16|FP8|INT8)\b', sentence, re.I)],
                    'concurrency': re.findall(r'(?:batch size|concurrency|параллельных запросов)\s*(?:of|=|:)?\s*(\d+)', folded),
                    'user_rate': [str((_decimal(m['number'], sentence) * _scale(m['scale'])).normalize())
                                  for m in _RATE.finditer(sentence) if _rate_scope(sentence,m) == 'user']}
                row = {'metric': metric, 'value': str(value.normalize()), 'unit': unit,
                    'scope': scope, 'conditions': conditions, 'object': subject, 'source': source,
                    'quote': sentence}
                # In "A vs B tokens/s", both values share the written unit.
                # Keep comparison roles explicit; never guess device ownership.
                pair = re.search(_NUMBER + r'\s*(?:vs\.?|versus|против)\s*$', sentence[:match.start()], re.I)
                if pair:
                    left = _decimal(pair['number'], sentence) * _scale(pair['scale'])
                    result.append({**row, 'value': str(left.normalize()), 'comparison_position': 'left'})
                    row['comparison_position'] = 'right'
                result.append(row)
    return result


def measurement_issues(source: str, draft: str) -> list[str]:
    observed, claimed = bindings(source), bindings(draft)
    issues = []
    for claim in claimed:
        same_unit = [s for s in observed if s['unit'] == claim['unit']]
        if not same_unit:
            continue  # The existing numeric and semantic verifier handles unknown units.
        matches = [s for s in same_unit if s['value'] == claim['value']]
        if not matches:
            if claim['metric']=='entity_count':
                continue  # Ambiguous noun adjacency is not proof of a count; verify semantically.
            issues.append('Measurement value or magnitude differs from source: ' + claim['value'] + ' ' + claim['unit']
                          + '; source values: ' + ', '.join(s['value'] for s in same_unit))
            continue
        compatible = [s for s in matches if (s['metric'] == claim['metric'] or
                      'unspecified_rate' in {s['metric'], claim['metric']})
                      and (not s['scope'] or s['scope'] == claim['scope'])]
        if not compatible:
            if claim['metric']=='entity_count':
                issues.append('Count lost its new-participant scope: сохрани уточнение «новые» рядом с числом '
                              'участников или моделей; это не общее количество. Source: '+matches[0]['quote'][:250])
                continue
            issues.append('Measurement meaning or per-device/per-user scope differs from source: '
                          + claim['value'] + ' ' + claim['unit'] + '; draft=' + claim['metric'] + '/' + claim['scope']
                          + '; source=' + ', '.join(s['metric'] + '/' + s['scope'] for s in matches)
                          + '. Exact source: ' + matches[0]['quote'][:350]
                          + '. Retain the source metric and accounting conditions; aggregate tokens are not generated output.')
            if any(s['metric'] == 'tco_efficiency' for s in matches):
                issues.append('Укажи TCO (совокупную стоимость владения) рядом с числом токенов за доллар, '
                              'в том числе в заголовке, если число стоит там. Это не цена API.')
            if any(s['metric'] == 'aggregate_rate' for s in matches) and claim['metric'] == 'output_rate':
                issues.append('Замени «скорость генерации» на «совокупная пропускная способность», '
                              'сохрани учёт кэша, входных и выходных токенов. Это не скорость генерации ответа.')
            continue
        if all(s['metric'] == 'aggregate_rate' and set(s['conditions']['components']) == {'cached', 'input', 'output'}
               for s in compatible):
            if set(claim['conditions']['components']) != {'cached', 'input', 'output'}:
                issues.append('Aggregate rate omits its cached/input/output accounting conditions')
        if claim['scope'] in {'gpu', 'mw'}:
            for condition in ('hardware', 'user_rate'):
                if condition == 'hardware' and any(s.get('comparison_position') for s in compatible):
                    continue  # Shared comparison context: quote verifier binds each object.
                required = [set(s['conditions'][condition]) for s in compatible]
                if required and required[0] and all(value == required[0] for value in required):
                    if not required[0].issubset(set(claim['conditions'][condition])):
                        issues.append('Per-device throughput omits its measured hardware or target user rate')
    return list(dict.fromkeys(issues))
