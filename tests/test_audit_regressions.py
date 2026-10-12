import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ainews.__main__ import publish_digest
from ainews.digest import card, due_slot
from ainews.feeds import Entry
from ainews.pipeline import _read_source, prerelease_url, telegram_evidence_url
from ainews.quality import check_semantic_claims, freshness_hours, same_event
from ainews.store import Store
from ainews.x_rss import parse_x_rss


class AuditRegressions(unittest.TestCase):
    def test_wrong_units_and_meanings_are_rejected(self):
        cases = [
            ('Open weights soon.', 'Исходный код планируют открыть вскоре.'),
            ('Given a table of labeled rows, predicts without training.', 'Не нужно собирать метки.'),
            ('Run ~100 bug hunts for $20.', 'Модели находят около 100 уязвимостей за 20 долларов.'),
            ('Generate hundreds of thousands of tokens.', 'Модель выполняет сотни тысяч шагов.'),
            ('Output token limit to an industry-leading 1M tokens.', 'Лимит контекста — 1 миллион токенов.'),
            ('At max effort costs less.', 'Модель дешевле при максимальной нагрузке.'),
            ('Rolling out to trusted cyber defenders through Fairwind.', 'Специалисты могут использовать без ограничений.'),
        ]
        for source, draft in cases:
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                check_semantic_claims(source, draft)

    def test_correctly_scoped_claims_pass(self):
        cases = [
            ('Open weights soon.', 'Веса планируют открыть вскоре.'),
            ('Given a table of labeled rows, predicts without training.', 'Нужны размеченные примеры в контексте, но дообучать модель не нужно.'),
            ('Run ~100 bug hunts for $20.', 'Можно выполнить около 100 запусков поиска ошибок за 20 долларов.'),
            ('Generate hundreds of thousands of tokens.', 'Модель может генерировать сотни тысяч токенов.'),
            ('Output token limit to an industry-leading 1M tokens.', 'Лимит выходных токенов — миллион.'),
            ('At max effort costs less.', 'Стоимость ниже на максимальном уровне рассуждений.'),
        ]
        for source, draft in cases:
            check_semantic_claims(source, draft)

    def test_rephrased_bio_watermark_and_sol_pricing_events_match(self):
        self.assertTrue(same_event('Новый метод SynthID Bio маркирует белки', 'Новые методы маркировки.',
                        [('Google DeepMind добавляет водяные знаки в искусственно созданные белки', 'Представлена SynthID Bio.')]))
        self.assertTrue(same_event('GPT-6.1 Sol стал дешевле на 30%', 'Стоимость задачи снизилась.',
                        [('GPT-6.1 Sol стал самым выгодным вариантом среди моделей OpenAI', 'Стоимость задачи снизилась.')]))
        self.assertFalse(same_event('Gemini 4 Argon оказалась дешевле конкурентов', 'Сравнили с GPT-6.1 Sol.',
                         [('GPT-6.1 Sol стал дешевле на 30%', 'Сравнение цен.')]))
        self.assertFalse(same_event('GPT-6.1 Sol появилась на платформе Nebius', 'Новый доступ через Nebius.',
                         [('GPT-6.1 Sol появилась в Arena', 'Новый доступ через Arena.')]))

    def test_compaction_preserves_labeled_examples_and_access_caveat(self):
        fields = {'headline': 'Новая модель', 'what': 'Модель делает прогнозы. Для работы нужны размеченные примеры.',
                  'simple': 'Ещё одно пояснение. ' * 12, 'caveat': 'Доступ пока ограничен тестовой группой.'}
        result = card(fields, 190)
        self.assertIn('размеченные примеры', result)
        self.assertIn('ограничен', result)
        self.assertEqual(card(fields, 35), '')

    def test_token_failure_keeps_retry_possible_without_uncertain_send(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'news.db')
            try:
                now = datetime.now().astimezone().replace(minute=10, second=0, microsecond=0)
                slot, cutoff = due_slot(now)
                url = 'https://example.com/new-model'
                store.add_feed('Official', [Entry('Official', 'New model', url, now.isoformat(), 'Model announcement')], include_existing=True)
                store.set_state(url, 'ready', draft='🧠 Новая модель\n\nЧто произошло: Разработчики выпустили новую модель.')
                store.db.execute("update items set created_at=datetime(?,'-1 minute'),published=datetime(?,'-1 minute') where url=?", (cutoff,cutoff,url))
                store.db.commit()
                config = {'sources':[{'name':'Official','auto_publish':True,'freshness_minutes':1440}],
                          'auto_publish':True,'channel_id':123,'digest_lookback_hours':6}
                with patch('ainews.__main__.read_token', side_effect=TimeoutError), patch('ainews.__main__.send_message') as send:
                    self.assertIn('ещё не началась', publish_digest(config,store,now=now)[0])
                    send.assert_not_called()
                self.assertIsNone(store.digest(slot))
                self.assertEqual(store.ready()[0]['url'],url)
            finally:
                store.close()

    def test_x_does_not_inherit_official_24_hour_catchup(self):
        config={'digest_lookback_hours':6,'official_catchup_hours':24}
        self.assertEqual(freshness_hours(config,{'type':'x'}),6)
        self.assertEqual(freshness_hours(config,{'type':'telegram'}),6)
        self.assertEqual(freshness_hours(config,{'name':'Official RSS'}),24)

    def test_research_article_links_are_preserved_and_allowed(self):
        url='https://hamel.dev/blog/posts/claude-auto-evals/index.html'
        xml=f'''<rss><channel><item><title>Review</title><link>https://nitter.example/HamelHusain/status/42</link>
            <pubDate>Thu, 01 Oct 2026 09:00:00 GMT</pubDate>
            <description>&lt;p&gt;I reviewed the new evaluation tool. &lt;a href="{url}"&gt;hamel.dev/blog/posts/claude-…&lt;/a&gt;&lt;/p&gt;</description>
            </item></channel></rss>'''
        entry=parse_x_rss(xml,{'handle':'HamelHusain','name':'X @HamelHusain'})[0]
        self.assertEqual(telegram_evidence_url(entry.summary),url)
        self.assertIsNone(telegram_evidence_url('https://hamel.dev.evil.test/article'))
        self.assertEqual(telegram_evidence_url('https://blog.google/innovation-and-ai/news'),
                         'https://blog.google/innovation-and-ai/news')

    def test_anthropic_model_announcements_at_root_are_not_missed(self):
        source={'name':'Anthropic','feed':'https://www.anthropic.com/sitemap.xml',
                'hosts':['www.anthropic.com'],'url_contains':['/news/'],
                'url_regex':r'^/claude-(?:sonnet|opus|haiku|fable|mythos)-[0-9]+(?:-[0-9]+)*/?$'}
        xml='<rss><channel>'+''.join(f'<item><title>Announcement</title><link>https://www.anthropic.com{p}</link></item>'
             for p in ['/news/test','/claude-sonnet-5-5','/claude-code'])+'</channel></rss>'
        with patch('ainews.pipeline.download_feed',return_value=(xml,source['feed'],None,None)):
            entries,*_=_read_source(source,None,None)
        self.assertEqual(len(entries),2)
        self.assertTrue(any('/claude-sonnet-5-5' in e.url for e in entries))

    def test_percent_encoded_canary_is_not_a_stable_release(self):
        self.assertTrue(prerelease_url('https://github.com/NousResearch/hermes-agent/releases/tag/v0.21.4%2Bcanary.20261001T070239Z'))
        self.assertFalse(prerelease_url('https://github.com/NousResearch/hermes-agent/releases/tag/v0.21.4'))


if __name__ == '__main__':
    unittest.main()
