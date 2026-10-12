"""Checks for semantic mistakes found in the published-news audit."""
import re


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
    r"Context\s+Language\s+Models|Ember-\d+|Holo\d+(?:-\d+B(?:-A\d+B)?)?)\b", re.I)


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
    return entity, focus, provider


def same_event(headline: str, body: str, previous: list[tuple[str, str]]) -> bool:
    current = event_signature(headline, body)
    return current is not None and any(current == event_signature(h, b) for h, b in previous)


def check_semantic_claims(source: str, draft: str) -> None:
    s, d = source.casefold(), draft.casefold()
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
