import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from ainews import daily, pipeline
from ainews.editorial import decision, event_key, queue
from ainews.feeds import Entry
from ainews.store import Store


def row(title, url='https://x.com/vendor/status/1', summary='', **extra):
    return dict(url=url, title=title, summary=summary, published='2026-10-18T12:00:00Z',
                source='official', draft=None, article=None, **extra)


class EditorialQueueTests(unittest.TestCase):
    def test_priority_does_not_depend_on_generated_length(self):
        a = row('Acme V7.2 is here!')
        b = {**a, 'draft': 'api model agent open source research ' * 100}
        self.assertEqual(daily.priority(a), daily.priority(b))

    def test_current_evaluation_precedes_weekly_recap(self):
        self.assertGreater(daily.priority(row('Acme is #1 in the Code Arena')),
                           daily.priority(row('This Week in the Arena: new models and updates')))

    def test_no_company_ranking(self):
        self.assertEqual(daily.priority(row('UnknownCo V2.3 is here!')),
                         daily.priority(row('OpenAI V2.3 is here!')))

    def test_full_version_preserved_and_distinct(self):
        a = event_key(row('Acme-V4.1-Flash-1017 is here!'))
        b = event_key(row('Acme V4.1 Flash 1017 is here!'))
        self.assertEqual(a, b)
        self.assertNotEqual(a, event_key(row('Acme-V4.1-Flash-1018 is here!')))

    def test_incidental_cost_does_not_split_release(self):
        self.assertEqual(event_key(row('Acme V4.1 is here! Better performance and cost')),
                         event_key(row('Acme V4.1 new model')))
        self.assertNotEqual(event_key(row('Acme V4.1 price reduction')),
                            event_key(row('Acme V4.1 is here!')))

    def test_integrations_remain_distinct(self):
        self.assertNotEqual(event_key(row('Qwen3.6 support on Ollama')),
                            event_key(row('Qwen3.6 support on vLLM')))

    def test_quoted_release_does_not_override_integration_or_benchmark(self):
        a = row('Acme V2.3 support on Ollama')
        b = row('Acme V2.3 support on vLLM')
        a['article'] = b['article'] = 'Acme V2.3 is here! New model release.'
        self.assertNotEqual(event_key(a), event_key(b))
        c = row('Acme V2.3 benchmark results')
        c['article'] = a['article']
        self.assertNotEqual(event_key(c), event_key(row('Acme V2.3 is here!')))
        a['title'] = 'Acme V2.3 available on Ollama'
        b['title'] = 'Acme V2.3 available on vLLM'
        self.assertNotEqual(event_key(a), event_key(b))

    def test_generic_company_names_do_not_create_identity(self):
        self.assertIsNone(event_key(row('Acme introduces a useful tool')))

    def test_patch_feed_titles_use_repository_and_full_tag(self):
        a = row('v2.1.302', 'https://github.com/acme/tool/releases/tag/v2.1.302')
        b = row('v2.1.303', 'https://github.com/acme/tool/releases/tag/v2.1.303')
        self.assertNotEqual(event_key(a), event_key(b))

    def test_primary_representative_first_but_alternatives_retained(self):
        a = row('Acme V2.3 is here!', source_name='unused')
        a['source'] = 'repost';a['url'] += '0'
        b = {**a, 'source': 'official', 'url': a['url'] + '1'}
        c = row('Other V3.0 is here!');c['url'] += '2'
        ordered = queue([a,b,c], {'official': {'primary_account': True}})
        self.assertLess(ordered.index(b), ordered.index(a))
        self.assertLess(ordered.index(c), ordered.index(a))
        self.assertEqual(len(ordered), 3)

    def test_eligibility_verifiability_and_priority_are_separate(self):
        d = decision(row('Acme V2.3 is here!', summary='An unconfirmed claim'))
        self.assertEqual(d['verifiability'], 'unresolved')
        self.assertEqual(d['eligibility'], 'pending_existing_checks')
        self.assertGreater(d['priority'], 50)

    def test_exact_tag_metadata_rejects_wrong_or_future_release(self):
        url = 'https://github.com/acme/tool/releases/tag/v2.3.4'
        for payload in ({'tag_name':'v2.3.5'}, {'tag_name':'v2.3.4','published_at':'2026-10-19T12:00:00Z'}):
            with patch('ainews.pipeline.download', return_value=(json.dumps(payload), url)):
                with self.assertRaises(ValueError):
                    pipeline.github_repo_release_date(url, '2026-10-18T12:00:00Z')

    def test_exact_tag_uses_published_not_created_or_updated(self):
        url = 'https://github.com/acme/tool/releases/tag/v2.3.4'
        payload = {'tag_name':'v2.3.4','published_at':'2026-10-18T11:00:00Z',
                   'created_at':'2020-01-01T00:00:00Z','updated_at':'2026-10-19T00:00:00Z'}
        with patch('ainews.pipeline.download', return_value=(json.dumps(payload), url)):
            self.assertEqual(pipeline.github_repo_release_date(url, '2026-10-18T12:00:00Z'), payload['published_at'])


class EditorialIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name)
        self.db = Store(self.root/'test.db')
        self.cfg = {'publication_mode':'daily','sources':[{'name':'official','type':'x','primary_account':True,'auto_publish':True}]}

    def tearDown(self):
        self.db.close();self.tmp.cleanup()

    def add(self, title, summary, url='https://x.com/acme/status/2', published='2026-10-18T12:00:00Z'):
        self.db.add_feed('official',[Entry('official',title,url,published,summary)],include_existing=True)
        return url

    def test_recap_held_without_llm_or_losing_source(self):
        url = self.add('This Week in the Arena: updates', 'A weekly list of positions.')
        with patch('ainews.pipeline.generate_draft') as writer:
            pipeline.prepare(self.cfg,self.db,limit=1,candidate_urls=[url])
        writer.assert_not_called()
        saved = self.db.db.execute('SELECT * FROM items WHERE url=?',(url,)).fetchone()
        self.assertEqual(saved['state'],'needs_review')
        self.assertEqual(saved['summary'],'A weekly list of positions.')

    def test_old_quote_checked_against_retained_original_before_llm(self):
        original = self.add('Acme launch','Original release.', 'https://x.com/acme/status/1','2026-10-13T12:00:00Z')
        with self.db.db:self.db.db.execute("UPDATE items SET state='baseline' WHERE url=?",(original,))
        url = self.add('Комментарий аккаунта acme', 'Комментарий аккаунта acme:\n[Начало цитируемого поста]\nIntroducing Acme!\nhttps://mirror.example/acme/status/1#m')
        with patch('ainews.pipeline.generate_draft') as writer:
            pipeline.prepare(self.cfg,self.db,limit=1,candidate_urls=[url])
        writer.assert_not_called()
        self.assertEqual(self.db.db.execute('SELECT state FROM items WHERE url=?',(url,)).fetchone()[0],'skipped')

    def test_deadline_still_prevents_any_processing(self):
        url = self.add('Acme V2.3 is here!','Current model.')
        with patch('ainews.pipeline.generate_draft') as writer:
            pipeline.prepare({**self.cfg,'_deadline':0},self.db,limit=1,candidate_urls=[url])
        writer.assert_not_called()
        self.assertEqual(self.db.db.execute('SELECT state FROM items WHERE url=?',(url,)).fetchone()[0],'pending')

    def test_cached_repost_does_not_start_another_gpu_session(self):
        url = self.add('Acme V2.3 is here!', 'Acme V2.3 is here!')
        other = self.add('Acme V2.3 new model', 'Acme V2.3 is here!', 'https://x.com/acme/status/3')
        draft = '🧠 Acme V2.3 выпущена\n\nЧто произошло: Вышла модель Acme V2.3.'
        self.db.set_state(url,'ready',article='Acme V2.3 is here!',draft=draft)
        self.db.set_state(other,'pending',article='Acme V2.3 is here!')
        with self.db.db:
            self.db.db.execute("UPDATE items SET created_at='2026-10-18 12:00:00'")
        with patch('ainews.model_session.model_session') as model:
            daily.prepare_daily(self.cfg,self.db,self.root,now=datetime(2026,10,18,20,15,tzinfo=daily.MSK))
        model.assert_not_called()
        self.assertEqual(self.db.db.execute('SELECT state FROM items WHERE url=?',(other,)).fetchone()[0],'pending')

    def test_malformed_ready_row_cannot_starve_valid_alternative(self):
        url = self.add('Acme V2.3 is here!', 'Acme V2.3 is here!')
        other = self.add('Acme V2.3 new model', 'Acme V2.3 is here!', 'https://x.com/acme/status/3')
        self.db.set_state(url,'ready',article='Acme V2.3 is here!',draft='malformed')
        self.db.set_state(other,'pending',article='Acme V2.3 is here!')
        with self.db.db:
            self.db.db.execute("UPDATE items SET created_at='2026-10-18 12:00:00'")
        with patch('ainews.model_session.model_session') as model, \
             patch('ainews.daily.prepare',return_value=[]) as prepare, \
             patch('ainews.daily.merge_stories',return_value=[]):
            daily.prepare_daily(self.cfg,self.db,self.root,now=datetime(2026,10,18,20,15,tzinfo=daily.MSK))
        model.assert_called_once()
        self.assertEqual(prepare.call_args.kwargs['candidate_urls'],[other])


if __name__ == '__main__':
    unittest.main()
