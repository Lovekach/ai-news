"""Build one fact-checked Telegram post with detail scaled to the news count."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from .pipeline import canonical_title, duplicate_story, duplicate_title, recent_enough
from .store import Store
from .quality import freshness_hours, same_event
from .evidence import sentences

AD_TITLE = re.compile(r"\b(?:sponsored|advertisement|promo\s*code|subscribe|реклам\w*|промокод\w*|скидк\w*|подпишитесь)\b", re.I)
NEWS_SEPARATOR = "\n\n\n\n"
LABELS = {
    "Что произошло: ": "what",
    "Простыми словами: ": "simple",
    "Зачем это нужно: ": "why",
    "Что важно знать: ": "caveat",
}


def due_slot(now: datetime, *, grace_minutes: int = 1, interval_hours: int = 1,
             allow_catchup: bool = False) -> tuple[str, str] | None:
    """Return the completed local publication block and its exclusive UTC cutoff."""
    if interval_hours < 1 or 24 % interval_hours:
        raise ValueError("Digest interval must divide 24 hours")
    local = now if now.tzinfo is not None else now.astimezone()
    if (not allow_catchup and local.hour % interval_hours) or (local.hour % interval_hours == 0 and local.minute < grace_minutes):
        return None
    end = local.replace(minute=0, second=0, microsecond=0)
    if allow_catchup:
        end -= timedelta(hours=local.hour % interval_hours)
    start = end - timedelta(hours=interval_hours)
    return start.strftime("%Y-%m-%dT%H%z"), end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def previous_hour_start(cutoff_utc: str) -> str:
    cutoff = datetime.strptime(cutoff_utc, "%Y-%m-%d %H:%M:%S")
    return (cutoff - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def lookback_start(cutoff_utc: str, hours: int) -> str:
    if not 1 <= hours <= 24:
        raise ValueError("Digest lookback must be between 1 and 24 hours")
    cutoff = datetime.strptime(cutoff_utc, "%Y-%m-%d %H:%M:%S")
    return (cutoff - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def published_in_window(value: str, start_utc: str, cutoff_utc: str) -> bool:
    try:
        try:
            published = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        start = datetime.strptime(start_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        end = datetime.strptime(cutoff_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return start <= published.astimezone(timezone.utc) < end
    except (TypeError, ValueError, AttributeError):
        return False


def parse_draft(text: str) -> dict[str, str]:
    parts = text.split("\n\n")
    if len(parts) < 2 or not parts[0].startswith("🧠 "):
        raise ValueError("Invalid approved draft format")
    fields = {"headline": parts[0][2:].strip()}
    for part in parts[1:]:
        for label, key in LABELS.items():
            if part.startswith(label):
                fields[key] = part[len(label):].strip()
                break
    if not all(fields.get(key) for key in ("headline", "what")):
        raise ValueError("Approved draft is missing a field")
    return fields


def _sentences(value: str) -> list[str]:
    return sentences(value)


def card(fields: dict[str, str], max_chars: int | None = None, *, detail_first: bool = False) -> str:
    sections = {key: _sentences(fields.get(key, "")) for key in ("what", "simple", "why", "caveat")}
    if sections["simple"] and difflib.SequenceMatcher(
        None, canonical_title(fields["what"]), canonical_title(fields["simple"])
    ).ratio() >= 0.75:
        sections["simple"] = []
    if re.search(r"reasoning-only.{0,100}(?:перед|до).{0,30}ответ", fields['what'], re.I):
        sections['simple'] = [sentence for sentence in sections['simple']
                              if not (re.search(r"^Режим reasoning-only означает.{0,160}(?:перед|до).{0,30}ответ", sentence, re.I)
                                      and not re.search(r"\d", sentence))]

    def render(chosen: dict[str, list[str]]) -> str:
        # Selection favors details; rendering preserves their original order.
        main = " ".join(sentence for sentence in sections["what"] if sentence in chosen["what"])
        explanation = " ".join(" ".join(chosen[key]) for key in ("simple", "why", "caveat") if chosen[key])
        paragraphs = ["  " + main] if main else []
        if explanation:
            if main and len(main) + len(explanation) < 700:
                paragraphs[0] += " " + explanation
            else:
                paragraphs.append("  " + explanation)
        return f"- {fields['headline']}\n\n" + "\n\n".join(paragraphs)

    if max_chars is None:
        return render(sections)
    selected = {key: [] for key in sections}
    if not sections["what"]:
        return ""
    selected["what"].append(sections["what"][0])
    # Conditions must survive shortening; omit the item if they do not fit.
    important = re.compile(r"(?i)\b(?:только|ограничен\w*|предварительн\w*|тестов\w*|"
                           r"параллел\w*|суммарн\w*|одновременн\w*|токен\w*\s*(?:в\s+секунд\w*|/с)|"
                           r"GPU|NVFP\d+|BF16|FP16|FP8|INT8|"
                           r"платн\w*\s+тариф\w*|подписчик\w*|"
                           r"размеченн\w*|не\s+означает|по\s+(?:оценке|данным|сообщению)|"
                           r"сообщ\w*|заяв\w*|в\s+(?:их|этих)\s+тестах)\b")
    for sentence in sections["what"][1:]:
        if important.search(sentence):
            selected["what"].append(sentence)
    selected["caveat"] = sections["caveat"][:]
    # A measured result and its comparison conditions are information, even
    # when the small writer incorrectly put them in an explanatory field.
    quantified = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|процент\w*|раза\b|балл\w*|секунд\w*)", re.I)
    for key in ("simple", "why"):
        selected[key] = [sentence for sentence in sections[key] if quantified.search(sentence) or important.search(sentence)]
    if len(render(selected)) > max_chars:
        return ""
    if detail_first:
        # Daily editions spend scarce space on concrete event details before
        # generic explanations. Conditions and all caveats are already kept.
        technical = re.compile(r"\d|PCIe|охлажден|охлаждён|интерфейс|режим|рассужден", re.I)
        indices = sorted(range(1, len(sections["what"])),
                         key=lambda index: not bool(technical.search(sections["what"][index])))
        order = [("what", index) for index in indices]
        order += [(key, index) for key in ("simple", "why", "caveat") for index in range(len(sections[key]))]
    else:
        order = [(key, 0) for key in ("caveat", "simple", "why")]
        order += [(key, index) for key in ("what", "simple", "why", "caveat")
                  for index in range(1, len(sections[key]))]
    for key, index in order:
        if index >= len(sections[key]):
            continue
        if sections[key][index] in selected[key]:
            continue
        selected[key].append(sections[key][index])
        if len(render(selected)) > max_chars:
            selected[key].pop()
    return render(selected)


def render_sent_digest(store: Store, slot: str) -> str:
    row = store.digest(slot)
    if row is None:
        raise ValueError("Digest has no saved items")
    return str(row["text"])


def compose(
    config: dict[str, Any], store: Store, cutoff_utc: str, *, window_start_utc: str | None = None,
) -> tuple[str, list[str], list[tuple[str, str]]]:
    """Return post, selected URLs, and rejected URLs with a reason."""
    sources = {source["name"]: source for source in config["sources"]}
    rows = store.ready_before(cutoff_utc)
    discarded: list[tuple[str, str]] = []
    if window_start_utc is not None:
        def in_source_window(row: Any) -> bool:
            source = sources.get(row["source"], {})
            start = window_start_utc
            if source.get("type") not in {"telegram", "x"} and "official_catchup_hours" in config:
                start = lookback_start(cutoff_utc, freshness_hours(config, source))
            return published_in_window(row["published"], start, cutoff_utc)
        discarded.extend(
            (row["url"], "Outside the digest publication window")
            for row in rows
            if sources.get(row["source"], {}).get("auto_publish") and
            not in_source_window(row)
        )
        rows = [row for row in rows if in_source_window(row)]
    allowed = [row for row in rows if sources.get(row["source"], {}).get("auto_publish")]
    def score(row: Any) -> tuple[int, str]:
        title = row["title"].casefold()
        priority = sum(word in title for word in ("release", "model", "agent", "launch", "introduc", "релиз", "модел", "агент"))
        return priority, row["created_at"]
    allowed.sort(key=score, reverse=True)
    max_items = int(config.get("max_digest_items", 0))
    max_chars = min(int(config.get("max_digest_chars", 3900)), 4000)
    chosen: list[tuple[str, str, dict[str, str]]] = []
    titles = store.recent_sent_titles()
    headlines: list[str] = []
    events: list[tuple[str, str]] = []
    for previous_draft in store.recent_sent_drafts():
        try:
            previous = parse_draft(previous_draft)
            headlines.append(previous["headline"])
            events.append((previous["headline"], previous["what"]))
        except ValueError:
            continue
    for row in allowed:
        url = row["url"]
        source = sources[row["source"]]
        freshness = int(source.get("freshness_minutes", config.get("freshness_minutes", 1440)))
        freshness = freshness_hours(config, source) * 60
        if not recent_enough(row["published"], minutes=freshness):
            discarded.append((url, "Expired before hourly digest"))
            continue
        if AD_TITLE.search(row["title"]):
            discarded.append((url, "Promotional title"))
            continue
        try:
            fields = parse_draft(row["draft"] or "")
        except ValueError:
            discarded.append((url, "Invalid approved draft"))
            continue
        if (duplicate_title(row["title"], titles) or duplicate_story(fields["headline"], headlines)
                or same_event(fields["headline"], fields["what"], events)):
            discarded.append((url, "Duplicate story in digest or recent publication"))
            continue
        if max_items > 0 and len(chosen) >= max_items:
            discarded.append((url, "Lower priority than selected hourly news"))
            continue
        chosen.append((url, row["title"], fields))
        titles.append(row["title"])
        headlines.append(fields["headline"])
        events.append((fields["headline"], fields["what"]))
    while chosen:
        available = max_chars - len(NEWS_SEPARATOR) * (len(chosen) - 1)
        full_lengths = [len(card(fields)) for _, _, fields in chosen]
        budgets = [min(length, available // len(chosen)) for length in full_lengths]
        remaining = available - sum(budgets)
        while remaining > 0:
            needy = [index for index, length in enumerate(full_lengths) if budgets[index] < length]
            if not needy:
                break
            share = max(1, remaining // len(needy))
            for index in needy:
                added = min(share, remaining, full_lengths[index] - budgets[index])
                budgets[index] += added
                remaining -= added
                if remaining == 0:
                    break
        cards = [card(fields, budget) for (_, _, fields), budget in zip(chosen, budgets)]
        empty = next((index for index, item in enumerate(cards) if not item), None)
        if empty is not None:
            removed = chosen.pop(empty)
            if not chosen:
                discarded.append((removed[0], "Cannot fit a complete news sentence"))
            continue
        body = NEWS_SEPARATOR.join(cards)
        if len(body) <= max_chars:
            return body, [url for url, _, _ in chosen], discarded
        chosen.pop()  # Keep overflow ready for the next three-hour digest.
    return "", [], discarded
