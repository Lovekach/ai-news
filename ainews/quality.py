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
    r"Gemini\s+\d+(?:\.\d+)*(?:\s+Argon)?|Qwen\d+(?:\.\d+)*(?:-\d+B)?|"
    r"Mistral\s+(?:Large|Medium|Small)\s+\d+(?:\.\d+)*|"
    r"DeepSeek[ -]?(?:V|R)\d+(?:\.\d+)*|GLM[ -]?\d+(?:\.\d+)*|MiniMax[ -]?M\d+(?:\.\d+)*|"
    r"Ideogram\s+\d+(?:\.\d+)*|SynthID\s+Bio|ProvenanceGuard|Kumo\s+Tabular|"
    r"Context\s+Language\s+Models|Ember-\d+|Holo\d+(?:-\d+B(?:-A\d+B)?)?|"
    r"Hermes(?:\s+Agent)?|DigUp|NeatLogs|Le\s+Chonk)\b", re.I)


def event_signature(headline: str, body: str) -> tuple[str, str, str] | None:
    """Use the main subject and event type, not competitor names in the body."""
    match = _ENTITY.search(headline) or _ENTITY.search(body)
    if not match:
        return None
    entity = re.sub(r"[\s-]+", " ", match.group().casefold())
    # The headline identifies the event. The body may mention unrelated tests
    # or competing models, which must not turn every item into a pricing event.
    title = headline.casefold()
    text = title + " " + body.casefold()
    if re.search(r"уязвим|кибер|bug hunt|cybergym", title):
        focus = "cyber"
    elif re.search(r"цен|стоим|дешев|дешёв|эконом|выгод|cost|price", title):
        focus = "pricing"
    elif re.search(r"бенчмарк|benchmark|dense.?200|grounding", title):
        focus = "benchmark"
    elif re.search(r"рейтинг|занял|заняла|место|arena|leaderboard", title):
        focus = "ranking"
    elif re.search(r"доступ|платформ|api|вес\w*\s+откры|available", title):
        focus = "availability"
    elif re.search(r"исправ|ошибк|patch|fix", title):
        focus = "fix"
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
    return entity, focus, provider


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
    return (f"\nURL первоисточника: {config.get('_source_url', 'не указан')}"
            f"\nАккаунт сообщения (не обязательно разработчик): {config.get('_source_author', 'не установлен')}"
            f"\nДата публикации сообщения: {config.get('_source_published', 'не установлена')}"
            f"\nДата публикации материала: {config.get('_original_published') or 'не установлена'}"
            "\nДата обнаружения не доказывает дату события. Не называй старый продукт новым релизом "
            "по сегодняшнему репосту. Если дата события неизвестна, не выдумывай её. "
            "Автор комментария, автор цитаты, разработчик модели и разработчик приложения — разные роли. "
            "Не объявляй комментатора основателем или инвестором без прямого подтверждения. "
            "В заголовке называй конкретный продукт, не только номер версии. "
            "Вендорский benchmark — заявление автора: сохраняй атрибуцию, метрику, единицы, "
            "название теста и условия сравнения; score не означает точность или универсальное превосходство.\n")


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


def check_semantic_claims(source: str, draft: str) -> None:
    s, d = source.casefold(), draft.casefold()
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
        if not re.search(r"по (?:данным|оценке|сообщению)|сообщ\w*|заяв\w*|собственн\w* тест", d):
            raise ValueError("Benchmark comparison lacks source attribution")
    if re.search(r"open[- ]weights", s) and not re.search(r"source code|open[- ]source", s):
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
