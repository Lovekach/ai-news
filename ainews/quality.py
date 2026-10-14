"""Checks for semantic mistakes found in the published-news audit."""
import re
from datetime import datetime


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
    elif re.search(r"доступ|платформ|api|вес\w*\s+откры|available|comes to|"
                   r"(?:добавлен\w*|откр\w*).{0,60}(?:прилож|разработчик)|в\s+приложение", title):
        focus = "availability"
    else:
        focus = "announcement"
    provider = ""
    if focus == "availability":
        provider = next((name for name in ("nebius", "arena", "bedrock", "ollama", "hugging face")
                         if name in text), "")
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
    parts = [head]
    risky = re.compile(r"not affiliated|isn't affiliated|founder|developed by|built by|"
                       r"release date|published|only|unchanged|forks|mirrors|\d+(?:\.\d+)?%", re.I)
    budget = limit - len(head) - len(tail) - 120
    for match in risky.finditer(text, len(head), len(text) - len(tail)):
        excerpt = text[max(len(head), match.start() - 100):min(len(text), match.end() + 220)]
        if len(excerpt) <= budget and excerpt not in " ".join(parts):
            parts.append(excerpt)
            budget -= len(excerpt) + 24
    parts.append(tail)
    return "\n[Пропуск текста]\n".join(parts)[:limit]


def editorial_context(config: dict) -> str:
    """Provenance is not authorship; dates describe their actual meaning."""
    provenance = (f"\nURL первоисточника: {config.get('_source_url', 'не указан')}"
            f"\nАккаунт сообщения (не обязательно разработчик): {config.get('_source_author', 'не установлен')}"
            f"\nДата публикации сообщения: {config.get('_source_published', 'не установлена')}"
            f"\nДата публикации материала: {config.get('_original_published') or 'не установлена'}"
            f"\nКалендарная дата выпуска (МСК): {config.get('_edition_date') or 'не указана'}")
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
            "Для нового оборудования сохраняй интерфейс и охлаждение, если они указаны.\n")


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
    issues = []
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


def measurement_issues(source: str, draft: str) -> list[str]:
    """Report all measurement objections together for a bounded revision."""
    s, d = source.casefold(), draft.casefold()
    issues = []
    if re.search(r"open[- ]weights?\b", s) and not re.search(r"source code|open[- ]source", s):
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
    title = d.splitlines()[0]
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
