import unittest
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ainews.daily import MSK, publish_daily
from ainews.evidence import ArticleText, Document, chunks, linked_primary_urls, packet, retrieve
from ainews.fact_first import Fact, Result, audit_text, compose_edition, edit, extract, prepare_entry, render, verify_facts
from ainews.feeds import Entry
from ainews.store import Store


class EvidencePackets(unittest.TestCase):
    def test_discovery_orchestration_reaches_editor_with_official_evidence(self):
        row = {'url': 'https://official.example/release', 'title': 'Aster release',
               'summary': 'Aster is now available.'}
        expected = Result('needs_review', 'Manual review', {}, ())
        with patch('ainews.fact_first.edit', return_value=expected) as editor:
            result, evidence = prepare_entry({}, row, {'type': 'rss', 'primary_account': True},
                edition_date='2026-10-18', loader=lambda url: ('Aster is now available.', None))
        self.assertIs(result, expected)
        self.assertIsNotNone(evidence)
        editor.assert_called_once()

    def test_table_keeps_headers_with_values_and_excludes_navigation(self):
        parser = ArticleText()
        parser.feed('<nav><p>Unrelated model wins.</p></nav><article><h1>Aster test</h1>'
                    '<p>' + 'This report describes controlled experiments. ' * 8 + '</p>'
                    '<table><tr><th>Device</th><th>Output tokens/s</th></tr>'
                    '<tr><td>B200</td><td>150</td></tr></table></article>')
        self.assertIn('Device | Output tokens/s\nB200 | 150', parser.text)
        self.assertNotIn('Unrelated', parser.text)
        value = packet([Document('https://official.example/report', parser.text)], edition_date='2026-10-18', official=True)
        table = [s for s in value.spans if 'Device |' in s.text]
        self.assertEqual(len(table), 1)
        self.assertIn('B200 | 150', table[0].text)

    def test_chunks_retain_every_source_span_without_slicing_a_fact(self):
        value = packet([Document('https://official.example', 'First fact.\n\nSecond fact.\n\nLast limitation.')],
                       edition_date='2026-10-18', official=True)
        self.assertEqual([s for chunk in chunks(value, 25) for s in chunk], list(value.spans))
        with self.assertRaisesRegex(ValueError, 'block exceeds'):
            chunks(value, 5)

    def test_deduplicate_only_identical_documents_and_keep_stable_provenance(self):
        a = Document('https://official.example', 'Aster is released.')
        value = packet([a, a, Document('https://another.example', a.text)], edition_date='2026-10-18', official=True)
        self.assertEqual(len(value.documents), 2)
        self.assertEqual(value.fingerprint, packet([a, a, Document('https://another.example', a.text)], edition_date='2026-10-18', official=True).fingerprint)
        self.assertEqual([s.document for s in value.spans], [0, 1])

    def test_short_official_post_survives_optional_article_outage(self):
        row = {'url': 'https://x.com/runtime/status/1', 'published': '2026-10-18',
               'summary': 'Runtime now supports Aster. https://github.com/vendor/aster'}
        def fail(url):
            raise TimeoutError
        docs, errors = retrieve(row, {'type': 'x', 'primary_account': True, 'handle': 'runtime'}, fail)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].text, row['summary'])
        self.assertEqual(errors[0]['error_type'], 'TimeoutError')

    def test_secondary_title_never_becomes_a_primary_document(self):
        row = {'url': 'https://t.me/example/1', 'published': '2026-10-18',
               'summary': 'Unproven 9000 tokens/s. https://huggingface.co/blog/example'}
        docs, _ = retrieve(row, {'type': 'telegram'}, lambda url: ('Aster was released.', None))
        self.assertEqual([d.text for d in docs], ['Aster was released.'])

    def test_repository_evidence_retains_owner_and_project_scope(self):
        row = {'url': 'https://t.me/example/1', 'published': '2026-10-18',
               'summary': 'Read https://github.com/vendor/aster'}
        docs, _ = retrieve(row, {'type': 'telegram'}, lambda url: ('Aster documentation.', None))
        self.assertEqual((docs[0].publisher, docs[0].project), ('vendor', 'aster'))

    def test_primary_subdomains_are_recognized_without_accepting_lookalike_hosts(self):
        links = linked_primary_urls('https://developers.openai.com/blog/test https://github.com.evil.example/test')
        self.assertEqual(links, ['https://developers.openai.com/blog/test'])

    def test_integration_trigger_precedes_older_linked_background(self):
        value = packet([Document('https://vendor.example/old', 'Aster released.', '2025-01-01', 'linked_background'),
                        Document('https://x.com/runtime/status/1', 'Now supported in Runtime.', '2026-10-18', 'official_post')],
                       edition_date='2026-10-18', official=True)
        self.assertEqual(value.documents[0].role, 'official_post')
        self.assertEqual(value.documents[1].published, '2025-01-01')


class FactEditor(unittest.TestCase):
    def setUp(self):
        self.evidence = packet([Document('https://official.example/report',
                    'Aster released a model for local use. The output rate is 150 tokens/s on B200.')],
                    edition_date='2026-10-18', official=True)
        self.event = {'company': 'Aster', 'product': 'Aster', 'version': '', 'scope': '', 'kind': 'release', 'date': '', 'span_ids': ['s0']}
        self.row = {'text': 'Aster выпустила модель для локального запуска.', 'subject': 'Aster',
                    'metric': '', 'value': '', 'unit': '', 'conditions': '', 'comparison': '',
                    'kind': 'event', 'essential': True, 'span_ids': ['s0']}
        self.extraction = {'has_event': True, 'event': self.event,
                           'headline': 'Aster выпустила локальную модель', 'headline_span_ids': ['s0'], 'facts': [self.row]}
        self.verdict = {'event_supported': True, 'event_issue': '', 'headline_supported': True, 'headline_issue': '',
                        'checks': [{'id': 'f0', 'supported': True, 'issue': ''}], 'missing_restrictions': []}

    def fact(self, **changes):
        return Fact(id=changes.pop('id', 'f0'), **{**self.row, **changes, 'span_ids': tuple(changes.get('span_ids', self.row['span_ids']))})

    def test_verified_assembly_adds_no_factual_prose_or_additional_model_call(self):
        with patch('ainews.fact_first.ollama_json', side_effect=[self.extraction, self.verdict]) as model:
            result = edit({}, self.evidence)
        self.assertEqual(result.state, 'ready')
        self.assertEqual(result.paragraphs, (self.row['text'],))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(result.facts[0].span_ids, ('s0',))

    def test_verified_event_need_not_be_duplicated_in_a_fact_kind(self):
        raw = {**self.extraction, 'facts': [{**self.row, 'kind': 'capability'}]}
        with patch('ainews.fact_first.ollama_json', side_effect=[raw, self.verdict]):
            self.assertEqual(edit({}, self.evidence).state, 'ready')

    def test_event_refusal_requires_a_consistent_diagnostic_reason(self):
        for verdict in [{**self.verdict, 'event_supported': False},
                        {**self.verdict, 'headline_issue': 'Wrong product.'}]:
            with patch('ainews.fact_first.ollama_json', return_value=verdict):
                _, reason = verify_facts({}, self.evidence, self.event, self.extraction['headline'], [self.fact()])
            self.assertIn('Contradictory', reason)

    def test_unknown_or_duplicate_source_references_hold_the_story(self):
        for references in [['fake'], ['s0', 's0'], []]:
            raw = {**self.extraction, 'facts': [{**self.row, 'span_ids': references}]}
            with self.subTest(references=references), patch('ainews.fact_first.ollama_json', return_value=raw):
                event, title, facts, error = extract({}, self.evidence)
            self.assertTrue(error)
            self.assertFalse(facts)

    def test_number_not_in_cited_spans_is_not_borrowed_from_another_document(self):
        value = packet([Document('https://official.example', 'Aster released a model.'),
                        Document('https://other.example', 'Boreal output rate is 9000 tokens/s.')],
                       edition_date='2026-10-18', official=True)
        raw = {**self.extraction, 'facts': [{**self.row, 'text': 'Aster выдаёт 9000 токенов в секунду.'}]}
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            _, _, facts, _ = extract({}, value)
        self.assertFalse(facts)

    def test_correct_sentence_cannot_conceal_invented_typed_measurement(self):
        raw = {**self.extraction, 'facts': [{**self.row, 'value': '9999'}]}
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            _, _, facts, _ = extract({}, self.evidence)
        self.assertFalse(facts)

    def test_product_identifier_in_heading_does_not_become_an_unbound_measurement(self):
        value = packet([Document('https://official.example',
            'Aster-24B released.\n\nScore is 48.09 on the benchmark.')],
            edition_date='2026-10-18', official=True)
        raw = {**self.extraction, 'event': {**self.event, 'product': 'Aster-24B'},
            'headline': 'Вышла Aster-24B', 'facts': [{**self.row,
                'text': 'Aster-24B набрала 48.09 балла.', 'span_ids': ['s1']}]}
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            _, _, facts, reason = extract({}, value)
        self.assertFalse(reason)
        self.assertEqual(len(facts), 1)
        raw['facts'][0]['text'] = 'Aster-24B набрала 9999 баллов.'
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            _, _, facts, _ = extract({}, value)
        self.assertFalse(facts)

    def test_continuation_facts_do_not_require_a_second_event(self):
        value = packet([Document('https://official.example',
            'Aster released a model.\n\nOutput rate is 150 tokens/s on B200.')],
            edition_date='2026-10-18', official=True)
        continuation = {**self.extraction, 'has_event': False,
            'facts': [{**self.row, 'text': 'Вывод составляет 150 токенов в секунду на B200.',
                       'value': '150', 'metric': 'output_rate', 'span_ids': ['s1']}]}
        with patch('ainews.fact_first.chunks', return_value=[(value.spans[0],), (value.spans[1],)]), \
             patch('ainews.fact_first.ollama_json', side_effect=[self.extraction, continuation]):
            event, _, facts, reason = extract({}, value)
        self.assertFalse(reason)
        self.assertEqual(event['product'], 'Aster')
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[1].span_ids, ('s1',))

    def test_measurements_without_an_initial_event_do_not_create_one(self):
        with patch('ainews.fact_first.ollama_json', return_value={**self.extraction, 'has_event': False}):
            event, _, facts, _ = extract({}, self.evidence)
        self.assertFalse(event)
        self.assertFalse(facts)

    def test_scaled_number_words_are_equivalent_but_do_not_approve_invented_values(self):
        value = packet([Document('https://official.example',
            'Aster supports two million tokens of context.')], edition_date='2026-10-18', official=True)
        raw = {**self.extraction, 'facts': [{**self.row,
            'text': 'Aster поддерживает контекст 2 млн токенов.', 'value': '2M'}]}
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            _, _, facts, error = extract({}, value)
        self.assertFalse(error)
        self.assertEqual(len(facts), 1)
        raw['facts'][0]['text'] = 'Aster поддерживает контекст 9 млн токенов.'
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            _, _, facts, _ = extract({}, value)
        self.assertFalse(facts)

    def test_writer_may_reference_six_verified_facts_in_one_paragraph(self):
        facts = [self.fact(id=f'f{i}', text=f'Подробность номер {i} подтверждена.') for i in range(6)]
        written = {'headline': {'text': self.extraction['headline'], 'fact_ids': ['f0']},
            'paragraphs': [{'text': ' '.join(f.text for f in facts), 'fact_ids': [f.id for f in facts]}]}
        with patch('ainews.fact_first.extract', return_value=(self.event, self.extraction['headline'], facts, '')), \
             patch('ainews.fact_first.verify_facts', return_value=(facts, '')), \
             patch('ainews.fact_first.ollama_json', side_effect=[written, {'supported': True, 'issues': []}]):
            result = edit({}, self.evidence, mode='writer')
        self.assertEqual(result.state, 'ready')

    def test_third_party_repository_cannot_establish_another_company_release(self):
        source = packet([Document('https://github.com/outsider/boreal',
            'Boreal uses Aster. Aster was released.', project='boreal', publisher='outsider')],
            edition_date='2026-10-18', official=False)
        with patch('ainews.fact_first.extract', return_value=(self.event, self.extraction['headline'], [self.fact()], '')), \
             patch('ainews.fact_first.verify_facts') as verifier:
            result = edit({}, source)
        self.assertEqual(result.state, 'needs_review')
        self.assertIn('authority', result.reason)
        verifier.assert_not_called()

    def test_undated_repository_overview_is_not_a_dated_release_announcement(self):
        source = packet([Document('https://github.com/vendor/aster', 'Aster documentation.',
            project='aster', publisher='vendor')], edition_date='2026-10-18', official=False)
        with patch('ainews.fact_first.extract', return_value=(self.event, self.extraction['headline'], [self.fact()], '')):
            result = edit({}, source)
        self.assertIn('no dated', result.reason)
        self.assertEqual(result.state, 'needs_review')

    def test_exact_project_release_can_reach_source_verification(self):
        source = packet([Document('https://github.com/vendor/aster/releases/tag/v1',
            'Aster released.', '2026-10-18T12:00:00Z', project='aster', publisher='vendor')],
            edition_date='2026-10-18', official=False)
        with patch('ainews.fact_first.extract', return_value=(self.event, self.extraction['headline'], [self.fact()], '')), \
             patch('ainews.fact_first.verify_facts', return_value=([self.fact()], '')) as verifier:
            self.assertEqual(edit({}, source).state, 'ready')
        verifier.assert_called_once()

    def test_verifier_receives_link_free_fact_wording_and_evidence_stays_private(self):
        raw = {**self.extraction, 'facts': [{**self.row,
            'text': 'Aster выпустила [модель](https://official.example/model) для локального запуска.'}]}
        with patch('ainews.fact_first.ollama_json', side_effect=[raw, self.verdict]) as model:
            result = edit({}, self.evidence)
        self.assertEqual(result.state, 'ready')
        checked = __import__('json').loads(model.call_args_list[1].args[1])
        self.assertNotIn('https://', checked['facts'][0]['text'])
        self.assertIn('модель', checked['facts'][0]['text'])
        self.assertIn('https://', raw['facts'][0]['text'])
        self.assertEqual(self.evidence.documents[0].url, 'https://official.example/report')

    def test_required_url_value_cannot_be_removed_from_a_verified_fact(self):
        raw = {**self.extraction, 'facts': [{**self.row,
            'text': 'Адрес API — https://official.example/api.', 'value': 'https://official.example/api'}]}
        with patch('ainews.fact_first.ollama_json', return_value=raw) as model:
            result = edit({}, self.evidence)
        self.assertEqual(result.state, 'needs_review')
        self.assertIn('URL value', result.reason)
        self.assertEqual(model.call_count, 1)

    def test_citation_presence_does_not_bypass_negative_entailment(self):
        bad = {**self.verdict, 'checks': [{'id': 'f0', 'supported': False, 'issue': 'Wrong product owner.'}]}
        with patch('ainews.fact_first.ollama_json', return_value=bad):
            facts, reason = verify_facts({}, self.evidence, self.event, self.extraction['headline'], [self.fact()])
        self.assertFalse(facts)
        self.assertIn('essential', reason)

    def test_missing_conditions_hold_even_when_all_selected_sentences_pass(self):
        with patch('ainews.fact_first.ollama_json', return_value={**self.verdict, 'missing_restrictions': ['Only at batch 16.']}):
            facts, reason = verify_facts({}, self.evidence, self.event, self.extraction['headline'], [self.fact()])
        self.assertFalse(facts)
        self.assertIn('restrictions', reason)

    def test_supported_verdict_with_objection_is_protocol_failure(self):
        raw = {**self.verdict, 'checks': [{'id': 'f0', 'supported': True, 'issue': 'Not proven.'}]}
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            facts, reason = verify_facts({}, self.evidence, self.event, self.extraction['headline'], [self.fact()])
        self.assertEqual(reason, 'Contradictory fact verdict')

    def test_missing_verdict_or_unknown_fact_id_cannot_approve(self):
        for checks in [[], [{'id': 'f99', 'supported': True, 'issue': ''}]]:
            with patch('ainews.fact_first.ollama_json', return_value={**self.verdict, 'checks': checks}):
                facts, reason = verify_facts({}, self.evidence, self.event, self.extraction['headline'], [self.fact()])
            self.assertFalse(facts)
            self.assertIn('protocol', reason)

    def test_current_integration_does_not_inherit_background_release_date(self):
        raw = {**self.extraction, 'event': {**self.event, 'kind': 'integration', 'date': '2026-10-18'}}
        with patch('ainews.fact_first.ollama_json', side_effect=[raw, self.verdict]):
            self.assertEqual(edit({}, self.evidence).state, 'ready')

    def test_verified_historical_release_is_not_published_as_new(self):
        raw = {**self.extraction, 'event': {**self.event, 'date': '2026-10-17'}}
        with patch('ainews.fact_first.ollama_json', side_effect=[raw, self.verdict]):
            self.assertEqual(edit({}, self.evidence).state, 'skipped')

    def test_final_audit_accepts_normal_headline_but_rejects_truncated_body(self):
        audit_text('Aster выпустила локальную модель\n\n'+self.row['text'], [self.fact()])
        with self.assertRaises(ValueError):
            audit_text('Aster выпустила локальную модель\n\nКонтекст вырос до ~', [self.fact()])
        with self.assertRaises(ValueError):
            audit_text('Aster выпустила локальную модель\n\nДоступна по https://example.org.', [self.fact()])

    def test_writer_final_audit_can_reject_a_new_unsupported_implication(self):
        written = {'headline': {'text': self.extraction['headline'], 'fact_ids': ['f0']},
                   'paragraphs': [{'text': 'Она решает любые задачи.', 'fact_ids': ['f0']}]}
        with patch('ainews.fact_first.ollama_json', side_effect=[self.extraction, self.verdict, written,
                    {'supported': False, 'issues': ['Universal capability unsupported.']}]):
            result = edit({}, self.evidence, mode='writer')
        self.assertEqual(result.state, 'needs_review')

    def test_writer_verifies_source_language_facts_before_russian_generation(self):
        native = {**self.extraction, 'headline': 'Aster releases a local model',
            'facts': [{**self.row, 'text': 'Aster released a model for local use.'}]}
        written = {'headline': {'text': self.extraction['headline'], 'fact_ids': ['f0']},
            'paragraphs': [{'text': self.row['text'], 'fact_ids': ['f0']}]}
        with patch('ainews.fact_first.ollama_json', side_effect=[native, self.verdict, written,
                    {'supported': True, 'issues': []}]) as model:
            result = edit({}, self.evidence, mode='writer')
        self.assertEqual(result.state, 'ready')
        verified = __import__('json').loads(model.call_args_list[1].args[1])['facts']
        writer_input = __import__('json').loads(model.call_args_list[2].args[1])['facts']
        self.assertEqual(verified[0]['text'], 'Aster released a model for local use.')
        self.assertEqual(writer_input[0]['text'], verified[0]['text'])
        self.assertEqual(result.paragraphs, (self.row['text'],))

    def test_cache_reuses_only_same_model_mode_date_and_captured_evidence(self):
        cache = {}
        with patch('ainews.fact_first.ollama_json', side_effect=[self.extraction, self.verdict]) as model:
            first = edit({'model': 'mock'}, self.evidence, cache=cache)
            second = edit({'model': 'mock'}, self.evidence, cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(model.call_count, 2)
        with patch('ainews.fact_first.ollama_json', side_effect=[self.extraction, self.verdict]) as model:
            edit({'model': 'other'}, self.evidence, cache=cache)
        self.assertEqual(model.call_count, 2)

    def test_invalid_event_metadata_is_held_before_fact_writing(self):
        raw = {**self.extraction, 'event': {**self.event, 'date': 'yesterday'}}
        with patch('ainews.fact_first.ollama_json', return_value=raw):
            result = edit({}, self.evidence)
        self.assertEqual(result.state, 'needs_review')
        self.assertIn('date', result.reason)

    def test_canonical_utc_release_date_is_compared_in_moscow(self):
        source = packet([Document('https://github.com/vendor/model/releases/tag/v2.0',
                                'New stable release.', '2026-10-17T22:30:00Z')],
                        edition_date='2026-10-18', official=True)
        # 22:30 UTC belongs to the next Moscow date: do not skip it early.
        with patch('ainews.fact_first.extract', return_value=({}, '', [], 'No selected facts')) as extract_mock:
            edit({}, source)
        extract_mock.assert_called_once()
        old = packet([Document('https://github.com/vendor/model/releases/tag/v2.0',
                                'New stable release.', '2026-10-17T18:30:00Z')],
                        edition_date='2026-10-18', official=True)
        with patch('ainews.fact_first.ollama_json') as model:
            self.assertEqual(edit({}, old).state, 'skipped')
        model.assert_not_called()

    def test_shortening_drops_whole_optional_paragraphs_and_keeps_conditions(self):
        main = self.fact()
        caveat = self.fact(id='f1', text='Доступна только подписчикам.', kind='limitation')
        optional = self.fact(id='f2', text='Дополнительная подробность. ' * 30, essential=False, kind='capability')
        value = Result('ready', '', self.event, (main, caveat, optional), self.extraction['headline'],
                       (main.text, caveat.text, optional.text), (('f0',), ('f1',), ('f2',)))
        text = render(value, 200)
        self.assertIn(caveat.text, text)
        self.assertNotIn('Дополнительная', text)
        self.assertEqual(render(value, 30), '')


class CertifiedPublication(unittest.TestCase):
    def test_experimental_composer_uses_existing_idempotent_ledger_and_mock_sender(self):
        url='https://official.example/release'
        source=Document(url,'Aster is now supported.')
        evidence=packet([source],edition_date='2026-10-18',official=True)
        fact=Fact('f0','Runtime добавил поддержку Aster.','Aster','','','','','', 'event',True,('s0',))
        event={'company':'Vendor','product':'Aster','version':'','kind':'integration','scope':'Runtime','date':''}
        result=Result('ready','',event,(fact,),'Aster появилась в Runtime',(fact.text,),(('f0',),))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'test.db')
            try:
                store.add_feed('official',[Entry('official','Aster integration',url,'2026-10-18T12:00:00Z',source.text)],include_existing=True)
                store.set_state(url,'ready',article=source.text,draft='Unused legacy representation')
                config={'channel_id':-1,'auto_publish':True,'sources':[{'name':'official','auto_publish':True}]}
                def composer(c,s,n):return compose_edition(c,s,n,{url:(result,evidence)})
                calls=[]
                def send(token,channel,text):calls.append(text);return 8
                now=datetime(2026,10,18,21,tzinfo=MSK)
                report=publish_daily(config,store,root,now=now,token_reader=lambda:'mock',sender=send,composer=composer)
                self.assertIn('Telegram published',report)
                self.assertEqual(publish_daily(config,store,root,now=now,token_reader=lambda:'mock',sender=send,composer=composer),[])
                self.assertEqual(len(calls),1)
                self.assertNotIn('https://',calls[0])
                archive=(root/'output/daily/2026-10-18.json').read_text(encoding='utf8')
                self.assertIn(url,archive)
                self.assertEqual(store.digest('daily:2026-10-18')['text'],calls[0])
                config['sources'][0]['auto_publish']=False
                self.assertEqual(compose_edition(config,store,now,{url:(result,evidence)}).telegram,'')
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
