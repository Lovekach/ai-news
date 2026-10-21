"""Checks for semantic mistakes found in the published-news audit."""
import re
from datetime import datetime


def sentences(text: str) -> list[str]:
    """Sentence boundaries shared with compaction; keep numeric units attached."""
    return [part.strip() for part in re.split(
        r'(?<!тыс\.)(?<!млн\.)(?<!млрд\.)(?<!трлн\.)(?<=[.!?])\s+', text.strip(), flags=re.I)
            if part.strip()]


def complete_sentence(text: str) -> bool:
    value = text.strip()
    if not re.search(r'[.!?][»”"\')\]]*$', value) or value.endswith(('...', '…')):
        return False
    if re.search(r'\b(?:тыс|млн|млрд|трлн)\.$', value, re.I):
        return False
    if re.search(r'[~≈$=:/−—-]\s*[.!?]|\d[.,]\s*[.!?]', value):
        return False
    return (value.count('(') == value.count(')') and value.count('[') == value.count(']')
            and value.count('«') == value.count('»') and value.count('“') == value.count('”')
            and value.count('"') % 2 == 0)


def trim_incomplete_tail(text: str) -> tuple[str, str]:
    if complete_sentence(text):
        return text, ''  # Quoted text can span several sentences.
    parts = sentences(text)
    if parts and not complete_sentence(parts[-1]):
        return ' '.join(parts[:-1]), parts[-1]
    return text, ''


def headline_issues(headline: str) -> list[str]:
    if len(re.findall(r'[^\W_][\w.-]*', headline)) < 2 or not complete_sentence(headline+'.'):
        return ['Headline lacks an informative event description']
    if len(headline) >= 100:
        return ['Headline reaches the generation schema limit; rewrite a shorter complete title']
    if re.search(r'\b(?:в|на|от|для|с|до|и|из|к|по|при|без)$', headline, re.I):
        return ['Headline ends with an unfinished phrase']
    return []


def integrity_issues(text: str, *, headline: str | None = None) -> list[str]:
    parts = text.split('\n\n')
    if parts and parts[0].startswith(('🧠 ', '- ')):
        first = parts.pop(0)
        headline = headline or first[2:].strip()
    issues = headline_issues(headline) if headline is not None else []
    for part in parts:
        if not part.strip() or part.lstrip().startswith(('https://', 'http://')):
            continue  # Private source suffix; the public transport forbids it.
        body = re.sub(r'^(?:Что произошло|Простыми словами|Зачем это нужно|Что важно знать):\s*', '', part.strip())
        if not complete_sentence(body):
            issues.append('Incomplete sentence, unbalanced delimiter or truncated characteristic')
    return list(dict.fromkeys(issues))


def freshness_hours(config: dict, source: dict) -> int:
    if config.get("publication_mode") == "daily":
        return 24
    window = int(config.get("digest_lookback_hours", 1))
    if source.get("type") in {"telegram", "x"}:
        return window
    return max(window, int(config.get("official_catchup_hours", window)))

_ENTITY = re.compile(
    r"\b(?:GPT[ -]?\d+(?:\.\d+)*(?:\s+(?:Sol|Astra|Luna))?|"
    r"Claude\s+(?:Sonnet|Opus|Haiku)\s+\d+(?:\.\d+)*|"
    r"Gemini\s+\d+(?:\.\d+)*(?:\s+Argon)?|Qwen\d+(?:\.\d+)*(?:-\d+B(?:-A\d+B)?)?|"
    r"Mistral\s+(?:Large|Medium|Small)\s+\d+(?:\.\d+)*|"
    r"DeepSeek[ -]?(?:V|R)\d+(?:\.\d+)*|GLM[ -]?\d+(?:\.\d+)*|MiniMax[ -]?M\d+(?:\.\d+)*|"
    r"Ideogram\s+\d+(?:\.\d+)*|SynthID\s+Bio|ProvenanceGuard|Kumo\s+Tabular|"
    r"Context\s+Language\s+Models|Ember-\d+|Holo\d+(?:-\d+B(?:-A\d+B)?)?|"
    r"Hermes(?:\s+Agent)?|DigUp|NeatLogs|Le\s+Chonk)\b", re.I)


_VERSIONED_PRODUCT = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z]+)?[ -]v?\d+(?:\.\d+)+(?:-[A-Za-z0-9]+)*\b|"
    r"\b[A-Za-z][A-Za-z0-9]*\d+\.\d+(?:-[A-Za-z0-9]+)*\b")
_NAMED_INDEX = re.compile(r"\b(?!(?:Introducing|Announcing|The)\b)(?:[A-Z][A-Za-z]+[ -]){1,4}(?:Index|Benchmark)\b")


def event_signature(headline: str, body: str) -> tuple[str, str, str, str] | None:
    """Use the main subject and event type, not competitor names in the body."""
    # A competitor mentioned in the body cannot become the main subject.
    subjects = [match for match in (_ENTITY.search(headline), _VERSIONED_PRODUCT.search(headline),
                                    _NAMED_INDEX.search(headline)) if match]
    match = min(subjects, key=lambda found: found.start()) if subjects else None
    if not match and len(body) <= 120 and not re.search(
            r"\b(?:vs|uses?|like|comparison|compared)\b|срав|например|использ", body, re.I):
        candidates = list(_ENTITY.finditer(body))
        if len(candidates) == 1:
            match = candidates[0]
    if not match:
        return None
    entity = re.sub(r"[\s-]+", " ", match.group().casefold())
    if _NAMED_INDEX.fullmatch(match.group()):
        version = re.search(re.escape(match.group()) + r"\s+v?(\d+(?:\.\d+)+)", headline + ' ' + body, re.I)
        if version:
            entity += ' ' + version[1]
    # The headline identifies the event. The body may mention unrelated tests
    # or competing models, which must not turn every item into a pricing event.
    title = headline.casefold()
    text = title + " " + body.casefold()
    if re.search(r"уязвим|кибер|bug hunt|cybergym", title):
        focus = "cyber"
    elif re.search(r"цен|стоим|дешев|дешёв|эконом|выгод|cost|price", title):
        focus = "pricing"
    elif re.search(r"бенчмарк|benchmark|dense.?200|grounding|decision index", title):
        focus = "benchmark"
    elif re.search(r"рейтинг|занял|заняла|место|arena|leaderboard", title):
        focus = "ranking"
    elif re.search(r"исправ|ошибк|patch|fix", title):
        focus = "fix"
    elif re.search(r"обнов|update|upgrade", title):
        focus = "update"
    elif re.search(r"new model|model release|новая модель|новый релиз", title):
        focus = "announcement"
    elif re.search(r'\bsupport(?:ed)?\b|\bintegration\b|поддержк|интеграц', title):
        focus = 'support'
    elif re.search(r"доступ|платформ|api|вес\w*\s+откры|available|comes to|"
                   r"(?:добавлен\w*|откр\w*).{0,60}(?:прилож|разработчик)|в\s+приложение", title):
        focus = "availability"
    else:
        focus = "announcement"
    provider = ""
    if focus in {"availability", "support"}:
        platforms = ("nebius", "arena", "bedrock", "ollama", "vllm", "sglang", "hugging face")
        provider = (next((name for name in platforms if name in title), "")
                    or next((name for name in platforms if name in text), ""))
    # Product patch releases are different events; don't mix consecutive days'
    # versions just because the agent name is the same.
    if entity.startswith("hermes"):
        version = re.search(r"\bv?(\d+\.\d+\.\d+)\b", headline + " " + body)
        entity = "hermes agent" + (" " + version[1] if version else "")
    brand = re.split(r"[\s\d]", entity)[0]
    company = {"gpt": "openai", "claude": "anthropic", "gemini": "google",
               "qwen": "alibaba", "lfm": "liquidai"}.get(brand, brand)
    return company, entity, focus, provider


def source_window(text: str, limit: int = 7000) -> str:
    """Keep verbatim evidence at both ends, especially attribution/conditions.

    A prefix-only cut hid independent authorship in long README footers. This
    envelope is shared by the writer, editor and verifier, not a second summary.
    """
    if len(text) <= limit:
        return text
    tail_size = min(1000, limit // 4)
    head = text[:max(1, limit - tail_size - 1600)]
    tail = text[-tail_size:]
    essential = re.compile(r"not affiliated|isn't affiliated|founder|developed by|built by|"
                           r"release date|published|only|unchanged|forks|mirrors", re.I)
    quantified = re.compile(r"\d+(?:\.\d+)?%|(?:\d[\d,.]*\s*[kmb]?|one|two|three|four|five|six|seven|eight|nine|ten)"
                           r"\s+(?:pull requests?|PRs?|lines?|engineers?|developers?|weeks?|days?|tokens?|parameters?)\b", re.I)
    budget = limit - len(head) - len(tail) - 120
    chosen = [(0, len(head)), (len(text)-len(tail), len(text))]
    # Keep ownership/date restrictions first. Merge overlapping excerpts so
    # a count, its unit and time interval do not consume the budget repeatedly.
    for pattern in (essential, quantified):
        ranges = []
        for match in pattern.finditer(text, len(head), len(text)-len(tail)):
            start, end = max(len(head), match.start()-100), min(len(text)-len(tail), match.end()+220)
            if ranges and start <= ranges[-1][1] and end-ranges[-1][0] <= min(900, max(1, budget)):
                ranges[-1] = (ranges[-1][0], max(end, ranges[-1][1]))
            else:
                ranges.append((start, end))
        for start, end in ranges:
            if end-start <= budget:
                chosen.append((start, end))
                budget -= end-start+24
    merged = []
    for start, end in sorted(chosen):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return '\n[Пропуск текста]\n'.join(text[start:end] for start, end in merged)[:limit]


def editorial_context(config: dict) -> str:
    """Provenance is not authorship; dates describe their actual meaning."""
    provenance = (f"\nURL первоисточника: {config.get('_source_url', 'не указан')}"
            f"\nАккаунт сообщения (не обязательно разработчик): {config.get('_source_author', 'не установлен')}"
            f"\nДата публикации сообщения: {config.get('_source_published', 'не установлена')}"
            f"\nДата публикации материала: {config.get('_original_published') or 'не установлена'}"
            f"\nКалендарная дата выпуска (МСК): {config.get('_edition_date') or 'не указана'}")
    if config.get('_signal_title_unverified'):
        provenance += '\nЗаголовок вторичного поста не является доказательством. Все факты и числа подтверждай только первичным текстом.'
    return (provenance +
            "\nДата обнаружения не доказывает дату события. Не называй старый продукт новым релизом "
            "по сегодняшнему репосту. Если дата события неизвестна, не выдумывай её. "
            "Автор комментария, автор цитаты, разработчик модели и разработчик приложения — разные роли. "
            "Не объявляй комментатора основателем или инвестором без прямого подтверждения. "
            "В заголовке называй конкретный продукт, не только номер версии. "
            "Вендорский benchmark — заявление автора: сохраняй атрибуцию, метрику, единицы, "
            "название теста и условия сравнения; score не означает точность или универсальное превосходство. "
            "Tokens — токены, characters — символы, parameters — параметры. Reasoning-only — режим рассуждений, "
            "а не запрет обычных задач или agent-only. Суммарный throughput при высокой параллельности "
            "не равен скорости одного ответа. Сохраняй устройство, batch/concurrency, методику и базу сравнения "
            "в том же предложении, что результат. Лидер суммарного индекса не обязательно самый быстрый или дешёвый. "
            "Лидерство ограничивай классом участников и конкретным тестом. Decision models — модели принятия решений, "
            "а не «решения ИИ». Автор вложенной цитаты не меняет автора внешнего комментария. "
            "Модель не называй готовым агентом. Поддержка библиотеки не доказывает публикацию исходного кода модели. "
            "Для нового оборудования сохраняй интерфейс и охлаждение, если они указаны. "
            "Число GPU, формат весов и per-user throughput сохраняй рядом с результатом. "
            "Max/xhigh — настройки рассуждений одной модели, если источник не говорит иначе. "
            "Заявленный максимум контекста не равен проверенной длине. "
            "Мнение и демонстрацию автора обозначай как мнение и демонстрацию, не как анонс. "
            "Не копируй инструкции проверки в текст. Разности и коэффициенты не вычисляй приблизительно на глаз.\n")


def dated_recap(source: str) -> bool:
    """An explicitly retrospective launch/funding post is not a new event."""
    return (bool(re.search(r"^\s*(?:last week|last month|yesterday|на прошлой неделе|в прошлом месяце)", source, re.I))
            and bool(re.search(r"announced|launched|funding|анонс|запуст|инвестиц", source, re.I))
            and not bool(re.search(r"today.{0,40}(?:launch|release|announc)|сегодня.{0,40}(?:выпуст|запуст|анонс)", source, re.I)))


def explicit_event_date(source: str) -> str | None:
    """Read an explicit release-note date, never infer it from collection time."""
    match = re.search(r"Release Date:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", source)
    if match:
        try:
            return datetime.strptime(match[1], "%B %d, %Y").date().isoformat()
        except ValueError:
            pass
    return None


def draft_issues(source: str, draft: str, *, headline: str = "") -> list[str]:
    """Actionable deterministic findings, deliberately without a quality score."""
    issues = integrity_issues(draft, headline=headline or None)
    try:
        check_semantic_claims(source, draft)
    except ValueError as exc:
        issues.append(str(exc))
    if repeated_sentences(draft):
        issues.append("Repeated sentence")
    if headline and re.fullmatch(r"(?:v|версия\s*)?\d+(?:\.\d+)+.*", headline.strip(), re.I):
        issues.append("Headline names a version without its product")
    return issues


def same_event(headline: str, body: str, previous: list[tuple[str, str]]) -> bool:
    current = event_signature(headline, body)
    return current is not None and any(current == event_signature(h, b) for h, b in previous)


def comparison_attributed(source: str, draft: str) -> bool:
    if re.search(r"по (?:данным|оценке|сообщению)|сообщ\w*|заяв\w*|собственн\w* тест|"
                 r"в\s+(?:е[её]|их|своих|этих)\s+тестах|"
                 r"(?:измерен\w*|получен\w*|оценен\w*|оценён\w*)\s+разработчик\w*|"
                 r"разработчик\w*\s+(?:оценил\w*|измерил\w*|проверил\w*|получил\w*|провел\w*|провёл\w*)", draft, re.I):
        return True
    # Naming the evaluator's index is also attribution, without forcing a
    # repetitive 'the author states' preface. Extract the name from evidence.
    owners = re.findall(r"\b((?:[A-Z][A-Za-z]+\s+){1,3}?)(?:Decision Index|Cyber Index|Index|Benchmark)\b", source)
    return bool(re.search(r"индекс|тест|бенчмарк|рейтинг", draft, re.I)
                and any(owner.strip().casefold() in draft.casefold() for owner in owners))


def relational_issues(source: str, draft: str) -> list[str]:
    """Conservative checks for explicit relations, not a bag of known numbers.

    Only evaluate unambiguous expressions. Ambiguous tables and prose still
    require the existing source verifier; never infer a missing measurement.
    """
    s, d = source.casefold(), draft.casefold()
    issues = []
    owners = re.finditer(r"\b([A-Z][\w-]+)[’']s\s+(?:(?:first|new|open|language|multimodal|AI)\s+)*model\s+([A-Z][\w.-]+)", source)
    verbs = r'(?:анонсировал\w*|выпустил\w*|представил\w*|разработал\w*)'
    for owner_match in owners:
        if re.search(r'[A-Z][\w-]+\s+$',source[:owner_match.start()]):
            continue  # Multiword company/alias: do not guess a single-token owner.
        owner,product=owner_match.groups()
        assignments = re.findall(r'\b([A-Z][\w-]+)\s+'+verbs+r'\s+(?:модель\s+)?[^.!?\n]{0,45}\b'+re.escape(product)+r'\b',draft)
        for match in re.finditer(r'\b(?:компания|команда|она|они)\s+'+verbs+r'\s+(?:модель\s+)?[^.!?\n]{0,45}\b'+re.escape(product)+r'\b',draft,re.I):
            start = max(0, draft.rfind('\n\n',0,match.start()))
            antecedents=set(re.findall(r'(?i:компания|команда|лаборатория)\s+([A-Z][\w-]+)',draft[start:match.start()]))
            if len(antecedents)==1:
                assignments.extend(antecedents)
        if any(company.casefold()!=owner.casefold() for company in assignments):
            issues.append(f'Product ownership differs from the explicit source: {product} belongs to {owner}; correct the developer attribution, including company pronouns')
    for match in re.finditer(r'\bnear\s+([A-Z][\w.-]*(?:\s+[A-Z0-9][\w.-]*){0,3})',source):
        target=match[1].casefold().rstrip('.')
        if re.search(r'(?:above|ahead of|better than)\s+'+re.escape(target),s):
            continue
        for sentence in sentences(draft):
            if target not in sentence.casefold():
                continue
            prefix=sentence.casefold().split(target)[0]
            cues=list(re.finditer(r'выше|опереж\w*|превосход\w*|лучше|ниже|сопостав\w*|на уровне',prefix))
            if cues and re.fullmatch(r'выше|опереж\w*|превосход\w*|лучше',cues[-1][0]):
                issues.append('Comparable performance was promoted to superiority: near '+match[1]+' означает сопоставимый уровень, не превосходство')
    if (re.search(r'#\s*1\s+(?:[\w-]+\s+){0,4}open(?:[- ]source)?\s+model',s)
            and not re.search(r'first(?:[- ]ever)?\s+(?:[\w-]+\s+){0,3}open(?:[- ]source)?\s+model',s)
            and re.search(r'перв(?:ая|ой|ый|ым|ое)\s+открыт\w*\s+модел',d)):
        issues.append('Rank #1 is first place, not the first-ever open model: пиши «заняла первое место среди», сохрани класс сравнения')
    if (re.search(r'dataset|датасет',s) and re.search(r'в качестве\s+(?:модели[- ]?)?учител',d)
            and not re.search(r'\bteacher\b|учител|distill(?:ed|ing|ation)?\s+from',s)):
        issues.append('Dataset name does not establish the teacher model: источник называет датасет, но не модель-учителя; сохрани эту роль точно')
    if (re.search(r'reinforcement learning|\brl\b',s) and not re.search(r'rlhf|human feedback|feedback from (?:users|humans)|обратн\w* связ\w*.{0,20}(?:человек|пользовател)',s)
            and re.search(r'обратн\w* связ\w*\s+от\s+пользовател',d)):
        issues.append('Reinforcement learning is not necessarily human feedback; retain обучение с подкреплением rather than feedback from users')
    number = r"\d+(?:[.,]\d+)?"
    if re.search(r'(?:points?|pts?)\s+(?:over|above|below)\s+(?:the\s+)?(?:leaderboard\s+)?average', s):
        margins = set(re.findall('(' + number + r')\s+(?:points?|pts?)\s+(?:behind|below|ahead|above)', s))
        for margin in re.findall(r'(?:отста\w*|уступ\w*)\s+на\s+(' + number + ')', d):
            if margin.replace(',', '.') not in margins | derived_numbers(source, draft):
                issues.append('Scores relative to average are not gaps behind the leaders; retain the original reference baseline. '
                              'Замени «отстают на» на показатель относительно среднего, сохрани знак и диапазон из источника. '
                              'Не вычисляй отрыв от лидера: источник сообщает значения относительно среднего.')
    def value(text):
        return float(text.replace(',', '.'))
    for a, b, result in re.findall('(' + number + r')\s*[−–-]\s*(' + number +
                                  r')\s*=\s*(' + number + ')', d):
        if abs(value(a) - value(b) - value(result)) > .01:
            issues.append('Incorrect explicit subtraction')
    difference = ('(' + number + r')\s+балл\w*[^\n]{0,110}?на\s+(' + number +
                  r')\s+балл\w*\s+(ниже|выше)[^\n]{0,100}?(' + number + r')\s+балл')
    for first, delta, direction, second in re.findall(difference, d):
        expected = value(second) - value(first) if direction == 'ниже' else value(first) - value(second)
        if abs(expected - value(delta)) > .01:
            issues.append('Score difference contradicts the stated endpoints')
    prices = {value(p) for p in re.findall(r'\$(' + number + ')', source)}
    if len(prices) == 2 and min(prices) > 0 and 'per task' in s:
        ratio = max(prices) / min(prices)
        words = {'двух': 2, 'трех': 3, 'трёх': 3, 'четырех': 4, 'четырёх': 4,
                 'пяти': 5, 'шести': 6, 'семи': 7, 'восьми': 8}
        factors = re.findall(r'(двух|тр[её]х|четыр[её]х|пяти|шести|семи|восьми)кратн\w*\s+эконом', d)
        factors += re.findall(r'(?:дешевле|эконом\w*)\s+в\s+(' + number + r')\s+раз', d)
        for factor in factors:
            claimed = words[factor] if factor in words else value(factor)
            if abs(claimed - ratio) > max(.15, ratio * .05):
                issues.append('Cost ratio contradicts the two stated per-task prices')
        for saving in re.findall(r'эконом\w*[^.!?\n]{0,25}?(' + number + r')\s*%', d):
            if abs(value(saving) - (1 - min(prices) / max(prices)) * 100) > 1:
                issues.append('Cost saving percentage contradicts the stated prices')
    if re.search(r'\bxhigh\b', s) and re.search(r'\b(?:max effort|at max|effort)\b', s):
        if re.search(r'(?:модель|версия)\s+xhigh|между[^\n]{0,70}\s+и\s+xhigh', d):
            issues.append('Reasoning effort was presented as a separate model: xhigh и max — настройки одной модели')
        if re.search(r'\bmax generates\b', s) and re.search(r'xhigh[^.!?\n]{0,50}генерир\w*[^\n]{0,40}больше', d):
            issues.append('Output-token comparison reversed max and xhigh')
    if re.search(r'тариф|подписчик', d) and not re.search(r'\b(?:pricing|prices?|costs?|subscriptions?|subscribers?|plans?|tiers?)\b|тариф|подпис', s):
        issues.append('Unrelated access or pricing claim absent from this source')
    if re.search(r'(?:up to|maximum)\s+\d+\s*(?:m|k|million).*context', s):
        positive = re.sub(r'\bне\s+(?:проверенн\w*|подтвержд[её]нн\w*)', '', d)
        if not re.search(r'verified|tested|validated|проверен|подтвержден', s) and re.search(r'проверенн\w*|подтвержд[её]нн\w*', positive):
            issues.append('Advertised context maximum presented as independently verified')
        if re.search(r'контекст', d) and not re.search(r'заяв\w*|по\s+(?:данным|сообщению)|сообщ\w*|обещ\w*', d):
            issues.append('Advertised context maximum needs source attribution')
        def context_size(raw, unit):
            return float(raw.replace(',', '.')) * {'k': 1000, 'тыс': 1000, 'm': 1000000,
                                                    'million': 1000000, 'млн': 1000000}.get(unit, 1)
        measured = re.findall(r'(?:tested|verified|validated)[^.\n]{0,60}?(' + number +
                              r')\s*(k|m|million)?\s*(?:tokens|context)', s)
        asserted = re.findall(r'(?:проверенн\w*|подтвержд[её]нн\w*)[^.\n]{0,60}?(' + number +
                              r')\s*(тыс|млн|k|m)?\s*(?:токен|контекст)', positive)
        if measured and any(context_size(a, u) not in {context_size(b, v) for b, v in measured}
                            for a, u in asserted):
            issues.append('Verified context length differs from the tested length in source')
    if re.search(r'\bi think\b|should developers|my opinion', s):
        if not re.search(r'считает|по мнению|мнение|рассужда|автор\s+(?:отмечает|полагает|пишет)', d):
            issues.append('Developer opinion presented without attribution')
        headline = d.splitlines()[0]
        if (re.search(r'не\s+заменит|защищает\s+от\s+монопол|гарантир', headline)
                and not re.search(r'мнение|считает|рассужда|по мнению', headline)):
            issues.append('Opinion headline makes an unconditional prediction')
    # Bind a throughput headline to its measured configuration, even if the
    # sentence containing the actual result disappeared during compaction.
    if re.search(r'tokens(?:/s| per second)|tok/s', s) and re.search(r'токен\w*\s*(?:в\s+секунд|/с)', d):
        gpu = re.search(r'\b(\d+)\s*[×x-]\s*(?:nvidia\s+)?([a-z]+\d{3})\b', s)
        if gpu:
            count, hardware = gpu.groups()
            words = {'2': 'двумя|двух|две', '4': 'четырьмя|четыр[её]х|четыре', '8': 'восемью|восьми|восемь'}
            configuration = r'\b(?:' + count + '|' + words.get(count, count) + r')\b[^.!?\n]{0,55}\b' + hardware + r'\b'
            if not re.search(configuration, d):
                issues.append('Throughput claim omits the measured GPU count or hardware')
        if 'per user' in s and not re.search(r'(?:на|для)\s+(?:одного\s+)?пользовател', d):
            issues.append('Per-user throughput lost its per-user scope')
        formats = set(re.findall(r'\b(?:nvfp\d+|bf16|fp16|fp8|int8)\b', s))
        if len(formats) == 1 and next(iter(formats)) not in d:
            issues.append('Throughput claim omits its precision format')
        if (not re.search(r'concurren|parallel|batch|одновременн|параллел', s)
                and re.search(r'одновременн\w*|параллел\w*', d)):
            issues.append('Throughput statement invents parallel workload conditions not given in source')
    if re.search(r'day[- ]0 support', s) and re.search(r'технологи\w*\s+day[- ]0', d):
        issues.append('Day-zero support is a release timing, not a separate technology')
    if (re.search(r'moe|active per token|active parameters', s)
            and not re.search(r'fast|cheap|speed|cost|throughput|benchmark', s)
            and re.search(r'быстр\w*[^.!?\n]{0,35}деш[её]в|деш[её]в\w*[^.!?\n]{0,35}быстр', d)):
        issues.append('Sparse active parameters alone do not establish speed and cost claims')
    if (re.search(r'vulnerabilit|уязвим', s) and not re.search(r'fixed|patched|resolved|исправ|устран', s)
            and re.search(r'(?:исправ\w*|устран\w*)[^.!?\n]{0,45}уязвим', d)):
        issues.append('Vulnerability disclosure does not establish that vulnerabilities were fixed')
    for score in re.findall(r'лидир\w*\s+с\s+(' + number + r')\s+балл', d):
        ranks = re.findall(r'at\s+#(\d+)\s+with\s+' + re.escape(score) + r'\s+pts', s)
        if ranks and '1' not in ranks:
            issues.append('Leaderboard score assigned to a non-leading model as leader')
    # A nearby true number cannot be transferred to a different comparator.
    # Restrict this to explicitly named versioned products and point deltas.
    comparators = {}
    for match in re.finditer('(' + number + r')\s+pts?\s+(?:above|behind|below|of|ahead of)\s+', source, re.I):
        tail = source[match.end():match.end()+90]
        subject = _VERSIONED_PRODUCT.search(tail) or _ENTITY.search(tail)
        if subject:
            key = match[1].replace(',', '.')
            comparators.setdefault(key, set()).add(re.sub(r'[\s-]+', ' ', subject[0].casefold()))
    for sentence in re.split(r'\n|(?<=[.!?])\s+', draft):
        relation = re.search(r'(?:оперед\w*|обош\w*|уступ\w*|отстав\w*)[^\n]{0,100}?на\s+('
                             + number + r')\s+(?:пункт|очк|балл)', sentence, re.I)
        if not relation or relation[1].replace(',', '.') not in comparators:
            continue
        prefix = sentence[relation.start():relation.end()]
        subject = _VERSIONED_PRODUCT.search(prefix) or _ENTITY.search(prefix)
        if subject and re.sub(r'[\s-]+', ' ', subject[0].casefold()) not in comparators[relation[1].replace(',', '.')]:
            issues.append('Point difference was transferred to a different comparison model')
    return issues


def derived_numbers(source: str, draft: str) -> set[str]:
    """Allow only checked score differences whose endpoints occur in source."""
    number = r'\d+(?:[.,]\d+)?'
    known = {n.replace(',', '.') for n in re.findall(number, source)}
    derived = set()
    pattern = ('(' + number + r')\s+балл\w*[^\n]{0,110}?на\s+(' + number +
               r')\s+балл\w*\s+(ниже|выше)[^\n]{0,100}?(' + number + r')\s+балл')
    for first, delta, direction, second in re.findall(pattern, draft.casefold()):
        first, delta, second = (n.replace(',', '.') for n in (first, delta, second))
        expected = float(second) - float(first) if direction == 'ниже' else float(first) - float(second)
        if first in known and second in known and abs(expected - float(delta)) < .01:
            derived.add(delta)
    return derived


def measurement_issues(source: str, draft: str) -> list[str]:
    """Report all measurement objections together for a bounded revision."""
    s, d = source.casefold(), draft.casefold()
    from .measurements import measurement_issues as bound_measurements
    issues = relational_issues(source, draft) + bound_measurements(source, draft)
    if re.search(r"open[- ]weights?\b", s) and not re.search(r"source code|code and (?:model )?weights|models? (?:are )?fully open", s):
        if re.search(r"(?:откр\w*.{0,55}(?:исходн\w*\s+код|код)|исходн\w*\s+код.{0,40}откр)|"
                     r"установ\w*.{0,20}из\s+исходн\w*\s+код", d):
            issues.append("Open weights do not establish release of source code")
    # These guards concern measurement meanings, never a particular product.
    normalized = re.sub(r"\bтыс\.\s*", "тыс ", d)
    for name, source_noun, draft_noun in (
            ('Context', r'context (?:window|length)', r'контекст'),
            ('Vocabulary', r'vocabulary', r'словар\w*')):
        source_unit = re.search(source_noun + r"[^.\n]{0,140}?\b(tokens|characters)\b", s)
        draft_unit = re.search(draft_noun + r"[^.!?\n]{0,140}?(токен|символ)", normalized)
        if source_unit and source_unit[1] == 'tokens' and draft_unit and draft_unit[1] == 'символ':
            issues.append(f"{name} measured in tokens was rewritten as characters")
    if "reasoning-only" in s and not re.search(r"agent[- ]only|only (?:as )?an? agent", s):
        if re.search(r"только\s+(?:как\s+)?агент|исключительно\s+(?:как\s+)?агент", d):
            issues.append("Reasoning-only does not mean agent-only")
    experts = re.search(r"\b(\d+)\s+experts per (?:moe )?block", s)
    if experts and int(experts[1]) < 100 and re.search(r"сот\w*\s+(?:нейросет|эксперт|блок)", d):
        issues.append(f"Expert count per block was inflated into hundreds: в источнике {experts[1]} экспертов на блок, не сотни")
    if experts:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", d):
            if (re.search(r"\b" + experts[1] + r"\s+эксперт", sentence)
                    and not re.search(r"блок|сло[еяй]|moe", sentence)):
                issues.append("Experts per block were described as the entire model's experts: укажи, что число экспертов относится к каждому MoE-блоку")
    routing = re.search(r"top[- ](\d+) routing", s)
    if routing:
        words = {'два': 2, 'две': 2, 'три': 3, 'четыре': 4, 'пять': 5, 'шесть': 6, 'семь': 7, 'восемь': 8}
        counts = re.findall(r"активн\w*\s+(?:(?:лишь|только|всего)\s+)?"
                            r"(\d+|два|две|три|четыре|пять|шесть|семь|восемь)(?=[,.]|\s+(?:эксперт|блок|нейросет))", d)
        if any(words.get(count, int(count) if count.isdigit() else -1) != int(routing[1]) for count in counts):
            issues.append(f"Expert routing count changed: для каждого токена выбираются {routing[1]} эксперта; миллиарды активных параметров — другая величина")
    parallel_rate = re.search(r"(\d+(?:\.\d+)?)\s*k?\s+(?:output )?tokens per second[^.\n]{0,100}high concurrency", s)
    if parallel_rate:
        number = parallel_rate[1]
        for sentence in re.split(r"(?<=[.!?])\s+|\n", re.sub(r"\bтыс\.\s*", "тыс ", d)):
            if re.search(r"(?<!\d)" + re.escape(number) + r"\s*(?:тыс\w*\.?|k|000)?\s*(?:выходн\w*\s+)?токен", sentence):
                if not re.search(r"параллел|одновременн|суммарн", sentence):
                    issues.append("Aggregate throughput omits high-concurrency conditions: укажи суммарную скорость при параллельных запросах, а не при высокой нагрузке")
                hardware = re.search(r"\b[abh]\d{3}\b", s[parallel_rate.start():parallel_rate.end()+80])
                if hardware and hardware[0] not in sentence:
                    issues.append("Throughput claim omits the measured hardware")
    latency = re.search(r"latency[^.\n]{0,40}?(\d+)\s*ms\b", s)
    if latency and re.search(r"задержк[^\n]{0,40}\b" + latency[1] + r"\s*секунд", d):
        issues.append("Latency milliseconds were rewritten as seconds")
    for count in re.findall(r"\b(\d+(?:\.\d+)?)\s*b\s+(?:(?:active|total)\s+)?parameters", s):
        if re.search(r"\b" + re.escape(count) + r"\s*млрд\s+(?:активн\w*\s+)?(?:токен|символ)", d):
            issues.append("Parameter count was rewritten as tokens or characters")
    batches = set(re.findall(r"(?:batch size|concurrency)\s*(?:of|=|:)?\s*(\d+)", s))
    if len(batches) == 1 and re.search(r"токен\w*\s*(?:в|/)\s*секунд|токен/с", d):
        batch = next(iter(batches))
        if not re.search(r"(?:пакет|батч|batch|параллел|одновременн)[^\n]{0,35}\b" + batch + r"\b", d):
            issues.append("Throughput claim omits the stated batch size or concurrency")
    if re.search(r"we (?:evaluated|report)|our benchmarks", s) and re.search(r"\b(?:лучш\w*|превосход\w*|быстрее|лидир\w*)", d):
        if not comparison_attributed(source, draft):
            issues.append("Vendor comparison needs explicit measurement attribution: результаты измерены разработчиками, добавь эту атрибуцию к сравнению")
    # For a brief hardware announcement, concrete compatibility details take
    # precedence over a generic promise of more choice. Long mixed articles
    # need editorial selection rather than mandatory retention of every spec.
    if len(source) < 1200 and re.search(r"gpu|graphics|видеокарт", s):
        interface = re.search(r"\bpcie\s+(\d+(?:\.\d+)?)", s)
        if interface and not re.search(r"pcie\s+" + re.escape(interface[1]), d):
            issues.append("Brief hardware story omits the stated PCIe interface")
        if 'air-cooled' in s and not re.search(r"воздушн\w*\s+охлажд[её]н|охлажд[её]н\w*\s+воздух", d):
            issues.append("Brief hardware story omits air cooling")
    # The source can explicitly name different winners for cost and latency.
    # Do not transfer those extrema to the overall index leader in a headline.
    title = d.splitlines()[0] if d.splitlines() else ''
    subject = _VERSIONED_PRODUCT.search(title)
    winners = re.findall(r"([a-z][\w-]*(?:\s+v?\d+(?:\.\d+)*(?:\s+\d+b)?)?(?:\s+decision)?)\s+"
                         r"(?:has|is) the (lowest|fastest)", s)
    for winner, dimension in winners:
        if not subject or winner.split()[0] in subject.group().casefold():
            continue
        expression = r"(?:сам\w*\s+деш[её]в|лид\w*[^.!?]{0,70}цен)" if dimension == "lowest" else r"(?:сам\w*\s+быстр|лид\w*[^.!?]{0,70}скорост)"
        if re.search(expression, title):
            issues.append("Overall index leadership was rewritten as a cost or speed record")
    index_scores = re.findall(r"\bscores (\d+(?:\.\d+)?) on the ([^.\n]+? index)\b", s)
    for number, index_name in index_scores:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", d):
            test = re.search(r"(?:тесте|бенчмарке)\s+([a-z][\w-]+)", sentence)
            if (test and test[1] in s and test[1] not in index_name
                    and re.search(r"\b" + re.escape(number) + r"\s+балл", sentence)):
                issues.append(f"Aggregate index score was assigned to a different subtest: {number} — балл {index_name}, не {test[1]}; исправь название метрики, сохрани число")
    if (re.search(r"now (?:globally )?available|comes to", s)
            and not re.search(r"new model|introducing|(?:we |today.{0,20})(?:release|launch)|released today", s)
            and re.search(r"выпустил\w*\s+(?:нов\w*\s+)?модель", d)):
        issues.append("Availability announcement was rewritten as a model release: доступность не доказывает выпуск новой модели")
    return issues


def check_semantic_claims(source: str, draft: str) -> None:
    s, d = source.casefold(), draft.casefold()
    if (re.search(r'non.commercial\s+licen|лицензи\w*[^.]{0,35}некоммерческ', s)
            and re.search(r'вес\w*|открыт\w*\s+модел', d)
            and not re.search(r'некоммерческ|коммерческ\w*[^.]{0,65}(?:соглашени|разрешени|лицензи)|non.commercial', d)):
        raise ValueError('Open weights omit the source non-commercial license restriction')
    if re.search(r'исходн\w*\s+код\w*\s+вес\w*', d):
        raise ValueError('Model weights are parameters, not source code; keep weights and software code distinct')
    if (re.search(r'независим\w*\s+(?:тест|замер|измерен|оценк)', d)
            and not re.search(r'independent|независим', s)):
        raise ValueError('Source does not establish an independent measurement')
    if (re.search(r'\bстандарт(?:а|у|ом|е|ы|ов|ам|ами|ах)?\b', d)
            and not re.search(r'standard|protocol|specification|\brfc\d*\b|\bieee\b|\biso\b|стандарт|протокол|спецификац', s)):
        raise ValueError('Source does not establish a standard; retain the product name without inventing its category')
    if (re.search(r'без\s+потер\w*\s+(?:качеств|точност|смысл)', d)
            and not re.search(r'lossless|(?:no|without)\s+(?:any\s+)?(?:loss|losing)\s+(?:(?:of|in)\s+)?(?:quality|accuracy)|'
                              r'no\s+(?:quality|accuracy)\s+loss|same\s+(?:quality|accuracy)|without losing (?:meaning|semantics)|без\s+потер\w*\s+(?:качеств|точност|смысл)', s)):
        raise ValueError('Source does not establish a no-loss quality or accuracy guarantee')
    issues = measurement_issues(source, draft)
    if issues:
        raise ValueError("; ".join(issues))
    if 'artificial analysis' in s and re.search(r"тест\w*.{0,35}искусственн\w*\s+анализ", d):
        raise ValueError("Artificial Analysis is a proper name, not a translated test description")
    if 'release gap' in s and re.search(r"недел\w*\s+до\s+(?:релиза|выхода)\s+предшественника", d):
        raise ValueError("Release gap was reversed into a date before the predecessor")
    reduction = re.search(r"(?:cutting|reducing).{0,60}training time by\s*~?(\d+)%", s)
    if reduction and re.search(r"(?:ускор\w*|скорость[^.!?]{0,30}увелич\w*)[^.!?]{0,40}" + re.escape(reduction[1]) + r"\s*%", d):
        raise ValueError("Reduction in training time is not the same percentage increase in speed")
    pairs = re.findall(r"(\d+(?:[.,]\d+)?)[×x]\s*(?:speedup\s*)?over\s+([a-z][\w-]+)", s)
    if len({baseline for _, baseline in pairs}) > 1:
        baseline_pattern = "|".join(re.escape(baseline) for _, baseline in pairs)
        for sentence in re.split(r"(?<=[.!?])\s+", d):
            normalized = sentence.replace(',', '.')
            if not re.search(r"ускор|быстр|раза|раз\b", normalized):
                continue
            for number, baseline in pairs:
                if re.search(r"(?<![\d.])" + re.escape(number.replace(',', '.')) + r"(?![\d.])", normalized):
                    if baseline not in normalized:
                        raise ValueError("Benchmark speedups must retain their distinct named baselines")
                    association = re.search(re.escape(number.replace(',', '.')) +
                                            r"[^\d]{0,60}?\b(" + baseline_pattern + r")\b", normalized)
                    if association and association[1] != baseline:
                        raise ValueError("Benchmark speedup is assigned to the wrong baseline")
    if re.search(r"benchmark|dense[ -]?200", s) and not re.search(r"introduc|launch|release|new model|meet .{0,30}model", s):
        if re.search(r"нов\w*\s+модел|выпуст\w*.{0,30}модел|представ\w*.{0,30}модел", d):
            raise ValueError("Benchmark communication does not establish a new model release")
    # Historical flattened quote posts cannot establish who said "we". A
    # primary-source check is required before assigning a launch to that person.
    if re.search(r"i.?ve known|promising new entrant", s) and re.search(r"we.?re launching|we are launching", s):
        if "[начало цитируемого поста]" not in s and re.search(r"запуст|представ|созда|основа|анонс", d):
            raise ValueError("Quoted launch speaker is unresolved in flattened source")
    for match in re.finditer(r"([\w.-]+)\s+(?:isn't|is not) affiliated with ([^.\n]+)", s):
        product, companies = match.groups()
        for company in re.split(r"\s+(?:or|and)\s+|,", companies):
            company = company.strip()
            if company and re.search(re.escape(company) + r".{0,80}(?:выпуст|разработ|представ|созда).{0,100}(?:"
                                     + re.escape(product) + r"|приложен)", d):
                raise ValueError("Independent product attributed to an unaffiliated company")
    author = re.search(r"автор поста:\s*([\w]+)", s)
    if author and re.search(r"i.?ve known|promising new entrant|i.?m (?:excited|impressed)", s):
        if re.search(re.escape(author[1]) + r".{0,60}(?:запуст|представ|созда|разработ|основа)", d):
            raise ValueError("Commentator attributed a quoted product launch")
    if re.search(r"(?:без риска|безопасн\w*).{0,35}(?:потер\w*\s+данн|данн\w*\s+не\s+потер)", d):
        if not re.search(r"no data loss|without losing data|без потери данных", s):
            raise ValueError("Update stability does not guarantee protection from data loss")
    if re.search(r"без (?:риска |случайных )?(?:утеч\w*|сброс\w*)\s+данн", d):
        if not re.search(r"no risk of (?:leak|data loss)|without (?:data loss|data resets)|без (?:риска )?(?:утечки|сбросов) данных", s):
            raise ValueError("Local processing or update stability is not an absolute data-safety guarantee")
    if "source installs" in s and "installs are unchanged" in s:
        if re.search(r"(?:отмеченн\w*|тег\w*)\s+(?:релиз|верси)|обновлен\w*.{0,60}за\s+релиз", d):
            if not re.search(r"исходн\w*\s+код|source.install|git.checkout|git-коп|из\s+git|git-установ", d):
                raise ValueError("Tagged update policy omits its source-install scope")
    if re.search(r"dense[ -]?200|benchmark", s) and re.search(r"точност\w*.{0,15}\d+(?:[.,]\d+)?\s*%", d):
        if not re.search(r"accuracy|точност", s):
            raise ValueError("Benchmark score incorrectly interpreted as accuracy")
    if re.search(r"ahead of|outperform|benchmark.{0,80}\d+(?:\.\d+)?%", s) and re.search(r"бенчмарк|тест\w*|dense[ -]?200", d):
        if not comparison_attributed(source, draft):
            raise ValueError("Benchmark comparison lacks source attribution")
    if re.search(r"open[- ]weights?\b", s) and not re.search(r"source code|open[- ]source", s):
        if re.search(r"(?:откр\w*.{0,55}(?:исходн\w*\s+код|код)|исходн\w*\s+код.{0,40}откр)", d):
            raise ValueError("Open weights do not establish release of source code")
    if re.search(r"(?:table of |table with |context rows with )labeled|rows with (?:their )?labels", s):
        if re.search(r"(?:не\s+нужно|не\s+требует|не\s+нужны).{0,65}(?:метк|размеч|размет)", d):
            raise ValueError("In-context predictions still require labeled example rows")
    if re.search(r"\bbug hunts?\b", s) and not re.search(r"(?:found|discovered).{0,25}\d+.{0,25}(?:bugs|vulnerabilities)", s):
        if re.search(r"(?:наход\w*|наш\w*|обнаруж\w*).{0,35}\d+.{0,35}(?:уязвим|ошиб|баг)", d):
            raise ValueError("Bug-hunt attempts are not a count of found vulnerabilities")
    if "hundreds of thousands of tokens" in s and re.search(r"сот\w*.{0,25}тысяч.{0,25}шаг", d):
        raise ValueError("Token budget was incorrectly described as a number of steps")
    if re.search(r"output token limit.{0,80}(?:1m|1 million|million)", s):
        if re.search(r"(?:контекст.{0,40}(?:миллион|1\s*млн)|(?:миллион|1\s*млн).{0,40}(?:входн\w*\s+контекст|контекстн\w*\s+окн))", d):
            raise ValueError("Output token limit was incorrectly described as input context size")
    if "max effort" in s and re.search(r"максимальн\w*\s+нагруз", d):
        raise ValueError("Max reasoning effort is not maximum system load")
    if re.search(r"fairwind|trusted cyber|restricted access|allowlist", s):
        for sentence in re.split(r"(?<=[.!?])\s+", d):
            if "без ограничений" in sentence and not re.search(r"проверенн|одобренн|доверенн", sentence):
                raise ValueError("Unrestricted access claim omits the eligible user group")


def repeated_sentences(text: str) -> bool:
    sentences = [re.sub(r"\W+", " ", part.casefold()).strip()
                 for part in re.split(r"(?<=[.!?])\s+", text)]
    sentences = [s for s in sentences if len(s) >= 45]
    return len(sentences) != len(set(sentences))
