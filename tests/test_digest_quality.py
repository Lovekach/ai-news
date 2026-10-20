"""Regressions for provenance, semantic checks and publication-time quality."""
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

from ainews.daily import MSK, compose_daily, prepare_daily, publish_daily
from ainews.digest import card
from ainews.feeds import Entry, parse_feed
from ainews.pipeline import (draft_text, generate_draft, ollama_json, prepare,
                             github_repo_release_date, normalize_literal_translations)
from ainews.quality import (check_semantic_claims, draft_issues, source_window,
                            event_signature, dated_recap, explicit_event_date)
from ainews.store import Store
from ainews.x_rss import parse_x_rss


class EvidenceQualityTests(unittest.TestCase):
    def test_readme_footer_survives_same_writer_and_verifier_envelope(self):
        text = 'Local semantic search with an embedding model. ' * 220
        text += "SearchApp isn't affiliated with Google or Apple."
        shortened = source_window(text)
        self.assertLessEqual(len(shortened), 7000)
        self.assertIn("SearchApp isn't affiliated", shortened)
        with self.assertRaisesRegex(ValueError, 'unaffiliated'):
            check_semantic_claims(text, 'Google представила приложение SearchApp для поиска файлов.')
        check_semantic_claims(text, 'SearchApp — независимое приложение для поиска файлов.')

    def test_small_merge_envelope_preserves_footer(self):
        text = 'Details about the current release. ' * 300 + 'Forks and mirrors are unchanged.'
        result = source_window(text, 3000)
        self.assertLessEqual(len(result), 3000)
        self.assertIn('Forks and mirrors are unchanged.', result)

    def test_commentator_is_not_product_founder(self):
        source = "Автор поста: Reviewer. I've known Ajay for a while. Promising new entrant. We're launching an eval tool."
        with self.assertRaises(ValueError):
            check_semantic_claims(source, 'Reviewer запустил сервис для оценки агентов.')
        check_semantic_claims(source, 'Reviewer рассказал об инструменте для оценки агентов.')

    def test_product_name_required_in_version_headline(self):
        self.assertIn('Headline names a version without its product',
                      draft_issues('Release v0.21.7', 'Исправлены ошибки.', headline='v0.21.7 исправляет ошибки'))
        self.assertFalse(draft_issues('Release v0.21.7', 'Исправлены ошибки.', headline='Hermes Agent v0.21.7'))

    def test_patch_stability_is_not_a_data_loss_guarantee(self):
        with self.assertRaisesRegex(ValueError, 'data loss'):
            check_semantic_claims('Stable update channel for source installs.', 'Обновления без риска потери данных.')
        check_semantic_claims('Stable update channel for source installs.', 'Канал обновлений стабилизирован.')
        with self.assertRaisesRegex(ValueError, 'data-safety'):
            check_semantic_claims('Local processing on your computer.', 'Поиск работает без риска утечки данных.')

    def test_source_install_policy_keeps_its_scope(self):
        source = 'What ships for source installs. Store and bundled installs are unchanged.'
        with self.assertRaisesRegex(ValueError, 'scope'):
            check_semantic_claims(source, 'Обновления теперь следуют за релизами.')
        check_semantic_claims(source, 'Установки из исходного кода получают обновления, следующие за релизами.')

    def test_benchmark_score_not_automatically_accuracy(self):
        source = '42% on Dense 200, ahead of frontier models in our tests.'
        with self.assertRaisesRegex(ValueError, 'accuracy'):
            check_semantic_claims(source, 'По данным разработчика, точность 42% на Dense 200.')
        with self.assertRaisesRegex(ValueError, 'attribution'):
            check_semantic_claims(source, 'Модель получила 42% на Dense 200 и обошла другие модели.')
        check_semantic_claims(source, 'По данным разработчика, результат на Dense 200 — 42%.')

    def test_benchmark_reshare_cannot_create_a_new_release(self):
        with self.assertRaisesRegex(ValueError, 'new model release'):
            check_semantic_claims('VisionTool scores 42% on Dense 200.', 'Новая модель VisionTool распознаёт объекты.')

    def test_explicit_retrospective_is_held_but_new_development_is_not(self):
        self.assertTrue(dated_recap('Last week, we announced funding and launched a new index.'))
        self.assertFalse(dated_recap('Last week we announced funding. Today we release a new model.'))

    def test_release_note_date_is_not_feed_or_discovery_date(self):
        self.assertEqual(explicit_event_date('Release Date: October 11, 2026 Patch release.'), '2026-10-11')
        self.assertIsNone(explicit_event_date('Detected October 12, 2026.'))

    def test_repo_post_cannot_borrow_a_later_release_date(self):
        releases = [{'published_at':'2026-10-12T16:20:00Z'},
                    {'published_at':'2026-10-09T19:04:00Z'}]
        with patch('ainews.pipeline.download',return_value=(json.dumps(releases),'https://api.github.com')) as request:
            date = github_repo_release_date('https://github.com/Author/SearchApp','2026-10-12T11:52:00Z')
        self.assertEqual(date,'2026-10-09T19:04:00Z')
        self.assertEqual(request.call_args.kwargs['allowed_hosts'],['api.github.com'])
        with patch('ainews.pipeline.download',return_value=(json.dumps(releases[:1]),'')):
            with self.assertRaisesRegex(ValueError,'dated primary'):
                github_repo_release_date('https://github.com/Author/SearchApp','2026-10-12T11:52:00Z')

    def test_repo_metadata_never_fetches_arbitrary_hosts(self):
        with patch('ainews.pipeline.download') as download:
            with self.assertRaises(ValueError):
                github_repo_release_date('https://localhost/Author/SearchApp','2026-10-12T11:52:00Z')
        download.assert_not_called()

    def test_shortening_keeps_vendor_attribution_and_conditions(self):
        fields = {'headline':'VisionTool: результат тестирования',
                  'what':'VisionTool распознаёт объекты. Компания сообщает о результате 42% на Dense 200.',
                  'simple':'Это помогает искать вещи на картинке.', 'why':'', 'caveat':''}
        result = card(fields, max_chars=210, detail_first=True)
        self.assertIn('Компания сообщает', result)
        self.assertIn('Dense 200', result)

    def test_different_speedup_baselines_cannot_be_collapsed_into_range(self):
        source = 'Up to 1.85× speedup over Colocate, 1.78× over Async.'
        with self.assertRaisesRegex(ValueError, 'baselines'):
            check_semantic_claims(source, 'Ускорение в 1,78–1,85 раза по сравнению с Async.')
        check_semantic_claims(source, 'Ускорение до 1,85 раза относительно Colocate и в 1,78 раза относительно Async.')
        with self.assertRaisesRegex(ValueError, 'wrong baseline'):
            check_semantic_claims(source, 'Ускорение в 1,85 раза относительно Async и в 1,78 раза относительно Colocate.')

    def test_quantified_results_survive_shortening_from_explanatory_field(self):
        fields = {'headline':'TrainingTool', 'what':'Инструмент обучает агентов.',
                  'simple':'Поддерживаются разные задачи.',
                  'why':'В тесте ускорение — 1,85 раза относительно Colocate.', 'caveat':''}
        text = card(fields,max_chars=160,detail_first=True)
        self.assertIn('1,85 раза относительно Colocate',text)

    def test_evaluation_organization_name_is_not_translated_literally(self):
        with self.assertRaisesRegex(ValueError, 'proper name'):
            check_semantic_claims('Artificial Analysis Intelligence Index scores.',
                                  'Рост показателей в тестах искусственного анализа.')

    def test_literal_repairs_require_the_original_term(self):
        self.assertEqual(normalize_literal_translations('Исходные установки получают обновления.',
                                                        'Policy for source installs.'),
                         'Установки из исходного кода получают обновления.')
        self.assertEqual(normalize_literal_translations('В тестах искусственного анализа.',
                                                        'Artificial Analysis Intelligence Index.'),
                         'В тестах Artificial Analysis.')
        self.assertEqual(normalize_literal_translations('Задача искусственного анализа.',
                                                        'A generic task.'),
                         'Задача искусственного анализа.')
        self.assertEqual(normalize_literal_translations('Работает за корпоративными фаерволами.',
                                                        'Updates no longer fail behind some firewalls.'),
                         'Работает за некоторыми фаерволами.')
        self.assertEqual(normalize_literal_translations('Обучение агентов на сверхдлинных горизонтах.',
                                                        'Long-horizon agent training.'),
                         'Обучение агентов длинным многошаговым задачам.')

    def test_observed_temporal_and_time_reduction_translations(self):
        source = 'A release gap of only 6 weeks. Cutting end-to-end training time by ~44% vs Async.'
        wrong = 'За шесть недель до релиза предшественника получили результат.'
        with self.assertRaisesRegex(ValueError,'Release gap'):
            check_semantic_claims(source, wrong)
        self.assertEqual(normalize_literal_translations(wrong,source),
                         'Через 6 недель после релиза предшественника получили результат.')
        wrong = 'Система ускорила обучение примерно на 44% по сравнению с Async.'
        with self.assertRaisesRegex(ValueError,'training time'):
            check_semantic_claims(source,wrong)
        self.assertEqual(normalize_literal_translations(wrong,source),
                         'Система сократила время обучения примерно на 44% по сравнению с Async.')
        self.assertEqual(normalize_literal_translations(wrong,'Different evidence.'),wrong)

    def test_x_quoted_launch_keeps_speakers_separate(self):
        xml = '''<rss><channel><item><title>Interesting tool</title>
          <link>https://nitter.net/Reviewer/status/123456789</link>
          <pubDate>Mon, 12 Oct 2026 14:00:00 GMT</pubDate>
          <description><![CDATA[<p>I've known Ajay for a while.</p><div class="quote">
          <a href="https://x.com/Builder/status/123456788">Builder</a>
          <p>We're launching EvalTool.</p></div>]]></description></item></channel></rss>'''
        summary = parse_x_rss(xml, {'name':'X reviewer', 'handle':'Reviewer'})[0].summary
        self.assertIn('[Начало цитируемого поста]', summary)
        self.assertIn('Источник цитаты: https://x.com/Builder/status/', summary)
        self.assertIn('[Конец цитируемого поста]', summary)

    def test_writer_prompt_does_not_assert_product_authorship(self):
        with patch('ainews.pipeline.ollama_json', return_value={}) as model:
            generate_draft({'_source_url':'https://github.com/Author/SearchApp'}, 'A search app',
                           'Author made a local search app.', source_author='Reviewer')
        prompt = model.call_args.args[1]
        self.assertIn('не обязательно разработчик', prompt)
        self.assertIn('https://github.com/Author/SearchApp', prompt)
        self.assertNotIn('Это собственный пост автора', prompt)

    def test_patch_versions_and_benchmarks_are_not_merged_indiscriminately(self):
        self.assertNotEqual(event_signature('Hermes Agent v0.21.7', ''),
                            event_signature('Hermes Agent v0.21.8', ''))
        self.assertNotEqual(event_signature('Le Chonk: новый релиз', ''),
                            event_signature('Le Chonk: benchmark Dense 200', ''))

    def test_truncated_json_retries_once_without_accepting_partial_facts(self):
        config = {'model':'mock', 'ollama_url':'http://127.0.0.1:11435'}
        bad = {'response':'{"supported":', 'done_reason':'length'}
        good = {'response':'{"supported":true,"unsupported_claims":[]}', 'done_reason':'stop'}
        responses = [io.BytesIO(json.dumps(x).encode()) for x in (bad,good)]
        with patch('ainews.pipeline.urllib.request.urlopen', side_effect=responses) as request:
            result = ollama_json(config, 'Verify only source facts.', {}, max_predict=350)
        self.assertTrue(result['supported'])
        self.assertEqual(request.call_count, 2)
        second = json.loads(request.call_args.args[0].data)
        self.assertEqual(second['options']['num_predict'], 1050)
        with patch('ainews.pipeline.urllib.request.urlopen', side_effect=[io.BytesIO(json.dumps(bad).encode()) for _ in range(2)]) as request:
            with self.assertRaises(json.JSONDecodeError):
                ollama_json(config, 'Verify.', {}, max_predict=350)
        self.assertEqual(request.call_count, 2)

    def test_decimal_comma_keeps_the_same_number(self):
        source = 'The evaluation result is 44.4 percent on the test.'
        draft = dict(relevant=True, confidence='high', headline='Результат теста',
                     what_happened='Результат — 44,4 процента.', simple_explanation='', why_it_matters='',
                     caveat='', evidence=source)
        self.assertIn('44,4', draft_text(draft, source))


class DigestGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'news.db')
        self.now = datetime(2026,10,12,21,tzinfo=MSK)
        self.config = {'publication_mode':'daily','auto_publish':True,'channel_id':-1,
                       'sources':[{'name':'official','auto_publish':True}]}

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add(self, source, draft):
        self.store.add_feed('official',[Entry('official','SearchApp','https://example.com/app',(self.now-timedelta(minutes=1)).isoformat(),source)],include_existing=True)
        with self.store.db:
            self.store.db.execute('UPDATE items SET created_at=?',
                                 ((self.now-timedelta(minutes=1)).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),))
        self.store.set_state('https://example.com/app','ready',article=source,draft=draft)

    def test_previously_approved_wrong_attribution_is_held_without_send(self):
        self.add("SearchApp isn't affiliated with Google or Apple.",
                 '🧠 SearchApp\n\nЧто произошло: Google представила приложение SearchApp.')
        sender = Mock()
        report = publish_daily(self.config,self.store,self.root,now=self.now,token_reader=lambda:'mock-only',sender=sender)
        sender.assert_not_called()
        self.assertIn('No verified news: no empty post published',report)
        self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0],'needs_review')
        self.assertIsNone(self.store.digest('daily:2026-10-12'))

    def test_atom_update_does_not_replace_event_or_original_date(self):
        entry = parse_feed('''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>SearchApp</title>
            <link href="https://example.com/app"/><published>2026-10-11T10:00:00Z</published>
            <updated>2026-10-12T10:00:00Z</updated></entry></feed>''','official')[0]
        self.store.add_feed('official',[entry],include_existing=True)
        self.store.record_source_dates(entry.url, original_published='2026-10-11')
        dates = self.store.db.execute('SELECT * FROM source_dates').fetchone()
        self.assertEqual(dates['source_published'],'2026-10-11T10:00:00Z')
        self.assertEqual(dates['source_updated'],'2026-10-12T10:00:00Z')
        self.assertIsNone(dates['event_date'])
        self.assertFalse(compose_daily(self.config,self.store,self.now).urls)

    def test_additive_upgrade_preserves_news_and_ledger(self):
        self.add('Source text.', '🧠 SearchApp\n\nЧто произошло: Приложение ищет файлы.')
        self.assertTrue(self.store.reserve_digest('daily:2026-10-12','Archived text.',['https://example.com/app'],[]))
        self.store.finish_digest('daily:2026-10-12',message_id=42)
        self.store.db.execute('DROP TABLE source_dates')
        self.store.db.execute('CREATE TABLE source_dates (url TEXT PRIMARY KEY,source_published TEXT,source_updated TEXT,original_published TEXT,event_date TEXT)')
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.root/'news.db')
        self.assertEqual(self.store.digest('daily:2026-10-12')['telegram_message_id'],42)
        self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0],'sent')
        self.assertIn('date_kind',[r[1] for r in self.store.db.execute('PRAGMA table_info(source_dates)')])

    def test_transient_article_failure_gets_only_one_retry_without_llm(self):
        self.store.add_feed('official',[Entry('official','New tool','https://example.com/tool',
                          datetime.now(MSK).isoformat(),'Brief')],include_existing=True)
        config = {**self.config, 'sources':[{'name':'official','auto_publish':True,'hosts':['example.com']}]}
        with patch('ainews.pipeline.article_details',side_effect=URLError('TLS handshake timeout')), \
             patch('ainews.pipeline.generate_draft') as generate:
            prepare(config,self.store,limit=1,candidate_urls=['https://example.com/tool'])
            self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0],'pending')
            prepare(config,self.store,limit=1,candidate_urls=['https://example.com/tool'])
        self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0],'needs_review')
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM editorial_audit WHERE stage='fetch_retry'").fetchone()[0],1)
        generate.assert_not_called()

    def test_repo_release_date_is_not_stored_as_readme_publication(self):
        now = datetime.now(MSK)
        entry = Entry('tg','A search app','https://t.me/sample/1',now.isoformat(),
                      'Independent search app https://github.com/Author/SearchApp')
        self.store.add_feed('tg',[entry],include_existing=True)
        config = {**self.config,'sources':[{'name':'tg','type':'telegram','auto_publish':True}]}
        old = (now-timedelta(days=3)).isoformat()
        with patch('ainews.pipeline.article_details',return_value=('Independent app README.',None)), \
             patch('ainews.pipeline.github_repo_release_date',return_value=old), \
             patch('ainews.pipeline.generate_draft') as generate:
            prepare(config,self.store,limit=1,candidate_urls=[entry.url])
        dates = self.store.db.execute('SELECT * FROM source_dates WHERE url=?',(entry.url,)).fetchone()
        self.assertEqual(dates['source_published'],entry.published)
        self.assertEqual(dates['event_date'],old)
        self.assertIsNone(dates['original_published'])
        generate.assert_not_called()

    def test_final_editor_waits_without_gpu_and_picks_up_late_arrival(self):
        start = self.now.replace(hour=20,minute=50)
        self.store.add_feed('official',[Entry('official','First model','one',(start-timedelta(seconds=1)).isoformat(),'News')],include_existing=True)
        with self.store.db:
            self.store.db.execute('UPDATE items SET created_at=?',
                                 ((start-timedelta(seconds=1)).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),))
        clock = [100.0]
        active = []
        from contextlib import contextmanager
        @contextmanager
        def model(config, root):
            active.append(True)
            try: yield
            finally: active.pop()
        def prepared(config,store,**kwargs):
            for url in kwargs['candidate_urls']:
                store.set_state(url,'skipped',error='Mock irrelevant')
            return ['processed']
        def sleep(seconds):
            self.assertFalse(active, 'GPU session must be closed before waiting')
            clock[0] += 300
            if clock[0] == 400:
                self.store.add_feed('official',[Entry('official','Late model','two',(start-timedelta(seconds=1)).isoformat(),'News')],include_existing=True)
                with self.store.db:
                    self.store.db.execute('UPDATE items SET created_at=? WHERE url=?',
                                         ((start-timedelta(seconds=1)).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), 'two'))
        with patch('ainews.daily.local_now',return_value=start), \
             patch('ainews.daily.time.monotonic',side_effect=lambda:clock[0]), \
             patch('ainews.daily.time.sleep',side_effect=sleep), \
             patch('ainews.model_session.model_session',side_effect=model) as sessions, \
             patch('ainews.daily.prepare',side_effect=prepared) as prepare_mock, \
             patch('ainews.daily.merge_stories',return_value=[]):
            prepare_daily(self.config,self.store,self.root)
        self.assertEqual(sessions.call_count,2)
        self.assertEqual(prepare_mock.call_args.kwargs['candidate_urls'],['two'])

    def test_final_editor_waits_even_when_initial_queue_is_empty(self):
        # Covered by the same bounded wait path: no candidates must not cause
        # the 20:50 task to exit before a genuinely late announcement arrives.
        with patch('ainews.daily.local_now',return_value=self.now.replace(hour=20,minute=50)), \
             patch('ainews.daily.time.monotonic',side_effect=[100,100,100,700]), \
             patch('ainews.daily.time.sleep') as sleep, \
             patch('ainews.model_session.model_session') as model:
            prepare_daily(self.config,self.store,self.root)
        model.assert_not_called()
        sleep.assert_called_once()


if __name__ == '__main__':
    unittest.main()
