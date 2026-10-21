"""Regression checks for coverage without relaxing factual verification."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from ainews import daily, pipeline
from ainews.digest import card
from ainews.feeds import Entry
from ainews.presentation import public_text, assert_public_text
from ainews.store import Store


class ClaimRepairTests(unittest.TestCase):
    source = 'Aster released a 7B model for local use. It maintains existing business logic.'

    def draft(self, **extra):
        return {'relevant': True, 'confidence': 'high', 'headline': 'Aster получила обновление',
                'what_happened': 'Выпущена модель Aster с 7 млрд параметров.',
                'simple_explanation': '', 'why_it_matters': '', 'caveat': '',
                'evidence': self.source, **extra}

    def test_optional_data_safety_guarantee_can_be_removed(self):
        original = self.draft(why_it_matters='ПО можно обновлять безопасно без потери данных.')
        repaired, text = pipeline.optional_claim_repair(original, self.source, 'Aster')
        self.assertEqual(repaired['what_happened'], original['what_happened'])
        self.assertEqual(repaired['why_it_matters'], '')
        self.assertIn('7 млрд', text)
        self.assertIn('без потери', original['why_it_matters'])

    def test_unsupported_optional_number_is_not_restored(self):
        original = self.draft(why_it_matters='Разработчики получили 42 миллиона пользователей.')
        repaired, _ = pipeline.optional_claim_repair(original, self.source, 'Aster')
        self.assertEqual(repaired['why_it_matters'], '')

    def test_main_or_restriction_is_never_dropped_by_local_repair(self):
        for field, value in [('what_happened', 'Выпущена модель с 42 млрд параметров.'),
                             ('caveat', 'Доступна только 42 подписчикам.'),
                             ('why_it_matters', 'Лицензия допускает только 42 коммерческих проекта.')]:
            with self.subTest(field=field):
                self.assertIsNone(pipeline.optional_claim_repair(self.draft(**{field: value}), self.source, 'Aster'))

    def test_separate_automatic_handling_and_launch_are_not_auto_launch(self):
        draft = self.draft(simple_explanation='Можно запускать модель локально. Библиотека автоматически обрабатывает историю.')
        self.assertIn('автоматически обрабатывает', pipeline.draft_text(draft, self.source))

    def test_actual_auto_launch_stays_blocked_in_either_order(self):
        for claim in ['Модель запускается автоматически.', 'Библиотека автоматически запускает модель.']:
            with self.subTest(claim=claim), self.assertRaisesRegex(ValueError, 'automatic launch'):
                pipeline.draft_text(self.draft(simple_explanation=claim), self.source)

    def test_competitor_preview_is_not_subject_status(self):
        pipeline.draft_text(self.draft(), self.source,
                            source_title='Aster 1.0 leads the arena, level with Nimbus Preview and ahead of Cloud 4')

    def test_subject_preview_still_requires_qualification(self):
        with self.assertRaisesRegex(ValueError, 'preliminary status'):
            pipeline.draft_text(self.draft(), self.source, source_title='Aster Preview, ahead of Nimbus')

    def test_numeric_repair_cannot_reinsert_wrong_sentences(self):
        original = self.draft(what_happened='Модель содержит 7 млрд параметров. Проведено 42 испытания.')
        edited = self.draft()
        with patch('ainews.pipeline.ollama_json', return_value=edited):
            fixed = pipeline.revise_draft({}, 'Aster', self.source, original, 'Draft contains numbers absent from source')
        self.assertNotIn('42', fixed['what_happened'])

    def test_license_in_explanation_survives_compaction(self):
        fields = {'headline': 'Aster открыла веса модели', 'what': 'Открыты веса модели Aster.',
                  'simple': '', 'why': 'Веса доступны по некоммерческой лицензии.', 'caveat': ''}
        compact = card(fields, max_chars=180, detail_first=True)
        self.assertIn('некоммерческой лицензии', compact)
        self.assertEqual(card(fields, max_chars=60, detail_first=True), '')

    def test_cpp_library_name_survives_link_removal(self):
        for text in ['Запуск через llama.cpp, MLX и Core ML.',
                     'Запуск через [engine.cpp](https://example.test/repo).']:
            result = public_text(text)
            self.assertIn('.cpp', result)
            self.assertNotIn('https', result)
            assert_public_text(result)


class ReleaseMetadataTests(unittest.TestCase):
    url = 'https://github.com/example/aster/releases/tag/v2.0.1'

    def metadata(self, **extra):
        return {'tag_name': 'v2.0.1', 'draft': False, 'prerelease': False,
                'created_at': '2026-10-19T10:00:00Z', 'published_at': '2026-10-19T21:34:39Z', **extra}

    def test_exact_tag_uses_publication_not_commit_creation_or_update(self):
        with patch('ainews.pipeline.download', return_value=(json.dumps(self.metadata()), '')) as request:
            date = pipeline.github_repo_release_date(self.url, '2026-10-20T01:00:00+03:00')
        self.assertEqual(date, '2026-10-19T21:34:39Z')
        self.assertEqual(request.call_args.args[0], 'https://api.github.com/repos/example/aster/releases/tags/v2.0.1')

    def test_future_wrong_prerelease_or_undated_metadata_is_not_evidence(self):
        for data in [self.metadata(published_at='2026-10-21T00:00:00Z'),
                     self.metadata(tag_name='v2.0.2'), self.metadata(prerelease=True),
                     self.metadata(draft=True), self.metadata(published_at=None)]:
            with self.subTest(data=data), patch('ainews.pipeline.download', return_value=(json.dumps(data), '')):
                with self.assertRaises(ValueError):
                    pipeline.github_repo_release_date(self.url, '2026-10-20T00:00:00Z')

    def test_updated_feed_preserves_original_timestamps_and_uses_verified_event(self):
        for age, expected in [(0, 'ready'), (72, 'skipped')]:
            with self.subTest(age=age), tempfile.TemporaryDirectory() as temp:
                store = Store(Path(temp)/'isolated.sqlite3')
                try:
                    posted = datetime.now(timezone.utc)-timedelta(minutes=5)
                    release = posted-timedelta(hours=age)
                    source = ClaimRepairTests.source
                    store.add_feed('official', [Entry('official', 'Aster v2.0.1', self.url,
                                   posted.isoformat(), source, updated=posted.isoformat(), date_kind='updated')], include_existing=True)
                    config = {'publication_mode': 'daily', 'sources': [{'name': 'official', 'auto_publish': True,
                              'hosts': ['github.com'], 'content_from_feed': True}]}
                    with patch('ainews.pipeline.github_repo_release_date', return_value=release.isoformat()), \
                         patch('ainews.pipeline.article_details', return_value=(source, None)), \
                         patch('ainews.pipeline.generate_draft', return_value=ClaimRepairTests().draft()) as writer, \
                         patch('ainews.pipeline.polish_draft', side_effect=lambda c,t,s,d:d), \
                         patch('ainews.pipeline.verify_draft'):
                        pipeline.prepare(config, store, limit=1)
                    row = store.db.execute('SELECT * FROM items').fetchone()
                    dates = store.db.execute('SELECT * FROM source_dates').fetchone()
                    self.assertEqual(row['published'], posted.isoformat())
                    self.assertIsNone(dates['source_published'])
                    self.assertEqual(dates['source_updated'], posted.isoformat())
                    self.assertIsNone(dates['original_published'])
                    self.assertEqual(row['state'], expected, row['error'])
                    if age == 0:
                        self.assertEqual(dates['event_date'], release.isoformat())
                    else:
                        writer.assert_not_called()
                finally:
                    store.close()


class DigestIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'isolated.sqlite3')
        self.now = datetime(2026, 10, 20, 21, tzinfo=daily.MSK)
        self.config = {'publication_mode': 'daily', 'auto_publish': True, 'channel_id': -1,
                       'sources': [{'name': 'official', 'auto_publish': True}]}
        self.sender = Mock(return_value=123)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def add(self, number, *, invalid=False):
        url = f'https://example.test/story/{number}'
        when = (self.now-timedelta(hours=1)).isoformat()
        title = f'Aster-{number+1}.0 добавила новый инструмент'
        body = f'Aster-{number+1}.0 получила инструмент для анализа программ.'
        self.store.add_feed('official', [Entry('official', title, url, when, body)], include_existing=True)
        with self.store.db:
            self.store.db.execute('UPDATE items SET created_at=? WHERE url=?', (when, url))
        draft = f'🧠 {title}\n\nЧто произошло: {body}'
        self.store.set_state(url, 'ready', article=body, draft=draft)
        if invalid:
            row = self.store.db.execute('SELECT * FROM items WHERE url=?', (url,)).fetchone()
            with self.store.db:
                self.store.db.execute('INSERT INTO daily_story_drafts VALUES (?,?)', (daily.fingerprint([row]), 'broken cached JSON'))
        return url

    def publish(self):
        return daily.publish_daily(self.config, self.store, self.root, now=self.now,
                                   token_reader=lambda: 'mock-only', sender=self.sender)

    def test_nine_good_cards_survive_one_bad_cached_card(self):
        good = [self.add(i) for i in range(9)]
        bad = self.add(99, invalid=True)
        self.publish()
        self.sender.assert_called_once()
        self.assertEqual({r[0] for r in self.store.db.execute('SELECT url FROM digest_items')}, set(good))
        row = self.store.db.execute('SELECT state,error FROM items WHERE url=?', (bad,)).fetchone()
        self.assertEqual(row['state'], 'needs_review')
        self.assertIn('Invalid merged draft', row['error'])
        archive = json.loads((self.root/'output/daily/2026-10-20.json').read_text(encoding='utf8'))
        self.assertEqual(archive['telegram_text'], self.sender.call_args.args[2])
        self.assertLessEqual(daily.units(archive['telegram_text']), 3900)
        self.publish()
        self.sender.assert_called_once()

    def test_all_bad_cards_produce_no_reservation_or_empty_post(self):
        self.add(1, invalid=True)
        self.publish()
        self.sender.assert_not_called()
        self.assertIsNone(self.store.digest('daily:2026-10-20'))

    def test_changed_final_payload_is_a_global_failure(self):
        self.add(1)
        edition = daily.compose_daily(self.config, self.store, self.now)
        edition.telegram += '\n\nInjected text.'
        with patch('ainews.daily.compose_daily', return_value=edition):
            report = self.publish()
        self.assertIn('Final payload differs from audited cards', report)
        self.sender.assert_not_called()
        self.assertIsNone(self.store.digest('daily:2026-10-20'))


if __name__ == '__main__':
    unittest.main()
