import json
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import test_daily
from ainews import telegram
from ainews.daily import compose_daily, publish_daily, units
from ainews.pipeline import draft_text, prepare
from ainews.store import Store
from ainews.feeds import Entry
from ainews.presentation import assert_public_text, public_text
from ainews.quality import (complete_sentence, integrity_issues, sentences,
                            trim_incomplete_tail, event_signature, check_semantic_claims)


class PublicPresentationTests(unittest.TestCase):
    def test_all_destination_forms_are_removed(self):
        for url in ['https://example.com/path?a=1#f', 'http://example.com', 'www.example.com/page',
                    't.me/channel/12', 't.co/abcd', 'goo.gle/abc', 'short.custom/123',
                    '//example.com/path', 'https://', 'https:', 'www.', 'example.com?q=1', 'tg://resolve?domain=abc',
                    'пример.рф/новость', 'example.xn--p1ai/path', 'contact@example.com']:
            with self.subTest(url=url):
                result = public_text('Новость опубликована.\n\nИсточник: '+url)
                self.assertEqual(result, 'Новость опубликована.')
                assert_public_text(result)

    def test_inline_and_reference_markdown_keep_names(self):
        self.assertEqual(public_text('[OpenAI](https://x.com/OpenAI) обновила [Qwen][q].\n[q]: https://example.com'),
                         'OpenAI обновила Qwen.')
        self.assertEqual(public_text('[Модель (Preview)](https://example.com/a_(b) "release") доступна.'),
                         'Модель (Preview) доступна.')

    def test_html_and_encoded_markup_keep_visible_text(self):
        for link in ['<a href="https://example.com">LiquidAI</a>',
                     '&lt;a href=&quot;https://example.com&quot;&gt;LiquidAI&lt;/a&gt;']:
            self.assertEqual(public_text(link+' выпустила модель.'), 'LiquidAI выпустила модель.')
        self.assertEqual(public_text('<script>https://bad.example/run()</script><b>Qwen</b> обновлена.'),
                         'Qwen обновлена.')

    def test_domain_shaped_product_labels_are_visible_but_not_clickable(self):
        for label in ['Z.ai', 'v0.dev', 'Node.js']:
            for text in [f'[{label}](https://example.com)', f'<a href="https://example.com">{label}</a>']:
                result=public_text(text+' получила обновление.')
                self.assertEqual(result.replace('\u2060',''), label+' получила обновление.')
                assert_public_text(result)
        self.assertEqual(public_text('Z.ai и Node.js обновлены.').replace('\u2060',''), 'Z.ai и Node.js обновлены.')

    def test_broken_markup_and_autolinks_leave_no_fragments(self):
        self.assertEqual(public_text('Используйте [Qwen](https://example.com/broken'), 'Используйте Qwen')
        self.assertEqual(public_text('Новость (https://example.com/a) опубликована.'), 'Новость опубликована.')
        self.assertEqual(public_text('Новость. <https://example.com>'), 'Новость.')

    def test_url_labels_and_formatted_source_blocks_are_removed(self):
        for label in ['example.com', 'www.example.com', 't.co/abc', 'contact@example.com']:
            self.assertEqual(public_text(f'Новость. [{label}](https://example.com)'), 'Новость.')
        for prefix in ['**Источник:**', '__Ссылки:__', '### Sources:', '`Links`:', 'Источники']:
            text='Новость.\n\n'+prefix+'\nhttps://example.com'
            self.assertEqual(public_text(text),'Новость.')
            with self.assertRaises(ValueError):assert_public_text(text)

    def test_public_post_is_idempotent_and_preserves_story_separation(self):
        text='- Qwen получила обновление\n\n  Модель доступна локально.\n\n\n\n- Новый инструмент\n\n  Инструмент опубликован.'
        self.assertEqual(public_text(text), text)
        self.assertEqual(public_text(public_text(text)), text)
        assert_public_text(text)

    def test_transport_rejects_links_and_hidden_link_entities_before_network(self):
        with patch('ainews.telegram.urllib.request.urlopen') as network:
            for text in ['https://example.com', '[Qwen](https://example.com)', '<a href="x">Qwen</a>']:
                with self.subTest(text=text), self.assertRaises(ValueError):
                    telegram.call('mock', 'sendMessage', {'text':text})
            with self.assertRaises(ValueError):
                telegram.call('mock','sendMessage',{'text':'Новость.', 'entities':[{'type':'text_link','url':'https://example.com'}]})
            network.assert_not_called()

    def test_send_and_edit_adapters_remove_destinations(self):
        with patch('ainews.telegram.call', return_value={'message_id':1}) as api:
            telegram.send_message('mock',-1,'[OpenAI](https://example.com) обновила модель.')
            self.assertEqual(api.call_args.args[2]['text'],'OpenAI обновила модель.')
            telegram.edit_message('mock',-1,1,'<a href="https://example.com">Qwen</a> обновлена.')
            self.assertEqual(api.call_args.args[2]['text'],'Qwen обновлена.')

    def test_utf16_is_enforced_at_transport(self):
        with self.assertRaisesRegex(ValueError, 'UTF-16'):
            assert_public_text('🧠'*1951)

    def test_transport_also_rejects_incomplete_news(self):
        for text in ['- Модель получила обновление\n\n  Вес модели составляет ~',
                     '- d1-ultra\n\n  Модель представлена.']:
            with self.subTest(text=text), patch('ainews.telegram.urllib.request.urlopen') as network, self.assertRaises(ValueError):
                telegram.call('mock','sendMessage',{'text':text})
            network.assert_not_called()


class IntegrityTests(unittest.TestCase):
    def test_schema_string_limit_tail_is_removed_before_fact_check(self):
        source='Aster has 24B parameters. Its quantized weights are approximately 16GB.'
        draft={'relevant':True,'confidence':'high','headline':'Aster получила обновление',
               'what_happened':'Модель имеет 24 млрд параметров. Квантованные веса составляют ~',
               'simple_explanation':'','why_it_matters':'','caveat':'','evidence':source}
        result=draft_text(draft,source)
        self.assertIn('24 млрд параметров.',result)
        self.assertNotIn('~',result)
        self.assertTrue(draft['what_happened'].endswith('~'))

    def test_only_incomplete_main_or_caveat_is_not_silently_approved(self):
        source='The model is available only to paid subscribers.'
        base={'relevant':True,'confidence':'high','headline':'Aster стала доступна',
              'what_happened':'Модель доступна подписчикам.','evidence':source}
        for fields in [{'what_happened':'Контекст составляет ~'}, {'caveat':'Доступна только'}]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):draft_text({**base,**fields},source)

    def test_numeric_abbreviations_and_versions_survive_compaction(self):
        text='Контекст составляет 128 тыс. токенов. vLLM поддерживает версию 2.1.'
        self.assertEqual(len(sentences(text)),2)
        self.assertEqual(trim_incomplete_tail(text),(text,''))
        self.assertTrue(complete_sentence(text))
        self.assertTrue(complete_sentence('Добавлена поддержка C++.'))
        quoted='Компания заявила: «Модель выпущена. Веса открыты».'
        self.assertEqual(trim_incomplete_tail(quoted),(quoted,''))

    def test_unbalanced_and_unfinished_characteristics_fail(self):
        for text in ['Вес — ~','Контекст: 128 тыс.','Скорость (на GPU.','Это «новая модель.','Цена составляет $', 'Модель работает...', 'Контекст составляет ~.', 'Скорость равна 1,.']:
            with self.subTest(text=text):self.assertFalse(complete_sentence(text))

    def test_bare_identifier_title_fails_without_model_name_rules(self):
        for title in ['d1-ultra','Aster-7B-A1B','v0.3.1','','Aster 🧠','Модель с контекстом ~']:
            with self.subTest(title=title):self.assertTrue(integrity_issues('Модель выпущена.',headline=title))
        self.assertFalse(integrity_issues('Модель выпущена.',headline='Aster получила поддержку файлов'))

    def test_release_and_two_runtime_integrations_are_separate_events(self):
        signatures=[event_signature(title,'') for title in ['Nova 2.0 new model release',
                    'vLLM adds support for Nova 2.0','Ollama adds support for Nova 2.0']]
        self.assertTrue(all(signatures))
        self.assertEqual(len(set(signatures)),3)
        self.assertEqual(event_signature('vLLM adds support for Nova 2.0','Ollama already supports it.')[3],'vllm')

    def test_daily_verifier_sees_only_complete_text_and_original_source(self):
        source='Aster is a model with 24B parameters for local use.'
        draft={'relevant':True,'confidence':'high','headline':'Aster получила обновление',
               'what_happened':'Модель имеет 24 млрд параметров. Вес составляет ~',
               'simple_explanation':'','why_it_matters':'','caveat':'','evidence':source}
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
            store.add_feed('official',[Entry('official','Aster update','https://example.com/update',
                           datetime.now(timezone.utc).isoformat(),source)],include_existing=True)
            config={'publication_mode':'daily','sources':[{'name':'official','auto_publish':True,'content_from_feed':True,'hosts':['example.com']}]}
            with patch('ainews.pipeline.article_details',return_value=(source,None)), \
                 patch('ainews.pipeline.generate_draft',return_value=draft), \
                 patch('ainews.pipeline.polish_draft',side_effect=lambda config,title,source,data:data) as style, patch('ainews.pipeline.verify_draft') as verify:
                prepare(config,store,limit=1)
            style.assert_called_once()
            self.assertNotIn('~',style.call_args.args[3]['what_happened'])
            verify.assert_called_once()
            self.assertEqual(verify.call_args.args[2],source)
            self.assertNotIn('~',verify.call_args.args[3])
            self.assertEqual(store.ready()[0]['article'],source)
            self.assertIsNotNone(store.db.execute("SELECT 1 FROM editorial_audit WHERE stage='incomplete_tail_removed'").fetchone())

    def test_explicit_release_date_is_not_replaced_by_feed_update(self):
        for offset, expected in [(0,'ready'),(-1,'skipped'),(None,'needs_review')]:
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
                now=datetime.now(timezone.utc)
                from ainews.daily import MSK
                date=(now.astimezone(MSK)+timedelta(days=offset or 0)).strftime('%B %d, %Y')
                source=('Release Date: '+date+'. ' if offset is not None else '')+'Aster released a stable update for local tools.'
                url='https://github.com/example/aster/releases/tag/v2.0.1'
                store.add_feed('official',[Entry('official','Aster v2.0.1',url,now.isoformat(),source,date_kind='updated')],include_existing=True)
                config={'publication_mode':'daily','sources':[{'name':'official','auto_publish':True,'content_from_feed':True,'hosts':['github.com']}]}
                draft={'relevant':True,'confidence':'high','headline':'Aster получила обновление',
                       'what_happened':'Вышло стабильное обновление для локальных инструментов.','evidence':'Aster released a stable update for local tools.'}
                with patch('ainews.pipeline.article_details',return_value=(source,None)), \
                     patch('ainews.pipeline.generate_draft',return_value=draft) as writer, \
                     patch('ainews.pipeline.polish_draft',side_effect=lambda config,title,source,data:data), patch('ainews.pipeline.verify_draft'):
                    prepare(config,store,limit=1)
                row=store.db.execute('SELECT * FROM items').fetchone()
                self.assertEqual(row['state'],expected,row['error'])
                if offset != 0:writer.assert_not_called()

    def test_product_cannot_become_a_standard_without_source_evidence(self):
        source='Nimbus 7 Preview has Day-0 support in Engine, with sparse attention and vision.'
        with self.assertRaisesRegex(ValueError,'standard'):
            check_semantic_claims(source,'Добавлена поддержка предварительной версии стандарта Nimbus 7.')
        check_semantic_claims(source,'Добавлена поддержка Nimbus 7 Preview.')
        check_semantic_claims('MCP is an open protocol for tools.','Поддерживается стандарт MCP.')

    def test_generic_performance_features_do_not_prove_lossless_quality(self):
        with self.assertRaisesRegex(ValueError,'no-loss'):
            check_semantic_claims('FP8 kernels improve inference speed.','Обработка ускорится без потери качества.')
        check_semantic_claims('The vendor reports lossless compression.','По данным разработчика, сжатие работает без потери качества.')


class PublicArchiveTests(unittest.TestCase):
    setUp=test_daily.DailyTests.setUp
    tearDown=test_daily.DailyTests.tearDown
    add=test_daily.DailyTests.add

    def test_api_ledger_archive_and_private_sources_stay_consistent(self):
        url='https://official.example/release'
        self.config['sources'][0]['hosts']=['official.example']
        self.add(url)
        raw=dict(self.store.db.execute('SELECT * FROM items WHERE url=?',(url,)).fetchone())
        # Exercise the real adapter with a mocked API, rather than bypassing
        # presentation using a mocked sender alone.
        with patch('ainews.telegram.call',return_value={'message_id':21}) as api:
            publish_daily(self.config,self.store,self.root,now=self.now,token_reader=lambda:'mock')
            publish_daily(self.config,self.store,self.root,now=self.now,token_reader=lambda:'mock')
        api.assert_called_once()
        text=api.call_args.args[2]['text']
        archive=json.loads((self.root/'output/daily/2026-10-12.json').read_text(encoding='utf8'))
        self.assertEqual(text,archive['telegram_text'])
        self.assertEqual(text,self.store.digest('daily:2026-10-12')['text'])
        self.assertIn(url,archive['full_text'])
        self.assertEqual(archive['published_urls'],[url])
        self.assertNotIn('https://',text)
        saved=self.store.db.execute('SELECT * FROM items WHERE url=?',(url,)).fetchone()
        self.assertEqual((raw['article'],raw['summary'],raw['draft']), (saved['article'],saved['summary'],saved['draft']))

    def test_invalid_ready_story_cannot_reach_publication(self):
        self.add('bad',what='Модель выпущена. Вес составляет ~')
        self.add('good',headline='Другая модель обновлена')
        sender=Mock(return_value=1)
        publish_daily(self.config,self.store,self.root,now=self.now,token_reader=lambda:'mock',sender=sender)
        sender.assert_called_once()
        self.assertNotIn('~',sender.call_args.args[2])
        self.assertEqual(self.store.db.execute("SELECT state FROM items WHERE url='bad'").fetchone()[0],'needs_review')
