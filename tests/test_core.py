import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from ainews.__main__ import publish_digest
from ainews.digest import card, compose, due_slot, lookback_start, parse_draft, previous_hour_start, published_in_window
from ainews.feeds import Entry, parse_feed
from ainews.lock import single_run
from ainews.pipeline import align_evidence, collect, draft_text, duplicate_story, duplicate_title, polish_draft, prepare, prerelease_url, recent_enough, speculative_telegram_post, sweeping_telegram_claim, telegram_evidence_url, verify_draft
from ainews.store import Store
from ainews.telegram_public import Post, entry_from_post, parse_page, promotional_post, scan as scan_telegram


class FeedTests(unittest.TestCase):
    def test_telegram_page_extracts_own_text_and_filters_ads(self):
        now = datetime.now(timezone.utc).isoformat()
        html = f'''<div class="tgme_widget_message" data-post="ai_newz/42">
            <div class="tgme_widget_message_text js-message_reply_text">Ложная цитата из другого поста</div>
            <div class="tgme_widget_message_text js-message_text">Новая модель помогает запускать задачи локально.<br>Разработчики опубликовали описание обновления для пользователей.</div>
            <time datetime="{now}"></time></div>
            <div class="tgme_widget_message" data-post="ai_newz/43"><div class="tgme_widget_message_text js-message_text">Реклама: получите скидку и промокод на платный курс. Это рекламный пост для теста фильтрации.</div><time datetime="{now}"></time></div>'''
        posts = parse_page(html, "ai_newz")
        self.assertEqual(len(posts), 2)
        entry = entry_from_post("Telegram @ai_newz", posts[0])
        self.assertIsNotNone(entry)
        self.assertEqual(entry.url, "https://t.me/ai_newz/42")
        self.assertIn("локально", entry.summary)
        self.assertNotIn("Ложная цитата", entry.summary)
        self.assertIsNone(entry_from_post("Telegram @ai_newz", posts[1]))

    def test_telegram_cursor_never_moves_backward(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            store.save_telegram_channel("ai_newz", 42, channel_id=123, access_hash=456)
            store.save_telegram_channel("ai_newz", 39, error="TimeoutError")
            row = store.telegram_channel("ai_newz")
            self.assertEqual(row["last_id"], 42)
            self.assertEqual(row["channel_id"], 123)
            store.close()

    def test_telegram_short_fact_survives_but_channel_promotion_does_not(self):
        now = datetime.now(timezone.utc)
        fact = Post("ai_newz", 50, now, "OpenAI выпустила новую модель для работы с длинными документами.")
        promotion = Post("ai_newz", 51, now, "OpenAI выпустила новую модель. Подписывайтесь на наш канал, чтобы узнать больше.")
        self.assertIsNotNone(entry_from_post("Telegram @ai_newz", fact))
        self.assertIsNone(entry_from_post("Telegram @ai_newz", promotion))

    def test_paid_activity_roundup_does_not_enter_news_queue(self):
        post = Post("ai_newz", 52, datetime.now(timezone.utc),
                    "Подборка активностей: сервис платит авторам за рекламные ролики. "
                    "Заходим на сайт, выбираем кампанию и получаем выплату за участие.")
        self.assertIsNone(entry_from_post("Telegram @ai_newz", post))

    def test_sweeping_iq_claim_is_held_for_review(self):
        self.assertTrue(sweeping_telegram_claim("ИИ официально получил IQ выше людей и стал умнее всех людей."))
        self.assertFalse(sweeping_telegram_claim("Модель решила визуальные задачи в открытом тесте."))

    def test_deleted_source_post_cannot_enter_later_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            source = "Telegram @ai_newz"
            for number in (10, 11, 12):
                store.add_feed(source, [Entry(source, f"Post {number}", f"https://t.me/ai_newz/{number}",
                                              datetime.now(timezone.utc).isoformat(), "Some news")], include_existing=True)
            store.set_state("https://t.me/ai_newz/11", "ready", draft="Approved")
            self.assertEqual(store.retire_missing_telegram(source, "ai_newz", {10, 12}), 1)
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url='https://t.me/ai_newz/11'").fetchone()[0], "skipped")
            self.assertEqual(store.retire_missing_telegram(source, "ai_newz", {12}), 0)
            store.close()

    def test_edited_telegram_post_invalidates_approved_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            source = "Telegram @ai_newz"
            url = "https://t.me/ai_newz/60"
            original = Entry(source, "Original news", url, datetime.now(timezone.utc).isoformat(), "A factual AI release was published today.")
            store.add_feed(source, [original], include_existing=True)
            store.set_state(url, "ready", draft="Old approved text")
            changed = Entry(source, "Corrected news", url, original.published, "The release was delayed by its authors.")
            self.assertTrue(store.refresh_telegram_post(url, changed))
            row = store.db.execute("SELECT state,draft,summary FROM items WHERE url=?", (url,)).fetchone()
            self.assertEqual((row["state"], row["draft"], row["summary"]), ("pending", None, changed.summary))
            self.assertTrue(store.refresh_telegram_post(url, None))
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (url,)).fetchone()[0], "skipped")
            store.close()

    def test_telegram_initial_hour_and_incremental_scan(self):
        now = datetime.now(timezone.utc).isoformat()
        def post(number: int, text: str) -> str:
            return f'<div class="tgme_widget_message" data-post="ai_newz/{number}"><div class="tgme_widget_message_text js-message_text">{text}</div><time datetime="{now}"></time></div>'
        first = post(10, "Разработчики представили обновление модели для локального запуска. В публикации приведены конкретные детали нового релиза.")
        second = post(11, "Опубликовано следующее обновление агента для обработки задач. Авторы описали его новое поведение и ограничения.")

        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            config = {"sources": [{"name": "Telegram @ai_newz", "type": "telegram", "handle": "ai_newz"}]}
            try:
                with patch("ainews.telegram_public.download", side_effect=[(first, "https://t.me/s/ai_newz"), (first + second, "https://t.me/s/ai_newz")]):
                    self.assertIn("1 новых", scan_telegram(config, store)[0])
                    self.assertIn("1 новых", scan_telegram(config, store)[0])
                self.assertEqual(store.telegram_channel("ai_newz")["last_id"], 11)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM items").fetchone()[0], 2)
            finally:
                store.close()

    def test_first_telegram_scan_uses_six_hour_digest_window(self):
        published = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        html = (f'<div class="tgme_widget_message" data-post="ai_newz/70">'
                '<div class="tgme_widget_message_text js-message_text">'
                'Разработчики выпустили обновление модели для работы с документами. '
                'Описаны изменения и ограничения.</div>'
                f'<time datetime="{published}"></time></div>')
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            config = {"digest_lookback_hours": 6, "sources": [
                {"name": "Telegram @ai_newz", "type": "telegram", "handle": "ai_newz"}
            ]}
            with patch("ainews.telegram_public.download", return_value=(html, "https://t.me/s/ai_newz")):
                self.assertIn("1 новых", scan_telegram(config, store)[0])
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)
            store.close()

    def test_telegram_unavailable_channel_does_not_stop_others(self):
        now = datetime.now(timezone.utc).isoformat()
        html = f'<div class="tgme_widget_message" data-post="ai_newz/20"><div class="tgme_widget_message_text js-message_text">Разработчики выпустили обновление модели для локальной работы. Описание изменений опубликовано в открытом канале.</div><time datetime="{now}"></time></div>'
        config = {"sources": [
            {"name": "Telegram @broken", "type": "telegram", "handle": "broken"},
            {"name": "Telegram @ai_newz", "type": "telegram", "handle": "ai_newz"},
        ]}
        def fetch(url, **kwargs):
            if url.endswith("/broken"):
                raise TimeoutError("unavailable")
            return html, url
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            try:
                with patch("ainews.telegram_public.download", side_effect=fetch):
                    report = scan_telegram(config, store)
                self.assertIn("ошибка TimeoutError", report[0])
                self.assertIn("1 новых", report[1])
                self.assertIn("TimeoutError", store.telegram_channel("broken")["last_error"])
                self.assertIsNone(store.telegram_channel("ai_newz")["last_error"])
            finally:
                store.close()

    def test_rss_guid_fallback_and_atom(self):
        rss = "<rss><channel><item><title>Launch</title><guid>https://example.com/a</guid><description>Useful update</description></item></channel></rss>"
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Release</title><link href="https://example.com/b"/><updated>2026-09-24T00:00:00Z</updated></entry></feed>'
        self.assertEqual(parse_feed(rss, "A")[0].url, "https://example.com/a")
        self.assertEqual(parse_feed(atom, "B")[0].url, "https://example.com/b")

    def test_sitemap(self):
        sitemap = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/news/new-model</loc><lastmod>2026-09-24T00:00:00Z</lastmod></url></urlset>'
        item = parse_feed(sitemap, "A")[0]
        self.assertEqual(item.title, "new model")
        self.assertEqual(item.published, "2026-09-24T00:00:00Z")

    def test_dates_and_duplicates(self):
        date = format_datetime(datetime.now(timezone.utc))
        self.assertTrue(recent_enough(date))
        self.assertTrue(duplicate_title("Introducing Hermes Agent 2", ["Introducing Hermes Agent 2!"]))

    def test_release_candidate_is_not_a_stable_release(self):
        self.assertTrue(prerelease_url("https://github.com/ollama/ollama/releases/tag/v0.40.0-rc0"))
        self.assertTrue(prerelease_url("https://github.com/example/project/releases/tag/v1.0-beta.2"))
        self.assertTrue(prerelease_url("https://github.com/example/project/releases/tag/v0.62.0-nightly.20260925"))
        self.assertTrue(prerelease_url("https://github.com/example/project/releases/tag/v0.21.4+canary.20260925"))
        self.assertFalse(prerelease_url("https://github.com/ollama/ollama/releases/tag/v0.40.0"))
        self.assertTrue(speculative_telegram_post("OpenAI готовит подписку. Скорее всего, это платный план."))
        self.assertFalse(speculative_telegram_post("Компания выпустила новую модель для разработчиков."))

    def test_evidence_alignment_changes_only_source_punctuation(self):
        source = "Today, we’re sharing early results."
        repaired = align_evidence({"evidence": "Today, we're sharing early results."}, source)
        self.assertEqual(repaired["evidence"], source)
        uncertain = align_evidence({"evidence": "Today, we're publishing confirmed results."}, source)
        self.assertEqual(uncertain["evidence"], "Today, we're publishing confirmed results.")

    def test_evidence_alignment_uses_one_exact_sentence_when_model_splices_two(self):
        source = ("The new model reads documents locally. Its authors also published a detailed guide. "
                  "Later, the release notes describe supported languages.")
        spliced = {"evidence": "The new model reads documents locally. Later, the release notes describe supported languages."}
        aligned = align_evidence(spliced, source)
        self.assertEqual(aligned["evidence"], "Later, the release notes describe supported languages.")


class GateTests(unittest.TestCase):
    def draft(self):
        return {
            "relevant": True,
            "confidence": "high",
            "headline": "Новая модель",
            "what_happened": "Компания выпустила модель 9B.",
            "simple_explanation": "Она помогает писать текст.",
            "why_it_matters": "Ее можно запускать локально.",
            "caveat": "Доступна не всем.",
            "evidence": "Company released a 9B model for local use.",
        }

    def test_draft_requires_source_for_numbers(self):
        without_number = self.draft()
        without_number["evidence"] = "Company released a model for local use."
        with self.assertRaisesRegex(ValueError, "numbers"):
            draft_text(without_number, "Company released a model for local use.")
        self.assertIn("9B", draft_text(self.draft(), "Company released a 9B model for local use."))

    def test_draft_rejects_links_and_uncertainty(self):
        draft = self.draft()
        draft["headline"] = "Читайте t.me/other_channel"
        with self.assertRaisesRegex(ValueError, "link"):
            draft_text(draft, "Company released a 9B model for local use.")
        draft = self.draft()
        draft["confidence"] = "low"
        with self.assertRaisesRegex(ValueError, "uncertain"):
            draft_text(draft, "Company released a 9B model for local use.")

    def test_draft_requires_exact_evidence(self):
        draft = self.draft()
        draft["evidence"] = "Company released an unrelated 9B model."
        with self.assertRaisesRegex(ValueError, "evidence"):
            draft_text(draft, "Company released a 9B model for local use.")

    def test_style_edit_cannot_replace_evidence_or_confidence(self):
        original = self.draft()
        edited = {**original, "headline": "Модель вышла", "evidence": "invented evidence", "confidence": "low"}
        with patch("ainews.pipeline.ollama_json", return_value=edited):
            result = polish_draft({"model": "local"}, "Release", original["evidence"], original)
        self.assertEqual(result["headline"], "Модель вышла")
        self.assertEqual(result["evidence"], original["evidence"])
        self.assertEqual(result["confidence"], "high")

    def test_preliminary_status_and_unsupported_launch_are_blocked(self):
        source = "Company released a 9B model for local use."
        with self.assertRaisesRegex(ValueError, "preliminary status"):
            draft_text(self.draft(), source, source_title="Model beta")
        draft = self.draft()
        draft["simple_explanation"] = "ИИ запускается автоматически."
        with self.assertRaisesRegex(ValueError, "automatic launch"):
            draft_text(draft, source)

    def test_draft_removes_invented_gestures_and_zero_delay(self):
        source = "Company released a 9B model for local use. The video feature has low latency."
        draft = self.draft()
        draft["simple_explanation"] = "Модель реагирует на жесты пользователя."
        self.assertNotIn("жесты", draft_text(draft, source))
        draft["simple_explanation"] = "Модель отвечает мгновенно."
        output = draft_text(draft, source)
        self.assertNotIn("мгновенно", output)
        self.assertIn("с малой задержкой", output)

    def test_draft_preserves_explicit_access_restriction(self):
        source = ("Company released a 9B model for local use. "
                  "Custom avatar creation is currently available only through enterprise allowlisting.")
        draft = self.draft()
        draft["what_happened"] = "Компании могут создавать собственные аватары."
        with self.assertRaisesRegex(ValueError, "access restriction"):
            draft_text(draft, source)
        draft["caveat"] = "Создание своих аватаров доступно только после допуска компании."
        self.assertIn("только после допуска", draft_text(draft, source))

    def test_long_draft_fact_check_rechecks_short_groups(self):
        responses = [
            {"supported": False, "unsupported_claims": ["Unclear in long text"]},
            {"supported": True, "unsupported_claims": []},
            {"supported": True, "unsupported_claims": []},
        ]
        draft = "🧠 Новая модель\n\nЧто произошло: Выпущена модель. Она работает локально. Авторы описали ограничения.\n\nПростыми словами: Модель запускается на своём компьютере."
        with patch("ainews.pipeline.ollama_json", side_effect=responses) as model:
            verify_draft({"model": "local", "ollama_url": "http://localhost"}, "Release",
                         "The model runs locally and has limitations.", draft)
        self.assertEqual(model.call_count, 3)


class StoreTests(unittest.TestCase):
    def test_initial_baseline_then_new_item_and_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            first = Entry("A", "One", "https://example.com/1", "today", "summary")
            second = Entry("A", "Two", "https://example.com/2", "today", "summary")
            self.assertEqual(store.add_feed("A", [first]), 1)
            self.assertEqual(store.counts(), [("baseline", 1)])
            self.assertEqual(store.add_feed("A", [first, second]), 1)
            self.assertEqual(store.next_pending()["url"], second.url)
            store.set_state(second.url, "ready", draft="Some text")
            self.assertTrue(store.claim_ready(second.url))
            self.assertFalse(store.claim_ready(second.url))
            store.mark_sent(second.url, 42)
            self.assertEqual(store.counts(), [("baseline", 1), ("sent", 1)])
            store.close()

    def test_source_cadence_and_error_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            self.assertTrue(store.source_due("A", now=1000))
            store.record_poll_success("A", 60, etag='"abc"', now=1000)
            self.assertFalse(store.source_due("A", now=1059))
            self.assertTrue(store.source_due("A", now=1060))
            self.assertEqual(store.record_poll_failure("A", "HTTP 503", now=1060), 60)
            self.assertEqual(store.record_poll_failure("A", "HTTP 503", now=1120), 120)
            self.assertEqual(store.poll_state("A")["etag"], '"abc"')
            store.record_poll_success("A", 300, now=1240)
            self.assertEqual(store.poll_state("A")["consecutive_failures"], 0)
            self.assertEqual(store.poll_state("A")["etag"], '"abc"')
            store.close()

    def test_digest_delay_is_persisted_and_varies_between_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            with patch("ainews.store.secrets.choice", side_effect=lambda choices: choices[0]):
                self.assertEqual(store.digest_delay("2026-09-25T10+0300"), 1)
                self.assertEqual(store.digest_delay("2026-09-25T10+0300"), 1)
                self.assertEqual(store.digest_delay("2026-09-25T11+0300"), 2)
            store.close()

    def test_scheduled_feed_poll_uses_cache_and_due_time(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            config = {"sources": [{"name": "A", "feed": "https://example.com/feed", "hosts": ["example.com"], "poll_seconds": 60}]}
            rss = "<rss><channel><item><title>Launch</title><link>https://example.com/a</link></item></channel></rss>"
            with patch("ainews.pipeline.download_feed", return_value=(rss, "https://example.com/feed", '"v1"', None)) as get:
                self.assertIn("1 new", collect(config, store, respect_schedule=True)[0])
                self.assertIn("Нет источников", collect(config, store, respect_schedule=True)[0])
                get.assert_called_once()
            with patch("ainews.pipeline.download_feed", return_value=(None, "https://example.com/feed", '"v1"', None)) as get:
                self.assertIn("not modified", collect(config, store)[0])
                self.assertEqual(get.call_args.kwargs["etag"], '"v1"')
            store.close()

    def test_single_run_prevents_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            with single_run(path) as first:
                with single_run(path) as second:
                    self.assertTrue(first)
                    self.assertFalse(second)

    def test_editor_revises_a_rejected_draft_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            url = "https://example.com/model"
            store.add_feed("Official", [Entry("Official", "Model launch", url, format_datetime(datetime.now(timezone.utc)), "summary")], include_existing=True)
            old_url = "https://example.com/z-old"
            store.add_feed("Official", [Entry("Official", "Old release", old_url,
                                              format_datetime(datetime.now(timezone.utc) - timedelta(days=1)),
                                              "old summary")], include_existing=True)
            config = {"sources": [{"name": "Official", "hosts": ["example.com"], "freshness_minutes": 180}]}
            article = "Company released a 9B model for local use."
            draft = {
                "relevant": True, "confidence": "high", "headline": "Новая модель",
                "what_happened": "Компания выпустила модель 9B.",
                "simple_explanation": "Она помогает писать текст.",
                "why_it_matters": "Ее можно запускать локально.", "caveat": "",
                "evidence": article,
            }
            with patch("ainews.pipeline.article_details", return_value=(article, None)), \
                 patch("ainews.pipeline.generate_draft", return_value=draft), \
                 patch("ainews.pipeline.polish_draft", return_value=draft), \
                 patch("ainews.pipeline.revise_draft", return_value=draft) as revise, \
                 patch("ainews.pipeline.verify_draft", side_effect=[ValueError("unsupported"), None]) as verify:
                report = prepare(config, store, limit=1)
                self.assertIn("SKIP old", report[0])
                self.assertIn("READY", report[1])
                revise.assert_called_once()
                self.assertEqual(verify.call_count, 2)
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (url,)).fetchone()[0], "ready")
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (old_url,)).fetchone()[0], "skipped")
            store.close()


class EditorialQualityTests(unittest.TestCase):
    def test_delayed_official_rss_uses_brief_and_24_hour_catchup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            url = "https://official.example/model-launch"
            summary = "The company released a new model for coding and computer use. It is available through the API."
            store.add_feed("Official", [Entry(
                "Official", "New model launch", url,
                format_datetime(datetime.now(timezone.utc) - timedelta(hours=12)), summary
            )], include_existing=True)
            config = {"sources": [{"name": "Official", "content_from_feed": True,
                                   "auto_publish": True, "hosts": ["official.example"]}],
                      "digest_lookback_hours": 6, "official_catchup_hours": 24}
            draft = {"relevant": True, "confidence": "high", "headline": "Новая модель",
                     "what_happened": "Компания выпустила модель для работы с кодом и компьютером.",
                     "simple_explanation": "", "why_it_matters": "", "caveat": "", "evidence": summary}
            with patch("ainews.pipeline.generate_draft", return_value=draft) as generate, \
                 patch("ainews.pipeline.polish_draft", return_value=draft), \
                 patch("ainews.pipeline.verify_draft"):
                self.assertIn("READY", prepare(config, store, limit=1)[0])
                generate.assert_called_once_with(config, "New model launch", summary, official_brief=True)
            store.close()

    def test_short_official_announcement_is_given_a_brief_news_prompt(self):
        from ainews.pipeline import generate_draft
        summary = "Meet a new model for coding and computer use at one fifth of a larger model's API token prices."
        with patch("ainews.pipeline.ollama_json", return_value={"relevant": True}) as model:
            generate_draft({"model": "local", "ollama_url": "http://localhost"}, "Model launch", summary,
                           official_brief=True)
        prompt = model.call_args.args[1]
        self.assertIn("не отклоняй его только из-за малой длины текста", prompt)
        self.assertIn(summary, prompt)

    def test_publication_date_extraction(self):
        from ainews.feeds import PublicationDateExtractor
        from ainews.pipeline import original_article_is_old
        extractor = PublicationDateExtractor()
        extractor.feed('<meta property="article:published_time" content="2026-09-20T10:00:00+00:00">')
        self.assertEqual(extractor.dates, ["2026-09-20T10:00:00+00:00"])
        self.assertTrue(original_article_is_old("2026-03-28", minutes=360))
        self.assertFalse(original_article_is_old(datetime.now(timezone.utc).date().isoformat(), minutes=360))
        self.assertFalse(original_article_is_old("date unavailable", minutes=360))

    def test_same_event_is_caught_across_different_headlines(self):
        self.assertTrue(duplicate_story(
            "NVIDIA анонсировала платформу безопасности для ИИ-агентов",
            ["NVIDIA анонсировала платформу безопасности для ИИ-агентов с контролем на уровне чипа"],
        ))
        self.assertTrue(duplicate_story(
            "OpenAI и Anthropic расследуют десятки тысяч побегов агентов",
            ["OpenAI и Anthropic фиксируют тысячи попыток побега ИИ из песочницы"],
        ))
        self.assertFalse(duplicate_story(
            "NVIDIA выпустила новые видеокарты для локальных моделей",
            ["NVIDIA анонсировала платформу безопасности для ИИ-агентов"],
        ))

    def test_repost_needs_direct_verifiable_link(self):
        self.assertEqual(telegram_evidence_url("Разбор https://arxiv.org/pdf/2609.29901"),
                         "https://arxiv.org/abs/2609.29901")
        self.assertIsNone(telegram_evidence_url("Новости только в https://t.me/example/1"))
        self.assertIsNone(telegram_evidence_url("Короткая ссылка https://nvda.ws/abc"))
        self.assertIsNone(telegram_evidence_url("Анонс на https://openai.com/"))
        now = datetime.now(timezone.utc).isoformat()
        posts = parse_page(
            '<div class="tgme_widget_message" data-post="example/1">'
            '<div class="tgme_widget_message_text js-message_text">'
            'Исследователи описали результаты для новой модели, подробности в '
            '<a href="https://arxiv.org/abs/2609.29901">статье</a>.</div>'
            f'<time datetime="{now}"></time></div>', "example")
        self.assertEqual(telegram_evidence_url(posts[0].text), "https://arxiv.org/abs/2609.29901")

    def test_disguised_sales_posts_are_filtered(self):
        self.assertTrue(promotional_post("Курс по ML обновили. Цену оставили той же, записаться можно сегодня."))
        self.assertTrue(promotional_post("Можно арендовать сервер с RTX. Оплата только за время работы."))
        self.assertFalse(promotional_post("Исследователи выпустили модель и опубликовали результаты тестов."))
        self.assertTrue(promotional_post("49 ИИ-инструментов вместо платных подписок: подборка ссылок."))

    def test_telegram_claim_without_external_evidence_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            url = "https://t.me/example/100"
            store.add_feed("Telegram @example", [Entry(
                "Telegram @example", "Компания выпустила новую модель",
                url, format_datetime(datetime.now(timezone.utc)),
                "Компания выпустила новую модель, которая помогает работать с кодом и файлами."
            )], include_existing=True)
            config = {"sources": [{"name": "Telegram @example", "type": "telegram", "hosts": ["t.me"],
                                   "auto_publish": True}], "digest_lookback_hours": 6}
            report = prepare(config, store, limit=1)
            self.assertIn("REVIEW no primary source", report[0])
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (url,)).fetchone()[0],
                             "needs_review")
            store.close()

    def test_telegram_rewrite_uses_linked_article_as_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            url = "https://t.me/example/101"
            store.add_feed("Telegram @example", [Entry(
                "Telegram @example", "Компания выпустила новую модель", url,
                format_datetime(datetime.now(timezone.utc)),
                "Компания выпустила новую модель для разработчиков. https://openai.com/index/model-news"
            )], include_existing=True)
            config = {"sources": [{"name": "Telegram @example", "type": "telegram", "hosts": ["t.me"],
                                   "auto_publish": True}], "digest_lookback_hours": 6}
            article = "The company released a new model for developer workflows and published the details today."
            draft = {"relevant": True, "confidence": "high", "headline": "Новая модель",
                     "what_happened": "Компания выпустила новую модель для разработчиков.",
                     "simple_explanation": "", "why_it_matters": "", "caveat": "", "evidence": article}
            with patch("ainews.pipeline.article_details", return_value=(article, datetime.now(timezone.utc).isoformat())) as get_article, \
                 patch("ainews.pipeline.generate_draft", return_value=draft), \
                 patch("ainews.pipeline.polish_draft", return_value=draft), \
                 patch("ainews.pipeline.verify_draft"):
                self.assertIn("READY", prepare(config, store, limit=1)[0])
                get_article.assert_called_once_with("https://openai.com/index/model-news", ["openai.com"])
            self.assertEqual(store.db.execute("SELECT article FROM items WHERE url=?", (url,)).fetchone()[0], article)
            store.close()

    def test_old_original_is_not_revived_by_fresh_telegram_repost(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            url = "https://t.me/example/102"
            store.add_feed("Telegram @example", [Entry(
                "Telegram @example", "Новая статья о модели", url,
                format_datetime(datetime.now(timezone.utc)),
                "В канале сообщили о модели. https://arxiv.org/abs/2603.29886"
            )], include_existing=True)
            config = {"sources": [{"name": "Telegram @example", "type": "telegram", "hosts": ["t.me"],
                                   "auto_publish": True}], "digest_lookback_hours": 6}
            with patch("ainews.pipeline.article_details", return_value=("Article text " * 30, "2026-03-28")):
                self.assertIn("SKIP old original", prepare(config, store, limit=1)[0])
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (url,)).fetchone()[0], "skipped")
            store.close()


class DigestTests(unittest.TestCase):
    def test_three_hour_digest_waits_for_block_end_and_sends_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            current = datetime.now().astimezone()
            boundary = current.replace(minute=4, second=0, microsecond=0)
            boundary -= timedelta(hours=boundary.hour % 3)
            earlier = boundary - timedelta(hours=1)
            self.assertIsNone(due_slot(earlier, grace_minutes=0, interval_hours=3))
            self.assertIsNone(due_slot(boundary.replace(minute=0), grace_minutes=4, interval_hours=3))
            slot, cutoff = due_slot(boundary, grace_minutes=4, interval_hours=3)
            self.assertEqual(datetime.strptime(slot[:13], "%Y-%m-%dT%H").hour, (boundary.hour - 3) % 24)
            self.add_ready(store, "https://example.com/three-hour", "Agent update", "Обновление агента", cutoff)
            config = {**self.config(), "digest_interval_hours": 3}
            store.db.execute("INSERT INTO digest_schedule VALUES (?,4)", (slot,))
            store.db.commit()
            with patch("ainews.__main__.read_token", return_value="secret"), \
                 patch("ainews.__main__.send_message", return_value=77) as send:
                self.assertEqual(publish_digest(config, store, now=earlier), [])
                self.assertIn("Опубликован", publish_digest(config, store, now=boundary)[0])
                self.assertEqual(publish_digest(config, store, now=boundary), [])
                send.assert_called_once()
            store.close()

    def test_missed_three_hour_slot_can_be_caught_up(self):
        moscow = timezone(timedelta(hours=3))
        late = datetime(2026, 9, 30, 11, 30, tzinfo=moscow)
        self.assertIsNone(due_slot(late, grace_minutes=2, interval_hours=3))
        self.assertEqual(due_slot(late, grace_minutes=2, interval_hours=3, allow_catchup=True),
                         ("2026-09-30T06+0300", "2026-09-30 06:00:00"))

    def test_overflow_remains_ready_for_next_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00:00")
            self.add_ready(store, "https://example.com/one", "First agent release", "Первый агент", cutoff)
            self.add_ready(store, "https://example.com/two", "Second model release", "Вторая модель", cutoff)
            config = {**self.config(), "max_digest_chars": 105}
            body, urls, discarded = compose(config, store, cutoff)
            self.assertEqual(len(urls), 1)
            self.assertLessEqual(len(body), 105)
            self.assertEqual(discarded, [])
            self.assertEqual(len(store.ready()), 2)
            self.assertTrue(store.reserve_digest("three-hour-test", body, urls, discarded))
            self.assertEqual(len(store.ready()), 1)
            store.close()

    def test_concise_draft_with_only_verified_news_is_valid(self):
        fields = parse_draft("🧠 В AI Studio появились скиллы\n\nЧто произошло: Инструкцию для агента можно использовать снова.")
        self.assertEqual(fields["what"], "Инструкцию для агента можно использовать снова.")
        self.assertIn("использовать снова", card(fields))

    def add_ready(self, store: Store, url: str, title: str, headline: str, cutoff: str) -> None:
        source = "Official"
        published = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - timedelta(minutes=10)
        store.add_feed(source, [Entry(source, title, url, format_datetime(published), "summary")], include_existing=True)
        draft = (
            f"🧠 {headline}\n\nЧто произошло: Компания представила {headline.lower()}."
            "\n\nПростыми словами: Появился новый инструмент для работы с ИИ."
            "\n\nЗачем это нужно: Пользователи получили новый способ решать задачи."
        )
        store.set_state(url, "ready", draft=draft)
        store.db.execute("UPDATE items SET created_at=datetime(?,'-10 minutes') WHERE url=?", (cutoff, url))
        store.db.commit()

    def config(self) -> dict:
        return {
            "auto_publish": True, "channel_id": -100123, "max_posts_per_day": 24,
            "digest_lookback_hours": 6,
            "sources": [{"name": "Official", "auto_publish": True, "freshness_minutes": 180}],
        }

    def test_digest_does_not_stop_at_eight_when_more_news_fits(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "news.sqlite3")
            cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00:00")
            names = ("Atlas", "Boreal", "Cobalt", "Delta", "Echo", "Fjord", "Garnet", "Helix", "Iris")
            for name in names:
                self.add_ready(store, f"https://example.com/{name.lower()}",
                               f"{name} agent update", f"Обновление {name}", cutoff)
            config = self.config()
            config["max_digest_items"] = 0
            body, urls, discarded = compose(config, store, cutoff)
            self.assertEqual(len(urls), len(names))
            self.assertEqual(discarded, [])
            self.assertLessEqual(len(body), 3900)
            store.close()

    def test_one_hourly_digest_deduplicates_and_sends_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            slot, cutoff = due_slot(now)
            self.add_ready(store, "https://example.com/a", "New AI model released", "Новая модель ИИ", cutoff)
            self.add_ready(store, "https://example.com/b", "New AI model released!", "Новая модель ИИ", cutoff)
            self.add_ready(store, "https://example.com/c", "Agent tool launched", "Новый агент", cutoff)
            self.add_ready(store, "https://example.com/ad", "Sponsored promo code", "Реклама", cutoff)
            body, urls, discarded = compose(self.config(), store, cutoff)
            self.assertEqual(len(urls), 2)
            self.assertEqual(len(discarded), 2)
            self.assertTrue(body.startswith("- "))
            self.assertIn("- Новая модель ИИ\n\n  ", body)
            self.assertIn("- Новый агент\n\n  ", body)
            self.assertNotIn("Главное об ИИ", body)
            self.assertNotIn("1. ", body)
            self.assertNotIn("Простыми словами:", body)
            self.assertNotIn("Почему важно:", body)
            self.assertNotIn("Реклама", body)
            with patch("ainews.__main__.read_token", return_value="secret"), patch("ainews.__main__.send_message", return_value=42) as send:
                self.assertIn("2 тем", publish_digest(self.config(), store, now=now)[0])
                self.assertEqual(publish_digest(self.config(), store, now=now), [])
                send.assert_called_once()
                self.assertLess(len(send.call_args.args[2]), 4000)
            self.assertEqual(store.digest(slot)["state"], "sent")
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM items WHERE state='sent'").fetchone()[0], 2)
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM items WHERE state='skipped'").fetchone()[0], 2)
            store.close()

    def test_one_story_keeps_full_detail_and_dense_digest_shortens(self):
        fields = {
            "headline": "Новая модель для работы с документами",
            "what": " ".join(f"Разработчики описали подтверждённую функцию номер {i}." for i in range(1, 11)),
            "simple": " ".join(f"Это объяснение детали номер {i} простыми словами." for i in range(1, 6)),
            "why": "Пользователь видит результат прямо в интерфейсе. Это помогает понять изменение.",
            "caveat": "Доступ пока ограничен тестовой группой.",
        }
        full = card(fields)
        compact = card(fields, 440)
        self.assertGreater(len(full), len(compact))
        self.assertLessEqual(len(compact), 440)
        self.assertIn("функцию номер 10", full)
        self.assertNotIn("функцию номер 10", compact)
        self.assertIn("Доступ пока ограничен", compact)
        self.assertTrue(compact.startswith("- Новая модель"))

    def test_eight_detailed_stories_fit_one_telegram_message(self):
        names = ["Alpha model", "Beta voice", "Gamma robotics", "Delta inference",
                 "Epsilon agents", "Zeta images", "Eta evaluation", "Theta search"]
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now)
            for index, name in enumerate(names):
                url = f"https://example.com/story-{index}"
                self.add_ready(store, url, name, name, cutoff)
                detail = " ".join(f"Авторы описали подтверждённую деталь {number} для {name}." for number in range(1, 12))
                draft = (f"🧠 {name}\n\nЧто произошло: {detail}\n\n"
                         "Простыми словами: Изменение касается работы инструмента. Пользователь видит результат в интерфейсе.\n\n"
                         "Зачем это нужно: Команда объяснила применение этой функции.")
                store.set_state(url, "ready", draft=draft)
            body, urls, discarded = compose(self.config(), store, cutoff)
            self.assertEqual(len(urls), 8)
            self.assertFalse(discarded)
            self.assertLessEqual(len(body), 3900)
            self.assertEqual(body.count("\n\n- "), 7)
            store.close()

    def test_uncertain_hourly_send_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            slot, cutoff = due_slot(now)
            self.add_ready(store, "https://example.com/a", "New model released", "Новая модель", cutoff)
            with patch("ainews.__main__.read_token", return_value="secret"), patch("ainews.__main__.send_message", side_effect=TimeoutError) as send:
                self.assertIn("Проверьте вручную", publish_digest(self.config(), store, now=now)[0])
                self.assertEqual(publish_digest(self.config(), store, now=now), [])
                send.assert_called_once()
            self.assertEqual(store.digest(slot)["state"], "send_uncertain")
            store.close()

    def test_digest_suppresses_reworded_source_with_published_headline(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now)
            first = "https://example.com/a"
            second = "https://example.com/b"
            self.add_ready(store, first, "0.157.0", "Codex добавил новые модели", cutoff)
            self.assertTrue(store.claim_ready(first))
            store.mark_sent(first, 10)
            self.add_ready(store, second, "Анонс обновления инструмента", "Codex добавил новые модели!", cutoff)
            _, urls, discarded = compose(self.config(), store, cutoff)
            self.assertEqual(urls, [])
            self.assertEqual(discarded[0][0], second)
            store.close()

    def test_new_hour_items_wait_for_next_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now)
            url = "https://example.com/new-hour"
            self.add_ready(store, url, "Agent launched", "Новый агент", cutoff)
            store.db.execute("UPDATE items SET created_at=datetime(?,'+1 minute') WHERE url=?", (cutoff, url))
            store.db.commit()
            body, urls, discarded = compose(self.config(), store, cutoff)
            self.assertEqual((body, urls, discarded), ("", [], []))
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (url,)).fetchone()[0], "ready")
            store.close()

    def test_no_post_at_hour_boundary_and_neighboring_hours_can_vary(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            first = (datetime.now().astimezone() - timedelta(hours=2)).replace(minute=4, second=20, microsecond=0)
            second = first + timedelta(hours=1, minutes=-2)
            first_slot, first_cutoff = due_slot(first, grace_minutes=0)
            second_slot, second_cutoff = due_slot(second, grace_minutes=0)
            self.assertIsNone(due_slot(first.replace(minute=0), grace_minutes=4))
            self.assertIsNone(due_slot(first.replace(minute=3), grace_minutes=4))
            store.db.execute("INSERT INTO digest_schedule VALUES (?,4)", (first_slot,))
            store.db.execute("INSERT INTO digest_schedule VALUES (?,2)", (second_slot,))
            store.db.commit()
            self.add_ready(store, "https://example.com/first", "First model", "Первая модель", first_cutoff)
            config = {**self.config(), "digest_lookback_hours": 6}
            with patch("ainews.__main__.read_token", return_value="secret"), patch("ainews.__main__.send_message", side_effect=[1, 2]) as send:
                self.assertEqual(publish_digest(config, store, now=first.replace(minute=0)), [])
                self.assertIn("Опубликован", publish_digest(config, store, now=first)[0])
                self.add_ready(store, "https://example.com/second", "Second agent", "Второй агент", second_cutoff)
                self.assertIn("Опубликован", publish_digest(config, store, now=second)[0])
                self.assertEqual(send.call_count, 2)
            store.close()

    def test_digest_uses_only_previous_hour(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now, grace_minutes=0)
            old_url = "https://example.com/old"
            new_url = "https://example.com/new"
            self.add_ready(store, old_url, "Older agent", "Старый агент", cutoff)
            self.add_ready(store, new_url, "New model", "Новая модель", cutoff)
            store.db.execute("UPDATE items SET created_at=datetime(?,'-70 minutes') WHERE url=?", (cutoff, old_url))
            old_published = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - timedelta(minutes=70)
            store.db.execute("UPDATE items SET published=? WHERE url=?", (format_datetime(old_published), old_url))
            store.db.commit()
            body, urls, discarded = compose(
                self.config(), store, cutoff, window_start_utc=previous_hour_start(cutoff)
            )
            self.assertEqual(urls, [new_url])
            self.assertEqual(discarded[0][0], old_url)
            self.assertNotIn("Старый агент", body)
            store.close()

    def test_six_hour_digest_carries_unsent_recent_story(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now, grace_minutes=0)
            url = "https://example.com/carryover"
            self.add_ready(store, url, "Recent agent release", "Недавний релиз агента", cutoff)
            published = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - timedelta(hours=2)
            store.db.execute("UPDATE items SET published=?,created_at=datetime(?,'-2 hours') WHERE url=?",
                             (format_datetime(published), cutoff, url))
            store.db.commit()
            config = {**self.config(), "digest_lookback_hours": 6}
            body, urls, discarded = compose(config, store, cutoff,
                                            window_start_utc=lookback_start(cutoff, 6))
            self.assertEqual(urls, [url])
            self.assertFalse(discarded)
            self.assertIn("Недавний релиз", body)
            store.close()

    def test_official_story_can_be_caught_up_without_extending_telegram_window(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00:00")
            official = "https://example.com/official"
            telegram = "https://t.me/example/1"
            self.add_ready(store, official, "Official model launch", "Официальный релиз модели", cutoff)
            store.add_feed("Telegram @example", [Entry(
                "Telegram @example", "Та же старая новость", telegram,
                format_datetime(datetime.now(timezone.utc) - timedelta(hours=20)), "Пост"
            )], include_existing=True)
            store.set_state(telegram, "ready", draft="🧠 Старая тема\n\nЧто произошло: Ранее вышла модель.")
            old = format_datetime(datetime.now(timezone.utc) - timedelta(hours=20))
            store.db.execute("UPDATE items SET published=?,created_at=datetime(?,'-20 hours') WHERE url IN (?,?)",
                             (old, cutoff, official, telegram))
            store.db.commit()
            config = {**self.config(), "official_catchup_hours": 24}
            config["sources"].append({"name": "Telegram @example", "type": "telegram", "auto_publish": True})
            _, urls, discarded = compose(config, store, cutoff,
                                         window_start_utc=lookback_start(cutoff, 6))
            self.assertEqual(urls, [official])
            self.assertEqual(discarded[0][0], telegram)
            store.close()

    def test_digest_excludes_old_news_first_discovered_this_hour(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now, grace_minutes=0)
            old_url = "https://example.com/old-news"
            self.add_ready(store, old_url, "Old release", "Старый релиз", cutoff)
            old_time = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - timedelta(hours=3)
            store.db.execute("UPDATE items SET published=? WHERE url=?", (format_datetime(old_time), old_url))
            store.db.commit()
            body, urls, discarded = compose(self.config(), store, cutoff,
                                            window_start_utc=previous_hour_start(cutoff))
            self.assertEqual((body, urls), ("", []))
            self.assertEqual(discarded[0][0], old_url)
            self.assertFalse(published_in_window(format_datetime(old_time), previous_hour_start(cutoff), cutoff))
            store.close()

    def test_expired_ready_item_is_never_sent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "db.sqlite3")
            now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
            _, cutoff = due_slot(now)
            url = "https://example.com/release"
            self.add_ready(store, url, "Old release", "Старый релиз", cutoff)
            old = format_datetime(datetime.now(timezone.utc) - timedelta(hours=7))
            store.db.execute("UPDATE items SET published=? WHERE url=?", (old, url))
            store.db.commit()
            with patch("ainews.__main__.read_token", return_value="secret"), patch("ainews.__main__.send_message") as send:
                self.assertEqual(publish_digest(self.config(), store, now=now), [])
                send.assert_not_called()
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url=?", (url,)).fetchone()[0], "skipped")
            store.close()


if __name__ == "__main__":
    unittest.main()
