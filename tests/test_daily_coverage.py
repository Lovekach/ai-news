"""Cutoff, discovery and unconsumed-backlog regressions; no live services."""
import json
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

import test_daily
from ainews.daily import MSK, candidates, compose_daily, prepare_daily, publish_daily, window


class CoverageTests(TestCase):
    setUp = test_daily.DailyTests.setUp
    tearDown = test_daily.DailyTests.tearDown
    add = test_daily.DailyTests.add
    publish = test_daily.DailyTests.publish

    def discover(self, url, when):
        with self.store.db:
            self.store.db.execute('UPDATE items SET created_at=? WHERE url=?',
                (when.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), url))

    def urls(self, now=None, states=('ready',)):
        return {r['url'] for r in candidates(self.store, now or self.now, states)}

    def test_adjacent_windows_share_exact_2100_cutoff(self):
        today = window(self.now)
        tomorrow = window(self.now + timedelta(days=1))
        self.assertEqual(today, ('daily:2026-10-12', '2026-10-11 18:00:00', '2026-10-12 18:00:00'))
        self.assertEqual(today[2], tomorrow[1])
        self.assertEqual(window(self.now + timedelta(minutes=4)), today)
        self.assertEqual(window(self.now - timedelta(minutes=10))[2], '2026-10-12 17:50:00')

    def test_205959_210000_2105_belong_to_adjacent_editions(self):
        for name, delta in [('before', -1), ('exact', 0), ('after', 300)]:
            self.add(name, when=self.now + timedelta(seconds=delta))
        self.assertEqual(self.urls(), {'before'})
        self.assertEqual(self.urls(self.now + timedelta(minutes=4)), {'before'})
        # Candidate inclusion is separate from the unchanged 24h quality gate.
        self.assertEqual(self.urls(self.now + timedelta(days=1)), {'exact', 'after'})

    def test_anthropic_style_evening_announcement_survives_midnight(self):
        when = self.now + timedelta(minutes=5, seconds=5)
        self.add('announcement', when=when, state='pending')
        self.discover('announcement', self.now + timedelta(minutes=11, seconds=16))
        self.assertFalse(self.urls(states=('pending',)))
        self.assertEqual(self.urls(self.now + timedelta(days=1), ('pending',)), {'announcement'})

    def test_late_discovery_preserves_both_dates_and_has_no_retroactive_knowledge(self):
        published = self.now - timedelta(minutes=1)
        self.add('late', when=published)
        self.discover('late', self.now + timedelta(minutes=5))
        original = dict(self.store.db.execute('SELECT * FROM items').fetchone())
        self.assertFalse(self.urls())
        following_editor = self.now + timedelta(hours=21)
        self.assertEqual(self.urls(following_editor), {'late'})
        self.assertEqual(compose_daily(self.config, self.store, following_editor).urls, ['late'])
        self.assertEqual(dict(self.store.db.execute('SELECT * FROM items').fetchone()), original)

    def test_late_discovery_does_not_make_an_old_approved_story_fresh(self):
        self.add('stale', when=self.now - timedelta(days=5))
        self.discover('stale', self.now - timedelta(minutes=1))
        self.assertEqual(self.urls(), {'stale'})
        self.assertFalse(compose_daily(self.config, self.store, self.now).urls)
        self.publish()
        self.sender.assert_not_called()
        self.assertIsNone(self.store.digest('daily:2026-10-12'))

    def test_missed_edition_recovers_fresh_backlog_without_replaying_old_news(self):
        # No ledger for the missed day is created or moved forward.
        self.add('fresh', when=self.now - timedelta(hours=23))
        self.add('expired', when=self.now - timedelta(days=2))
        self.assertEqual(self.urls(), {'fresh'})
        self.publish()
        self.assertEqual(self.store.digest('daily:2026-10-12')['state'], 'sent')
        self.assertIsNone(self.store.digest('daily:2026-10-11'))
        self.publish()
        self.sender.assert_called_once()

    def test_unprocessed_tail_before_previous_cutoff_is_seen_by_next_editor(self):
        self.add('tail', when=self.now - timedelta(days=1, seconds=30), state='pending')
        self.assertEqual(self.urls(self.now - timedelta(hours=3), ('pending',)), {'tail'})

    def test_future_publication_or_future_discovery_cannot_enter_edition(self):
        self.add('future-publication', when=self.now + timedelta(hours=1))
        self.discover('future-publication', self.now - timedelta(hours=1))
        self.add('future-discovery')
        self.discover('future-discovery', self.now + timedelta(seconds=1))
        self.assertFalse(self.urls())

    def test_invalid_dates_fail_closed_and_empty_state_filter_is_safe(self):
        self.add('bad')
        with self.store.db:
            self.store.db.execute("UPDATE items SET created_at='unknown'")
        self.assertFalse(self.urls())
        self.assertFalse(self.urls(states=()))

    def test_daily_ledger_blocks_used_url_even_if_item_state_was_reset(self):
        self.add('used')
        self.publish()
        self.store.set_state('used', 'ready')
        self.assertFalse(self.urls())
        self.assertFalse(self.urls(self.now + timedelta(days=1)))
        self.sender.assert_called_once()

    def test_uncertain_delivery_members_cannot_enter_another_edition(self):
        self.add('used')
        self.sender.side_effect = TimeoutError('mock')
        self.publish()
        self.store.set_state('used', 'ready')
        self.assertFalse(self.urls())
        self.assertEqual(self.store.digest('daily:2026-10-12')['state'], 'send_uncertain')

    def test_old_calendar_ledger_upgrade_keeps_history_and_unconsumed_evening_news(self):
        previous = self.now - timedelta(days=1)
        self.add('old-receipt', when=previous - timedelta(hours=1),
                 headline='Компания открыла офис', what='Открыт новый офис компании.')
        self.assertTrue(self.store.reserve_digest('daily:2026-10-11', 'Old archive.', ['old-receipt'], []))
        self.store.finish_digest('daily:2026-10-11', message_id=9)
        old = tuple(self.store.digest('daily:2026-10-11'))
        self.add('evening', when=previous + timedelta(minutes=5))
        self.assertEqual(self.urls(), {'evening'})
        self.publish()
        self.assertEqual(tuple(self.store.digest('daily:2026-10-11')), old)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM digest_items').fetchone()[0], 2)
        archive = json.loads((self.root/'output/daily/2026-10-12.json').read_text(encoding='utf8'))
        self.assertEqual(archive['provenance'][0]['source_published'], (previous+timedelta(minutes=5)).isoformat())
        self.assertEqual(archive['coverage_window']['start'], '2026-10-11 18:00:00')

    def test_evening_editor_passes_evening_candidates_to_existing_prepare(self):
        self.add('evening', when=self.now-timedelta(hours=23), state='pending')
        with patch('ainews.model_session.model_session'), \
             patch('ainews.daily.prepare', return_value=[]) as prepare, \
             patch('ainews.daily.merge_stories', return_value=[]):
            prepare_daily(self.config, self.store, self.root, now=self.now-timedelta(hours=1))
        self.assertEqual(prepare.call_args.kwargs['candidate_urls'], ['evening'])

    def test_old_late_pending_still_fails_existing_age_gate_before_llm(self):
        self.add('old', when=self.now-timedelta(days=3), state='pending')
        self.discover('old', self.now-timedelta(minutes=2))
        from ainews.pipeline import prepare
        config = {**self.config, 'sources': [{'name': 'official', 'auto_publish': True}]}
        with patch('ainews.pipeline.generate_draft') as writer:
            prepare(config, self.store, candidate_urls=list(self.urls(states=('pending',))), limit=1)
        writer.assert_not_called()
        self.assertEqual(self.store.db.execute('SELECT state FROM items').fetchone()[0], 'skipped')
