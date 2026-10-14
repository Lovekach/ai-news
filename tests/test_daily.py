import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from ainews.daily import (MSK, candidates, compose_daily, fingerprint, groups, local_now,
                          merge_stories, prepare_daily, publication_window, publish_daily, units, window)
from ainews.feeds import Entry
from ainews.pipeline import ollama_json
from ainews.store import Store


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'news.db')
        self.now = datetime(2026, 10, 12, 21, tzinfo=MSK)
        self.config = {'publication_mode': 'daily', 'auto_publish': True, 'channel_id': -1,
                       'max_digest_chars': 3900, 'sources': [{'name': 'official', 'auto_publish': True}]}
        self.sender = Mock(return_value=42)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add(self, url='one', headline='GPT-8 новая модель', what='Модель выпущена для работы с документами.',
            when=None, state='ready', caveat=''):
        published = (when or self.now - timedelta(hours=1)).isoformat()
        self.store.add_feed('official', [Entry('official', headline, url, published, what)], include_existing=True)
        draft = f'🧠 {headline}\n\nЧто произошло: {what}\n\nПростыми словами: Можно разобрать документ и найти нужные фрагменты.'
        if caveat:
            draft += '\n\nЧто важно знать: ' + caveat
        self.store.set_state(url, state, article=what, draft=draft)

    def publish(self, now=None):
        return publish_daily(self.config, self.store, self.root, now=now or self.now,
                             token_reader=lambda: 'mock-only', sender=self.sender)

    def test_once_per_moscow_calendar_day(self):
        self.add()
        self.publish()
        self.publish(self.now + timedelta(minutes=2))
        self.sender.assert_called_once()
        self.assertEqual(self.store.digest('daily:2026-10-12')['state'], 'sent')
        self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0], 'sent')

    def test_moscow_independent_of_host_and_utc(self):
        self.assertEqual(local_now(datetime(2026, 10, 12, 18, tzinfo=timezone.utc)), self.now)
        self.assertEqual(window(datetime(2026, 10, 11, 21, tzinfo=timezone.utc))[0], 'daily:2026-10-12')
        with self.assertRaises(ValueError):
            local_now(datetime(2026, 10, 12, 21))

    def test_daily_boundaries_and_invalid_dates(self):
        midnight = self.now.replace(hour=0)
        self.add('before', when=midnight - timedelta(seconds=1))
        self.add('midnight', when=midnight)
        self.add('future', when=self.now + timedelta(seconds=1))
        self.add('today')
        self.store.db.execute("UPDATE items SET published='bad' WHERE url='future'")
        self.store.db.commit()
        self.assertEqual({r['url'] for r in candidates(self.store, self.now, ('ready',))}, {'midnight', 'today'})

    def test_window_is_2056_to_2104_no_late_catchup(self):
        self.add()
        for minutes in (-5, 5, 180):
            self.assertFalse(publication_window(self.now + timedelta(minutes=minutes)))
            self.publish(self.now + timedelta(minutes=minutes))
        self.sender.assert_not_called()
        self.assertTrue(publication_window(self.now - timedelta(minutes=4)))
        self.assertTrue(publication_window(self.now + timedelta(minutes=4)))

    def test_duplicate_events_have_one_current_story_and_all_member_urls(self):
        self.add('early', what='Модель готовится к выпуску.', when=self.now - timedelta(hours=10))
        self.add('late', what='Модель уже выпущена.')
        edition = compose_daily(self.config, self.store, self.now)
        self.assertEqual(edition.stories, 1)
        self.assertEqual(set(edition.urls), {'early', 'late'})
        self.assertIn('уже выпущена', edition.telegram)
        self.assertNotIn('готовится', edition.telegram)
        self.publish()
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM items WHERE state='sent'").fetchone()[0], 2)

    def test_different_model_versions_are_separate(self):
        self.add('one', headline='GPT-8 новая модель')
        self.add('two', headline='GPT-9 новая модель')
        self.assertEqual(compose_daily(self.config, self.store, self.now).stories, 2)

    def test_similar_generic_headlines_do_not_merge_unrelated_tools(self):
        self.add('one', headline='Новый агент для разработки', what='Hermes запускает задачи в отдельной среде.')
        self.add('two', headline='Новый агент для разработки', what='OpenHands ищет ошибки в коде и предлагает исправления.')
        self.assertEqual(compose_daily(self.config, self.store, self.now).stories, 2)

    def test_invalid_and_advertising_drafts_not_published(self):
        self.add('ad', headline='Промокод на курс')
        self.add('bad')
        self.store.set_state('bad', 'ready', draft='Broken format')
        self.publish()
        self.sender.assert_not_called()

    def test_empty_does_not_send_or_reserve(self):
        self.publish()
        self.sender.assert_not_called()
        self.assertIsNone(self.store.digest('daily:2026-10-12'))

    def test_uncertain_delivery_blocks_repeat_and_keeps_ledger(self):
        self.add()
        self.sender.side_effect = TimeoutError('Mock response lost')
        self.publish()
        self.publish()
        self.sender.assert_called_once()
        self.assertEqual(self.store.digest('daily:2026-10-12')['state'], 'send_uncertain')

    def test_missing_token_leaves_drafts_ready(self):
        self.add()
        publish_daily(self.config, self.store, self.root, now=self.now,
                      token_reader=Mock(side_effect=RuntimeError()), sender=self.sender)
        self.assertIsNone(self.store.digest('daily:2026-10-12'))
        self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0], 'ready')

    def test_full_archive_keeps_more_than_telegram_and_no_utf16_overflow(self):
        for index in range(12):
            self.add(str(index), headline=f'GPT-{index+10} новая модель 🧠',
                     what=' '.join(f'В тесте задачи {n} модель обрабатывает документы и находит подтверждённые сведения.'
                                   for n in range(14)),
                     caveat='Доступ пока только в тестовой версии.')
        edition = compose_daily(self.config, self.store, self.now)
        self.assertLessEqual(units(edition.telegram), 3900)
        self.assertGreater(len(edition.full), len(edition.telegram))
        self.assertIn('только в тестовой версии', edition.telegram)
        self.publish()
        saved = json.loads((self.root / 'output/daily/2026-10-12.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['full_text'], edition.full)
        self.assertEqual(len(saved['full_edition_urls']), 12)

    def test_layout_has_bullets_spacing_and_no_internal_labels(self):
        self.add('one')
        self.add('two', headline='GPT-9 новый агент')
        text = compose_daily(self.config, self.store, self.now).telegram
        self.assertTrue(text.startswith('- '))
        self.assertIn('\n\n\n\n- ', text)
        self.assertNotIn('Простыми словами:', text)
        self.assertNotIn('Главное об ИИ', text)

    def test_already_published_facts_are_removed_but_updates_survive(self):
        self.add('old', state='sent')
        self.store.db.execute("UPDATE items SET sent_at=CURRENT_TIMESTAMP WHERE url='old'")
        self.store.db.commit()
        self.add('repeat')
        self.assertEqual(compose_daily(self.config, self.store, self.now).stories, 0)
        self.add('update', what='Модель получила поддержку локального запуска.')
        self.assertEqual(compose_daily(self.config, self.store, self.now).stories, 1)

    def test_merge_uses_production_fact_checker_and_cached_result(self):
        self.add('early', what='Модель готовится к выпуску.')
        self.add('late', what='Модель выпущена.', when=self.now - timedelta(minutes=1))
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'GPT-8 вышла',
                 'what_happened': 'Модель выпущена.', 'simple_explanation': 'Можно работать с документами.',
                 'why_it_matters': '', 'caveats': '', 'evidence': 'Модель выпущена.'}
        with patch('ainews.daily.ollama_json', return_value=draft), \
             patch('ainews.daily.draft_text', return_value='🧠 GPT-8 вышла\n\nЧто произошло: Модель выпущена.'), \
             patch('ainews.daily.verify_draft') as verify:
            merge_stories(self.config, self.store, self.now)
            # Verify every merged claim against original evidence; the latest
            # short notice alone cannot establish details from older sources.
            self.assertEqual(verify.call_count, 1)
        self.assertIn('GPT-8 вышла', compose_daily(self.config, self.store, self.now).telegram)

    def test_failed_merge_falls_back_to_latest_verified_copy(self):
        self.add('early', what='Модель готовится к выпуску.')
        self.add('late', what='Модель выпущена.', when=self.now - timedelta(minutes=1))
        with patch('ainews.daily.ollama_json', side_effect=ValueError('Unsupported claim')):
            merge_stories(self.config, self.store, self.now)
        self.assertNotIn('готовится', compose_daily(self.config, self.store, self.now).telegram)

    def test_daytime_editor_does_not_start_model(self):
        self.add(state='pending')
        with patch('ainews.model_session.model_session') as model:
            prepare_daily(self.config, self.store, self.root, now=self.now.replace(hour=9))
        model.assert_not_called()

    def test_reservation_is_atomic_and_other_connection_cannot_reserve(self):
        self.add()
        other = Store(self.root / 'news.db')
        try:
            self.assertTrue(self.store.reserve_digest('daily:2026-10-12', 'test', ['one'], []))
            self.assertFalse(other.reserve_digest('daily:2026-10-12', 'test', ['one'], []))
        finally:
            other.close()

    def test_production_alias_cannot_trigger_daytime_llm(self):
        from ainews import __main__ as cli
        with patch.object(cli, 'load_config', return_value=self.config), \
             patch.object(cli, 'DB_PATH', self.root / 'cli.db'), \
             patch.object(cli, 'prepare') as prepare, patch.object(cli, 'publish_digest') as publish, \
             patch('sys.argv', ['ainews', 'process-once']):
            cli.main()
        prepare.assert_not_called()
        publish.assert_not_called()

    def test_llm_request_uses_finite_keep_alive_and_deadline(self):
        with patch('ainews.pipeline.time.monotonic', return_value=100), \
             patch('ainews.pipeline.urllib.request.urlopen') as request:
            with self.assertRaises(TimeoutError):
                ollama_json({'model': 'mock', 'ollama_url': 'http://127.0.0.1:11435', '_deadline': 99}, 'test', {})
        request.assert_not_called()

    def test_shared_ollama_address_is_rejected(self):
        from ainews.model_session import model_session
        with self.assertRaises(ValueError), model_session({'ollama_url': 'http://127.0.0.1:11434'}, self.root):
            pass

    def test_occupied_ai_port_is_not_taken_over(self):
        from ainews.model_session import model_session
        with patch('ainews.model_session.socket.socket') as socket, \
             patch('ainews.model_session.subprocess.Popen') as spawn:
            socket.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaises(RuntimeError), model_session({'ollama_url': 'http://127.0.0.1:11435'}, self.root):
                pass
        spawn.assert_not_called()

    def test_owned_process_is_cleaned_up_if_job_assignment_fails(self):
        from ainews.model_session import model_session
        with patch('ainews.model_session.socket.socket') as socket, \
             patch('ainews.model_session.shutil.which', return_value='ollama.exe'), \
             patch('ainews.model_session.WindowsJob') as job, \
             patch('ainews.model_session.subprocess.Popen') as spawn:
            socket.return_value.__enter__.return_value.connect_ex.return_value = 1
            spawn.return_value.poll.return_value = None
            job.return_value.assign.side_effect = RuntimeError('Assignment failure')
            with self.assertRaises(RuntimeError), model_session({'ollama_url': 'http://127.0.0.1:11435'}, self.root):
                pass
            job.return_value.close.assert_called_once()
            spawn.return_value.terminate.assert_called_once()
            spawn.return_value.wait.assert_called_once()


if __name__ == '__main__':
    unittest.main()
