import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ainews import pipeline
from ainews.daily import priority
from ainews.editorial import event_key, decision
from ainews.feeds import Entry
from ainews.store import Store


SOURCE = ('AcmeRunner v2.3 is out! 🧭 Parser fixes for structured responses '
          '🛠 Legacy loader stays optional for existing users '
          '⚡ Startup profiling is available for maintainers')
SPLICED = ('🧭 Parser fixes for structured responses '
           '⚡ Startup profiling is available for maintainers')


class EvidenceBulletTests(unittest.TestCase):
    def test_flattened_bullets_restore_only_one_exact_source_slice(self):
        result = pipeline.align_evidence({'evidence': SPLICED}, SOURCE)
        self.assertNotEqual(result['evidence'], SPLICED)
        self.assertIn(result['evidence'], SOURCE)
        self.assertGreaterEqual(len(result['evidence']), 25)

    def test_currency_and_math_are_not_bullet_separators(self):
        source = 'The price is $0.75 per million tokens with a measured 1.5× throughput increase.'
        evidence = 'The price is $0.75 per thousand tokens with a measured 1.5× throughput increase'
        self.assertEqual(pipeline.align_evidence({'evidence': evidence}, source)['evidence'], evidence)

    def test_unmatched_bullets_remain_invalid(self):
        evidence = '🧭 Invented capabilities that are nowhere in the source ⚡ Unsupported promises about free hardware'
        self.assertEqual(pipeline.align_evidence({'evidence': evidence}, SOURCE)['evidence'], evidence)

    def test_changed_unit_does_not_become_literal_evidence(self):
        source = 'The temperature is 26°C and the sustained throughput is measured per second'
        evidence = 'The temperature is 25°C and the sustained throughput is measured per minute'
        self.assertEqual(pipeline.align_evidence({'evidence': evidence}, source)['evidence'], evidence)

    def test_recovered_literal_cannot_bypass_semantic_verifier(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Store(Path(folder)/'test.db')
            try:
                url = 'https://x.com/acme/status/1'
                db.add_feed('official', [Entry('official', 'AcmeRunner v2.3 is out!', url,
                    datetime.now(timezone.utc).isoformat(), SOURCE)], include_existing=True)
                draft = {'relevant':True,'confidence':'high','headline':'AcmeRunner v2.3 получил обновление',
                         'what_happened':'Вышла версия AcmeRunner v2.3 с исправлениями.',
                         'simple_explanation':'','why_it_matters':'','caveat':'','evidence':SPLICED}
                cfg = {'publication_mode':'daily','sources':[{'name':'official','type':'x','primary_account':True,'auto_publish':True}]}
                with patch('ainews.pipeline.generate_draft', return_value=draft), \
                     patch('ainews.pipeline.polish_draft', side_effect=lambda *args:args[3]), \
                     patch('ainews.pipeline.revise_draft', side_effect=lambda *args:args[3]), \
                     patch('ainews.pipeline.verify_draft', side_effect=ValueError('Unsupported test claim')) as verifier:
                    pipeline.prepare(cfg,db,limit=1,candidate_urls=[url])
                verifier.assert_called_once()
                self.assertEqual(db.db.execute('SELECT state FROM items WHERE url=?',(url,)).fetchone()[0],'needs_review')
            finally:
                db.close()

    def test_common_release_and_availability_assertions_get_event_priority(self):
        def row(title):return {'url':'https://x.com/acme/status/1','title':title,'summary':''}
        reference = priority(row('Existing service documentation'))
        self.assertGreater(priority(row('AcmeRunner v2.3 is out!')),reference)
        self.assertGreater(priority(row('AcmeRunner v2.3 is on an inference platform')),reference)

    def test_git_tag_identity_is_case_sensitive(self):
        def row(tag):return {'url':'https://github.com/Acme/Tool/releases/tag/'+tag,'title':tag,'summary':''}
        self.assertNotEqual(event_key(row('v2.3.4')),event_key(row('V2.3.4')))
        self.assertEqual(event_key(row('v2.3.4%2Bbuild')),event_key(row('v2.3.4+build')))

    def test_russian_weekly_digest_requires_current_event_evidence(self):
        for title in ('Нейродайджест за неделю', 'Недельный дайджест инструментов'):
            row = {'url':'https://example.com/recap','title':title,'summary':''}
            self.assertEqual(decision(row)['eligibility'],'needs_event_evidence')
            row['summary'] = 'Сегодня выпустили обновление AcmeRunner v2.3.'
            self.assertEqual(decision(row)['eligibility'],'pending_existing_checks')

    def test_verified_tag_date_still_obeys_24_hour_freshness(self):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):
                return datetime(2026,10,21,17,tzinfo=timezone.utc).astimezone(tz or timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            db = Store(Path(folder)/'test.db')
            try:
                url = 'https://github.com/acme/runner/releases/tag/v2.3.0'
                db.add_feed('official',[Entry('official','v2.3.0',url,'2026-10-20T19:00:00Z',SOURCE)],include_existing=True)
                with db.db:
                    db.db.execute("UPDATE source_dates SET date_kind='updated' WHERE url=?",(url,))
                cfg={'publication_mode':'daily','sources':[{'name':'official','type':'rss','content_from_feed':True,'auto_publish':True}]}
                with patch('ainews.pipeline.datetime',Clock), \
                     patch('ainews.pipeline.github_repo_release_date',return_value='2026-10-20T00:00:00Z'), \
                     patch('ainews.pipeline.generate_draft') as writer:
                    pipeline.prepare(cfg,db,limit=1,candidate_urls=[url])
                writer.assert_not_called()
                self.assertEqual(db.db.execute('SELECT state FROM items WHERE url=?',(url,)).fetchone()[0],'skipped')
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
