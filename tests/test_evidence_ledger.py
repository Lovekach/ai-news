import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from ainews import evidence
from ainews.pipeline import verify_draft, prepare
from ainews.digest import card
from ainews.store import Store
from ainews.feeds import Entry


SOURCE = 'Aster-8B-A1B is a model with 128K tokens of context. It is now supported by Engine.'
TEXT = '🧠 Aster-8B-A1B\n\nЧто произошло: Aster-8B-A1B получила поддержку Engine.\n\nЗачем это нужно: Она доступна бесплатно.'


def verdicts(text=TEXT, source=SOURCE):
    rows = []
    for claim in evidence.claims(text):
        rows.append({'id': claim['id'], 'status': 'supported', 'source': 0, 'quote': source,
                     **{key: '' for key in evidence.FACT_FIELDS},
                     'entity': 'Aster-8B-A1B', 'event': 'support', 'kind': 'model',
                     'basis': 'source_claim', 'attribute': claim['field']})
    return {'checks': rows}


class EvidenceContractTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{'url': 'https://official.example/support', 'text': SOURCE}]

    def test_ids_cover_multiple_fields_without_collision(self):
        text = TEXT.replace('поддержку Engine.', 'поддержку Engine. Контекст сохранён. Работает локально.')
        ids = [row['id'] for row in evidence.claims(text)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ['c'+str(index) for index in range(len(ids))])

    def test_rejected_optional_sentence_does_not_erase_supported_news(self):
        result = verdicts(); result['checks'][-1]['status'] = 'unsupported'
        review = evidence.validated_review(TEXT, result, self.sources)
        self.assertIn('поддержку Engine', review['text'])
        self.assertNotIn('бесплатно', review['text'])
        self.assertEqual(len(review['rejected']), 1)

    def test_missing_duplicate_and_foreign_ids_fail_closed(self):
        for mutate in (lambda rows: rows[:-1], lambda rows: rows+[rows[0]],
                       lambda rows: [{**rows[0], 'id': 'other'}]+rows[1:]):
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, 'verdicts'):
                evidence.validated_review(TEXT, {'checks': mutate(verdicts()['checks'])}, self.sources)

    def test_unsupported_main_requires_review(self):
        result = verdicts();result['checks'][1]['status'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, 'main sentence'):
            evidence.validated_review(TEXT, result, self.sources)

    def test_rejected_headline_uses_only_supported_literal_entity(self):
        result = verdicts();result['checks'][0]['status'] = 'unsupported'
        review = evidence.validated_review(TEXT, result, self.sources)
        self.assertEqual(review['text'].splitlines()[0], '🧠 Aster-8B-A1B')

    def test_quote_cannot_be_spliced_or_reassigned_to_another_source(self):
        for quote, index in (('Aster-8B-A1B now supported with free access.', 0), (SOURCE, 1), (SOURCE, True)):
            result = verdicts();result['checks'][1].update(quote=quote, source=index)
            with self.subTest(index=index, quote=quote), self.assertRaisesRegex(ValueError, 'main sentence'):
                evidence.validated_review(TEXT, result, self.sources+[{'url': 'other', 'text': 'Another source.'}])

    def test_a1b_cannot_change_to_a2b_even_when_digit_two_is_elsewhere(self):
        source = SOURCE+' Two versions have 2 deployment modes.'
        text = TEXT.replace('Aster-8B-A1B получила', 'Aster-8B-A2B получила')
        with self.assertRaisesRegex(ValueError, 'main sentence'):
            evidence.validated_review(text, verdicts(text, source), [{'url': 'official', 'text': source}])
        self.assertTrue(evidence.identity_issues(source, 'Aster-8B-A2B'))
        self.assertFalse(evidence.identity_issues(source, 'Aster-8B-A1B'))

    def test_unknown_product_identifier_is_not_allowed(self):
        self.assertTrue(evidence.identity_issues(SOURCE, 'Aster-9B-A1B'))
        self.assertTrue(evidence.identity_issues('Engine 7.3 is supported.', 'Engine7.4'))
        self.assertFalse(evidence.identity_issues('Engine 7.3 is supported.', 'Engine7.3'))
        self.assertFalse(evidence.identity_issues('Measured on Dense 300.', 'Dense-300'))
        self.assertTrue(evidence.identity_issues('Engine 7.3 is supported.', 'Engine7.30'))

    def test_entity_identity_numbers_are_not_confused_with_measurement_values(self):
        source = 'Aster 8 is available. Start using its API on the paid tier.'
        text = '🧠 Aster 8\n\nЧто произошло: Aster 8 доступна через платный API.'
        result = verdicts(text, source)
        for row in result['checks']:
            row.update(entity='Aster 8', quote='Start using its API on the paid tier.')
        review = evidence.validated_review(text, result, [{'url':'official', 'text':source}])
        self.assertIn('Aster 8 доступна', review['text'])
        text = text.replace('платный API', 'платный API с 256 токенами')
        with self.assertRaisesRegex(ValueError, 'main sentence'):
            evidence.validated_review(text, verdicts(text, source), [{'url':'official', 'text':source}])

    def test_optional_survivor_cannot_replace_rejected_main_event(self):
        text = TEXT.replace('поддержку Engine.', 'поддержку Engine. Документация доступна.')
        result = verdicts(text);result['checks'][1]['status']='unsupported'
        with self.assertRaisesRegex(ValueError, 'main sentence'):
            evidence.validated_review(text, result, self.sources)

    def test_benchmark_source_claim_is_scoped_without_an_extra_model_call(self):
        source = 'Aster leads our benchmark with 42 points.'
        text = '🧠 Aster лидирует в тесте\n\nЧто произошло: Aster набрала 42 балла в тесте.'
        result = verdicts(text, source)
        for row in result['checks']:
            row.update(entity='Aster', event='benchmark')
        review = evidence.validated_review(text, result, [{'url':'official', 'text':source}])
        self.assertTrue(review['text'].startswith('🧠 Aster\n'))
        self.assertIn('По данным источника, Aster', review['text'])
        self.assertFalse(evidence.final_issues(source, review['text'], review))

    def test_aggregate_index_cannot_be_relabelled_as_a_subtest(self):
        source = 'Aster scores 61 on the Decision Index. The knowledge test is also reported.'
        self.assertTrue(evidence.bound_issues(source, 'В тесте knowledge Aster набрала 61 балл.', {}))

    def test_score_metric_cannot_be_replaced_by_an_unnamed_knowledge_subtest(self):
        source='Aster scores 47 on the Capability Index. Knowledge and reasoning are components.'
        self.assertTrue(evidence.bound_issues(source,'В тестах на знания Aster набрала 47 баллов.',{}))
        self.assertFalse(evidence.bound_issues(source,'В Capability Index Aster набрала 47 баллов.',{}))
        self.assertEqual(evidence.scope_score(source,'Aster набрала 47 баллов.'),
                         'Capability Index: Aster набрала 47 баллов.')

    def test_one_result_cannot_be_assigned_to_a_list_of_distinct_tests(self):
        source='Aster is scoring 47.2 on EvalClaw versus 39.1.'
        self.assertTrue(evidence.bound_issues(source,'На тестах (AutoBench, EvalClaw) Aster набрала 47.2 балла.',{}))
        self.assertFalse(evidence.bound_issues(source,'На EvalClaw Aster набрала 47.2 балла.',{}))

    def test_equal_scores_on_different_metrics_are_ambiguous(self):
        source='Aster scores 47 on Capability Index. Beta scores 47 on EvalClaw.'
        self.assertFalse(evidence.bound_issues(source,'В Capability Index Aster набрала 47 баллов.',{}))
        self.assertEqual(evidence.score_bindings('Aster scores 47 on Capability Index Beta scores 9.'),
                         [('47','Capability Index')])

    def test_product_alias_is_expanded_only_by_its_original_subject_title(self):
        source='Aster8.2-Prime is now available in the app.'
        text='🧠 Prime\n\nЧто произошло: Aster8.2-Prime появилась в приложении.'
        result=verdicts(text,source)
        for row in result['checks']:
            row.update(entity='Prime',event='availability')
        review=evidence.validated_review(text,result,[{'url':'official','text':source}])
        key=evidence.event_key(review,'Aster8.2-Prime is now available.')
        for row in review['claims']:row['entity']='Aster8.2-Prime'
        self.assertEqual(evidence.event_key(review,'Aster8.2-Prime is now available.'),key)
        self.assertEqual(key[0],'aster8.2 prime')

    def test_throughput_configuration_survives_even_when_metadata_is_empty(self):
        source = 'Aster reaches 685 output tokens/s per user on 4 x GB300 in NVFP4.'
        self.assertTrue(evidence.bound_issues(source, 'Aster выдаёт 685 токенов в секунду.', {}))
        self.assertFalse(evidence.bound_issues(source, 'Aster выдаёт 685 токенов в секунду на одного пользователя на 4 GB300 в NVFP4.', {}))
        self.assertTrue(evidence.bound_issues('184 tokens per second on Apple M5 Max.',
                                             '184 токенов в секунду.', {'conditions':'Apple M5 Max'}))

    def test_model_with_a_preview_name_is_not_a_standard(self):
        source = 'Nimbus-7-Preview is a new model for developers.'
        self.assertTrue(evidence.bound_issues(source, 'Принят стандарт Nimbus-7-Preview.', {}))
        self.assertFalse(evidence.bound_issues(source, 'Модель Nimbus-7-Preview доступна разработчикам.', {}))

    def test_literal_fact_values_units_and_dates_require_quoted_evidence(self):
        for field, value in (('value', '256K'), ('unit', 'characters'), ('date', '2032-05-01'),
                             ('conditions', 'high concurrency'), ('version', '2.0')):
            result = verdicts();result['checks'][1][field] = value
            with self.subTest(field=field):
                review = evidence.validated_review(TEXT, result, self.sources)
                main = next(row for row in review['claims'] if row['field']=='what')
                self.assertEqual(main[field], '')
                self.assertIn(field, main['metadata_repairs'])

    def test_invented_date_or_value_in_prose_is_not_saved_by_cleaning_metadata(self):
        for sentence in ('Aster-8B-A1B выпущена 17 октября 2032 года.',
                         'Aster-8B-A1B получила 256 тыс. токенов контекста.'):
            text = TEXT.replace('Aster-8B-A1B получила поддержку Engine.', sentence)
            with self.subTest(sentence=sentence), self.assertRaisesRegex(ValueError, 'main sentence'):
                evidence.validated_review(text, verdicts(text), self.sources)

    def test_mislabelled_unit_is_rejected_without_model_specific_rules(self):
        text = TEXT.replace('Aster-8B-A1B получила поддержку Engine.', 'Контекст — 128 тыс. символов.')
        with self.assertRaisesRegex(ValueError, 'main sentence'):
            evidence.validated_review(text, verdicts(text), self.sources)
        text = text.replace('символов', 'токенов')
        self.assertIn('128 тыс. токенов', evidence.validated_review(text, verdicts(text), self.sources)['text'])

    def test_signed_values_and_scale_are_not_a_bag_of_unsigned_digits(self):
        self.assertEqual(evidence.numbers('128K tokens'), evidence.numbers('128 тыс. токенов'))
        self.assertTrue(evidence.bound_issues('Measured improvement was +7%.', 'Результат изменился на −7%.', {}))
        self.assertFalse(evidence.bound_issues('Measured improvement was +7%.', 'Результат вырос на 7%.', {}))

    def test_header_and_main_fact_are_not_deduplicated_into_an_empty_story(self):
        result = verdicts()
        result['checks'][0]['attribute'] = result['checks'][1]['attribute'] = 'support'
        review = evidence.validated_review(TEXT, result, self.sources)
        self.assertIn('поддержку Engine', review['text'])

    def test_source_url_is_assigned_by_caller(self):
        result = verdicts(); result['checks'][1]['source_url'] = 'https://invented.example'
        review = evidence.validated_review(TEXT, result, self.sources)
        self.assertTrue(all(row['source_url']==self.sources[0]['url'] for row in review['claims']))

    def test_separate_literal_spans_support_compound_fact_without_splicing(self):
        spans=['Aster-8B-A1B is a model with 128K tokens of context.', 'It is now supported by Engine.']
        result=verdicts()
        for row in result['checks']:
            row['quote']=spans
        review=evidence.validated_review(TEXT,result,self.sources)
        self.assertEqual(review['claims'][1]['evidence_spans'],spans)
        result['checks'][1]['quote']=[spans[0], 'It is available for free on Engine.']
        with self.assertRaisesRegex(ValueError,'main sentence'):
            evidence.validated_review(TEXT,result,self.sources)

    def test_quote_typography_is_rebound_to_the_exact_original_span(self):
        source='The model’s context is 128K tokens. It supports Engine.'
        quote="The model's context is 128K tokens."
        self.assertEqual(evidence.literal_span(source,quote),'The model’s context is 128K tokens.')
        self.assertIsNone(evidence.literal_span(source,quote.replace('128K','256K')))
        self.assertIsNone(evidence.literal_span(source,quote.replace('context','vocabulary')))
        self.assertIsNone(evidence.literal_span(source,'The model’s ... 128K tokens.'))

    def test_main_failure_reports_the_specific_unit_problem_to_existing_repair(self):
        text=TEXT.replace('Aster-8B-A1B получила поддержку Engine.','Контекст — 128 тыс. символов.')
        with self.assertRaisesRegex(ValueError,'Quantity unit'):
            evidence.validated_review(text,verdicts(text),self.sources)

    def test_event_subject_uses_verified_heading_not_subordinate_integration(self):
        source='Aster 8 arrives in the app with Helper integration.'
        text='🧠 Aster 8\n\nЧто произошло: Aster 8 доступна в приложении с Helper.'
        result=verdicts(text,source)
        for row in result['checks']:
            row.update(entity='Aster 8',version='8',event='availability')
        review=evidence.validated_review(text,result,[{'url':'official','text':source}])
        key=evidence.event_key(review)
        review['claims'][1].update(entity='Helper',version='')
        review['claims'][0]['event']='release'
        self.assertEqual(evidence.event_key(review),key)
        self.assertEqual(key[:2],('aster 8',''))

    def test_company_alone_cannot_merge_unrelated_product_launches(self):
        review=evidence.validated_review(TEXT,verdicts(),self.sources)
        for row in review['claims']:
            row.update(entity='Aster Labs',kind='company',event='release')
        self.assertIsNone(evidence.event_key(review))

    def test_source_claim_cannot_be_labelled_independently_proven(self):
        result = verdicts();result['checks'][1]['basis'] = 'independently_verified'
        with self.assertRaisesRegex(ValueError, 'main sentence'):
            evidence.validated_review(TEXT, result, self.sources)

    def test_malformed_optional_metadata_does_not_crash_a_valid_main_event(self):
        result=verdicts();result['checks'][-1]['entity']=123
        review=evidence.validated_review(TEXT,result,self.sources)
        self.assertIn('поддержку Engine',review['text'])
        self.assertNotIn('бесплатно',review['text'])

    def test_date_unknown_is_not_replaced_by_discovery_date(self):
        review = evidence.validated_review(TEXT, verdicts(), self.sources)
        self.assertTrue(all(row['date']=='' for row in review['claims']))

    def test_one_verifier_call_produces_a_structured_ledger(self):
        with patch('ainews.pipeline.ollama_json', return_value=verdicts()) as model:
            review = verify_draft({'_structured_review': True, '_source_url': 'official'}, 'Aster', SOURCE, TEXT)
        self.assertEqual(model.call_count, 1)
        self.assertIn('claims', review)
        self.assertIn('checks', model.call_args.args[2]['properties'])

    def test_large_documents_remain_distinct_in_verifier_input(self):
        docs = [{'url': 'one', 'text': SOURCE+' filler'*1700}, {'url': 'two', 'text': 'Other data. '*1200}]
        with patch('ainews.pipeline.ollama_json', return_value=verdicts()) as model:
            verify_draft({'_structured_review': True, '_source_documents': docs}, 'Aster', SOURCE, TEXT)
        inputs = json.loads(model.call_args.args[1])['sources']
        self.assertEqual([row['url'] for row in inputs], ['one', 'two'])
        self.assertLess(sum(len(row['text']) for row in inputs), 6500)

    def test_formatter_cannot_remove_conditions_inside_a_verified_sentence(self):
        review = evidence.validated_review(TEXT, verdicts(), self.sources)
        fields = {'headline': 'Aster-8B-A1B', 'what': 'Aster-8B-A1B получила поддержку Engine.', 'simple': '', 'why': '', 'caveat': ''}
        self.assertFalse(evidence.final_issues(SOURCE, card(fields), review))
        fields['what'] = 'Aster-8B-A1B получила поддержку.'
        self.assertTrue(evidence.final_issues(SOURCE, card(fields), review))

    def test_numeric_abbreviation_does_not_detach_unit_and_lowercase_brand_starts_sentence(self):
        value = 'Контекст — 128 тыс. токенов. vEngine поддерживает модель.'
        self.assertEqual(evidence.sentences(value), ['Контекст — 128 тыс. токенов.', 'vEngine поддерживает модель.'])

    def test_release_support_and_platforms_have_distinct_event_identity(self):
        review = evidence.validated_review(TEXT, verdicts(), self.sources)
        initial = evidence.event_key(review)
        review['claims'][1]['event'] = 'release'
        self.assertNotEqual(evidence.event_key(review), initial)
        review['claims'][1]['event'] = 'support';review['claims'][1]['platform'] = 'AnotherEngine'
        self.assertNotEqual(evidence.event_key(review), initial)

    def test_stale_source_cannot_reuse_claim_ledger(self):
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
            review = evidence.validated_review(TEXT, verdicts(), self.sources)
            review['source_hash'] = evidence.digest(SOURCE)
            store.record_editorial('url', 'claim_ledger', review)
            self.assertIsNotNone(evidence.load_ledger(store, {'url': 'url', 'article': SOURCE, 'summary': ''}))
            self.assertIsNone(evidence.load_ledger(store, {'url': 'url', 'article': SOURCE+' Updated.', 'summary': ''}))

    def test_daily_prepare_uses_writer_and_verifier_without_style_rewrite(self):
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
            url = 'https://x.com/AsterTeam/status/123'
            store.add_feed('official', [Entry('official', 'Aster-8B-A1B', url,
                           datetime.now(timezone.utc).isoformat(), SOURCE)], include_existing=True)
            draft = {'relevant': True, 'confidence': 'high', 'headline': 'Aster-8B-A1B',
                     'what_happened': 'Aster-8B-A1B получила поддержку Engine.',
                     'simple_explanation': '', 'why_it_matters': 'Она доступна бесплатно.',
                     'caveat': '', 'evidence': SOURCE}
            result = verdicts();result['checks'][-1]['status'] = 'unsupported'
            config = {'publication_mode':'daily', 'sources':[{'name':'official', 'type':'x',
                       'handle':'AsterTeam', 'primary_account':True, 'auto_publish':True}]}
            with patch('ainews.pipeline.ollama_json', side_effect=[draft, result]) as model, \
                 patch('ainews.pipeline.polish_draft') as style:
                prepare(config, store, limit=1)
            row = store.db.execute('SELECT * FROM items').fetchone()
            self.assertEqual(row['state'], 'ready', row['error'])
            self.assertNotIn('бесплатно', row['draft'])
            self.assertEqual(model.call_count, 2)
            style.assert_not_called()
            self.assertIsNotNone(evidence.load_ledger(store, row))
