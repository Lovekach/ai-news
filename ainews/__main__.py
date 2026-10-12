from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

from .lock import single_run
from .digest import compose, due_slot, lookback_start
from .pipeline import collect, prepare, verify_draft
from .store import Store
from .security import safe_error
from .telegram import call, check_channel_access, edit_message, find_channel, read_token, send_message

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DB_PATH = ROOT / ".state" / "news.sqlite3"
WATCHLIST_PATH = ROOT / "watchlist.json"


def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    watchlist = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    for url in watchlist["telegram"]:
        handle = url.rstrip("/").rsplit("/", 1)[-1]
        config["sources"].append({
            "name": f"Telegram @{handle}",
            "type": "telegram",
            "handle": handle,
            "freshness_minutes": 360,
            "auto_publish": True,
            "content_from_feed": True,
            "primary_account": handle.casefold() == "sberaiscience",
            "hosts": ["t.me"],
        })
    for group, urls in watchlist["x"].items():
        for url in urls:
            handle = url.rstrip("/").rsplit("/", 1)[-1]
            config["sources"].append({
                "name": f"X @{handle}", "type": "x", "handle": handle,
                "poll_seconds": 60, "freshness_minutes": 360,
                "auto_publish": True, "content_from_feed": True,
                "primary_account": group != "research_and_comparisons",
                "hosts": ["x.com", "twitter.com"],
            })
    return config


def save_config(config: dict) -> None:
    saved = {**config, "sources": [s for s in config["sources"] if s.get("type") not in {"telegram", "x"}]}
    CONFIG_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish_digest(config: dict, store: Store, *, now: datetime | None = None) -> list[str]:
    if config.get("publication_mode") == "daily":
        from .daily import publish_daily
        return publish_daily(config, store, ROOT, now=now, token_reader=read_token, sender=send_message)
    if not config["auto_publish"] or not config["channel_id"]:
        return ["Автопубликация отключена; материалы остаются в очереди."]
    current = now or datetime.now().astimezone()
    interval = int(config.get("digest_interval_hours", 1))
    upcoming = due_slot(current, grace_minutes=0, interval_hours=interval, allow_catchup=True)
    if upcoming is None:
        return []
    delay = store.digest_delay(upcoming[0])
    slot_info = due_slot(current, grace_minutes=delay, interval_hours=interval, allow_catchup=True)
    if slot_info is None:
        return []
    slot, cutoff_utc = slot_info
    if store.digest(slot):
        return []
    if store.digest_posts_today() >= int(config.get("max_posts_per_day", 24)):
        return ["Достигнут дневной лимит дайджестов."]
    body, urls, discarded = compose(
        config, store, cutoff_utc,
        window_start_utc=lookback_start(cutoff_utc, int(config.get("digest_lookback_hours", 1))),
    )
    if not urls:
        for url, reason in discarded:
            store.set_state(url, "skipped", error=reason)
        return []
    try:
        token = read_token()
    except Exception as exc:
        # No Telegram request has been made. Keep the drafts ready for retry.
        return [f"Отправка ещё не началась: не удалось прочитать токен ({type(exc).__name__})."]
    if not store.reserve_digest(slot, body, urls, discarded):
        return []
    try:
        message_id = send_message(token, int(config["channel_id"]), body)
    except Exception as exc:
        # The message might have arrived even when Telegram's response was lost.
        store.finish_digest(slot, error=safe_error(exc))
        return [f"Проверьте вручную отправку дайджеста {slot}: {type(exc).__name__}"]
    store.finish_digest(slot, message_id=message_id)
    return [f"Опубликован дайджест {slot}: {len(urls)} тем, message_id={message_id}"]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Личный бесплатный сборщик AI-новостей")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-model")
    sub.add_parser("discover-channel")
    sub.add_parser("check-channel")
    poll = sub.add_parser("poll")
    poll.add_argument("--include-existing", action="store_true", help="Взять уже существующие записи из лент для тестирования")
    poll.add_argument("--source", help="Опросить один источник из config.json")
    sub.add_parser("prepare")
    preview = sub.add_parser("preview-latest", help="Подготовить один пример из уже увиденных записей")
    preview.add_argument("--source", help="Имя источника из config.json")
    sub.add_parser("status")
    sub.add_parser("preview-digest", help="Показать текст ближайшего дайджеста без отправки")
    sub.add_parser("watchlist", help="Показать сохранённые каналы и фактически подключённые ленты")
    sub.add_parser("review")
    retry = sub.add_parser("retry-review", help="Повторно подготовить один отложенный материал после исправления правил")
    retry.add_argument("url")
    correct = sub.add_parser("correct-sent", help="Исправить опубликованный пост и сохранить прежний текст в истории")
    correct.add_argument("url")
    correct.add_argument("text_file", type=Path)
    correct_digest = sub.add_parser("correct-digest", help="Исправить опубликованный часовой дайджест")
    correct_digest.add_argument("slot", help="Слот выпуска из команды status")
    correct_digest.add_argument("text_file", type=Path)
    sub.add_parser("audit-ready", help="Повторно проверить готовые черновики на соответствие источнику")
    sub.add_parser("run-once")
    sub.add_parser("scan-once", help="Быстро проверить источники по их интервалам")
    sub.add_parser("telegram-scan-once", help="Проверить публичные Telegram-каналы")
    sub.add_parser("x-scan-once", help="Проверить X-аккаунты через публичные RSS-зеркала")
    sub.add_parser("process-once", help="Подготовить и опубликовать один новый материал")
    sub.add_parser("daily-prepare", help="Вечерняя редактура без отправки в канал")
    sub.add_parser("daily-publish", help="Один ежедневный выпуск в окне 20:56–21:04 MSK")
    sub.add_parser("activate", help="Включить автоматическую публикацию после проверки черновиков")
    args = parser.parse_args()
    config = load_config()

    if args.command == "watchlist":
        watchlist = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        connected = {source["name"] for source in config["sources"]}
        telegram = watchlist["telegram"]
        x_accounts = [url for group in watchlist["x"].values() for url in group]
        coverage = watchlist["official_feed_coverage"]
        active = sum(source in connected for source in coverage.values())
        source_store = Store(DB_PATH)
        connected_channels = sum(bool(state and state["last_id"] and not state["last_error"])
                                 for url in telegram if (state := source_store.telegram_channel(url.rsplit("/", 1)[-1])))
        print(f"Telegram: {len(telegram)} публичных каналов; последняя проверка успешна: {connected_channels}.")
        for url in telegram:
            state = source_store.telegram_channel(url.rsplit("/", 1)[-1])
            condition = ("ошибка: " + state["last_error"] if state and state["last_error"] else
                         "опрашивается" if state and state["last_id"] else "ожидает первой проверки")
            print(f"  {condition}: {url}")
        print(f"X: {len(x_accounts)} аккаунта; открытые ленты первоисточников: {active}.")
        for url in x_accounts:
            source = coverage.get(url)
            name = "X @" + url.rstrip("/").rsplit("/", 1)[-1]
            poll_state = source_store.poll_state(name)
            state = ("ошибка RSS: " + poll_state["last_error"] if poll_state and poll_state["last_error"] else
                     "RSS: проверка успешна" if poll_state and poll_state["last_success_at"] else "RSS: ожидает проверки")
            if source in connected:
                state += f"; открытая лента: {source}"
            print(f"  {state}: {url}")
        return

    if args.command == "check-model":
        from contextlib import nullcontext
        from .model_session import model_session
        with (model_session(config, ROOT) if config.get("publication_mode") == "daily" else nullcontext()):
            with urlopen(f"{config['ollama_url'].rstrip('/')}/api/tags", timeout=5) as response:
                models = json.load(response).get("models", [])
        names = [item.get("name") for item in models]
        print(f"Ollama: доступна; модель {config['model']}: {'установлена' if config['model'] in names else 'отсутствует'}")
        return
    if args.command == "discover-channel":
        token = read_token()
        bot = call(token, "getMe")
        if bot.get("username", "").casefold() != config.get("bot_username", "ai_news_main_bot").lstrip("@").casefold():
            raise SystemExit("Сохраненный токен принадлежит другому боту.")
        channels = find_channel(token)
        if not channels:
            print("Канал не найден в обновлениях бота. Опубликуйте еще одно тестовое сообщение и повторите команду.")
            return
        for channel_id, title in channels:
            print(f"Канал: {title!r}, ID: {channel_id}")
        if len(channels) == 1:
            config["channel_id"] = channels[0][0]
            save_config(config)
            print("ID канала сохранен в config.json; автопубликация пока отключена.")
        return
    if args.command == "check-channel":
        if not config["channel_id"]:
            raise SystemExit("Сначала выполните discover-channel.")
        title = check_channel_access(read_token(), int(config["channel_id"]), expected_username=config.get("bot_username", "ai_news_main_bot"))
        print(f"Канал {title!r}: бот имеет право публиковать сообщения.")
        return

    store = Store(DB_PATH)
    if config.get("publication_mode") == "daily" and args.command in {"prepare", "preview-latest", "audit-ready", "retry-review"}:
        # Explicit manual editing also uses only the independent finite session.
        from .model_session import model_session
        from .daily import candidates, local_now
        import time
        config = {**config, "_deadline": time.monotonic() + int(config.get("daily_prepare_seconds", 1500))}
        try:
            with single_run(ROOT / ".state" / "editor.lock") as acquired:
                if not acquired:
                    print("Другой редакторский запуск уже работает.")
                    return
                if args.command == "retry-review":
                    if not store.retry_review(args.url):
                        raise SystemExit("Материал не найден в очереди проверки.")
                urls = [r["url"] for r in candidates(store, local_now(), ("pending",))
                        if args.command != "preview-latest" or not args.source or r["source"] == args.source]
                if args.command == "retry-review":
                    urls = [url for url in urls if url == args.url]
                if args.command == "preview-latest":
                    urls = urls[:1]
                if urls or args.command == "audit-ready":
                    with model_session(config, ROOT):
                        if args.command == "audit-ready":
                            for row in candidates(store, local_now(), ("ready",)):
                                if time.monotonic() >= config["_deadline"]:
                                    break
                                try:
                                    verify_draft(config, row["title"], row["article"] or row["summary"], row["draft"])
                                except Exception as exc:
                                    store.set_state(row["url"], "needs_review", error=f"Audit: {type(exc).__name__}")
                        else:
                            print("\n".join(prepare(config, store, limit=max(1, len(urls)), candidate_urls=urls)))
                else:
                    print("Нет новых кандидатов за текущий московский день.")
        finally:
            store.close()
        return
    if config.get("publication_mode") == "daily" and args.command in {"daily-prepare", "daily-publish", "process-once", "preview-digest"}:
        from .daily import compose_daily, local_now, prepare_daily
        try:
            if args.command == "preview-digest":
                edition = compose_daily(config, store, local_now())
                print(edition.telegram or "Проверенных новостей за текущий московский день нет.")
                print(f"Полный выпуск: {edition.stories} историй; Telegram: {edition.selected}. Отправки не было.")
            elif args.command == "process-once":
                print("Ежедневный режим: сбор идёт отдельно; редактура и публикация запускаются по вечернему расписанию.")
            else:
                with single_run(ROOT / ".state" / "editor.lock") as acquired:
                    if acquired:
                        print("\n".join(prepare_daily(config, store, ROOT) if args.command == "daily-prepare" else publish_digest(config, store)))
                    else:
                        print("Другой вечерний запуск уже работает.")
        finally:
            store.close()
        return
    if args.command == "poll":
        print("\n".join(collect(config, store, include_existing=args.include_existing, only_source=args.source)))
    elif args.command == "prepare":
        print("\n".join(prepare(config, store)))
    elif args.command == "preview-latest":
        url = store.promote_baseline(args.source)
        if url is None:
            print("Нет исходных записей; сначала выполните poll.")
        else:
            print(f"Пример: {url}")
            print("\n".join(prepare(config, store, limit=1)))
    elif args.command == "status":
        print("\n".join(f"{state}: {count}" for state, count in store.counts()) or "Пока нет материалов.")
        print(f"Канал: {config['channel_id'] or 'не подключен'}; автопубликация: {config['auto_publish']}")
        telegram_count = store.db.execute(
            "SELECT COUNT(*) FROM telegram_channels WHERE last_id>0 AND last_error IS NULL"
        ).fetchone()[0]
        telegram_total = sum(source.get("type") == "telegram" for source in config["sources"])
        print(f"Telegram-источники: последняя проверка успешна: {telegram_count}/{telegram_total}")
        for row in store.ready()[:3]:
            print(f"\nЧерновик: {row['title']}\n{row['draft']}")
        latest = store.db.execute("SELECT slot,state,telegram_message_id FROM digests ORDER BY created_at DESC LIMIT 1").fetchone()
        if latest:
            print(f"Последний дайджест: {latest['slot']} — {latest['state']}, message_id={latest['telegram_message_id']}")
    elif args.command == "preview-digest":
        current = datetime.now().astimezone()
        interval = int(config.get("digest_interval_hours", 1))
        upcoming = due_slot(current, grace_minutes=0, interval_hours=interval, allow_catchup=True)
        if upcoming is None:
            next_hour = current.hour + (interval - current.hour % interval)
            print(f"Следующий выпуск после {next_hour % 24:02d}:00 и паузы 1–4 минуты.")
        else:
            delay = store.digest_delay(upcoming[0])
            slot_info = due_slot(current, grace_minutes=delay, interval_hours=interval, allow_catchup=True)
            if slot_info is None:
                print(f"Для завершённого блока выбрана пауза {delay} мин.; выпуск возможен после {current:%H}:{delay:02d}.")
            else:
                body, urls, discarded = compose(
                    config, store, slot_info[1],
                    window_start_utc=lookback_start(slot_info[1], int(config.get("digest_lookback_hours", 1))),
                )
                print(body or "Подходящих проверенных новостей за выбранный период нет.")
                print(f"\nВыбрано: {len(urls)}; пропущено: {len(discarded)}; отправки не было.")
    elif args.command == "review":
        for row in store.review_items():
            print(f"\n{row['state']}: {row['title']}\nПричина: {row['error']}\nURL: {row['url']}\nЧерновик: {row['draft'] or '(нет)'}")
    elif args.command == "retry-review":
        if not store.retry_review(args.url):
            raise SystemExit("Материал не найден в очереди проверки.")
        print("\n".join(prepare(config, store, limit=1)))
    elif args.command == "correct-sent":
        row = store.sent_item(args.url)
        if row is None or not row["telegram_message_id"]:
            raise SystemExit("Опубликованный пост не найден.")
        digest_item = store.db.execute("SELECT slot FROM digest_items WHERE url=?", (args.url,)).fetchone()
        if digest_item:
            raise SystemExit(f"Это часть общего дайджеста; исправьте весь пост командой correct-digest {digest_item['slot']} <файл>.")
        corrected = args.text_file.read_text(encoding="utf-8").strip()
        if not corrected or len(corrected) > 3000:
            raise SystemExit("Исправленный текст пустой или слишком длинный.")
        edit_message(read_token(), int(config["channel_id"]), int(row["telegram_message_id"]), corrected)
        store.record_correction(args.url, row["draft"] or "", corrected)
        print(f"Пост {row['telegram_message_id']} исправлен; исходный текст сохранен в истории.")
    elif args.command == "correct-digest":
        row = store.digest(args.slot)
        if row is None or row["state"] != "sent" or not row["telegram_message_id"]:
            raise SystemExit("Опубликованный дайджест не найден.")
        corrected = args.text_file.read_text(encoding="utf-8").strip()
        if not corrected or len(corrected) > 4000:
            raise SystemExit("Исправленный текст пустой или слишком длинный.")
        edit_message(read_token(), int(config["channel_id"]), int(row["telegram_message_id"]), corrected)
        store.record_digest_correction(args.slot, row["text"], corrected)
        print(f"Дайджест {args.slot} исправлен; исходный текст сохранен в истории.")
    elif args.command == "audit-ready":
        for row in store.ready():
            try:
                verify_draft(config, row["title"], row["article"] or "", row["draft"] or "")
                print(f"OK: {row['title']}")
            except Exception as exc:
                store.set_state(row["url"], "needs_review", error=f"Audit: {safe_error(exc)}")
                print(f"REVIEW: {row['title']}: {safe_error(exc)}")
    elif args.command == "run-once":
        with single_run(ROOT / ".state" / "scan.lock") as acquired:
            if not acquired:
                print("Другой запуск уже проверяет источники.")
            else:
                print("\n".join(collect(config, store, respect_schedule=True)))
        with single_run(ROOT / ".state" / "editor.lock") as acquired:
            if not acquired:
                print("Другой запуск уже готовит материал.")
            else:
                if config.get("publication_mode") != "daily":
                    print("\n".join(prepare(config, store, limit=1)))
                    print("\n".join(publish_digest(config, store)))
    elif args.command == "scan-once":
        with single_run(ROOT / ".state" / "scan.lock") as acquired:
            print("\n".join(collect(config, store, respect_schedule=True)) if acquired else "Другой запуск уже проверяет источники.")
    elif args.command == "telegram-scan-once":
        from .telegram_public import scan
        with single_run(ROOT / ".state" / "telegram.lock") as acquired:
            print("\n".join(scan(config, store)) if acquired else "Другой запуск уже проверяет Telegram.")
    elif args.command == "x-scan-once":
        with single_run(ROOT / ".state" / "x.lock") as acquired:
            print("\n".join(collect(config, store, respect_schedule=True, only_platform="x"))
                  if acquired else "Другой запуск уже проверяет X.")
    elif args.command == "process-once":
        with single_run(ROOT / ".state" / "editor.lock") as acquired:
            if acquired:
                print("\n".join(prepare(config, store, limit=1)))
                print("\n".join(publish_digest(config, store)))
            else:
                print("Другой запуск уже готовит материал.")
    elif args.command == "activate":
        if not config["channel_id"]:
            raise SystemExit("Сначала выполните discover-channel.")
        check_channel_access(read_token(), int(config["channel_id"]), expected_username=config.get("bot_username", "ai_news_main_bot"))
        config["auto_publish"] = True
        save_config(config)
        print("Автопубликация дайджеста включена.")


if __name__ == "__main__":
    main()
