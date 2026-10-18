import json
from io import BytesIO
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ainews.digest import card
from ainews.feeds import Entry
from ainews.measurements import bindings, measurement_issues, numeric_values
from ainews.pipeline import (VerificationFailure, VerificationProtocolError, draft_text,
                             enrich_primary_post, ollama_json, polish_draft, prepare, prerelease_url,
                             revise_draft, verification_claims, verification_sources, verified_subset, verify_draft)
from ainews.quality import check_semantic_claims, source_window
from ainews.store import Store


class MeasurementBindings(unittest.TestCase):
    def test_distinct_token_directions_cannot_borrow_each_others_values(self):
        source='Output: 720 tokens/s. Input: 240 tokens/s. Cached: 3600 tokens/s.'
        self.assertFalse(measurement_issues(source, 'Скорость генерации: 720 токенов в секунду.'))
        for text in ['Скорость генерации: 240 токенов в секунду.',
                     'Входных: 3600 токенов в секунду.']:
            with self.subTest(text=text):self.assertTrue(measurement_issues(source,text))

    def test_aggregate_is_not_generation_and_retains_its_accounting_scope(self):
        source='Throughput: 920K tok/s per GPU (cached + input + output) at 120 tok/s per user.'
        valid='Совокупная скорость: 920 тыс. токенов в секунду на GPU (кэш, ввод и вывод) при 120 токенов в секунду на пользователя.'
        self.assertFalse(measurement_issues(source, valid))
        for text in [valid.replace('Совокупная скорость','Скорость генерации'),
                     valid.replace('на GPU','на пользователя'),
                     valid.replace(' (кэш, ввод и вывод)',''),
                     valid.replace(' при 120 токенов в секунду на пользователя','')]:
            with self.subTest(text=text):self.assertTrue(measurement_issues(source,text))

    def test_hardware_and_magnitude_are_not_optional_for_a_measured_rate(self):
        source='Throughput: 180K tokens/s per GPU on A100.'
        self.assertFalse(measurement_issues(source,'Совокупная скорость: 180 тыс. токенов в секунду на GPU A100.'))
        self.assertTrue(measurement_issues(source,'Совокупная скорость: 180 токенов в секунду на GPU A100.'))
        self.assertTrue(measurement_issues(source,'Совокупная скорость: 180 тыс. токенов в секунду на GPU.'))

    def test_user_scope_can_precede_the_rate_without_being_lost(self):
        source='Throughput is 900K tok/s/GPU at 80 tok/s per user.'
        draft='Совокупная скорость — 900 тыс. токенов в секунду на GPU, при скорости для пользователя 80 токенов в секунду.'
        self.assertFalse(measurement_issues(source,draft))
        check_semantic_claims(source,draft)
        accounting='Throughput is 900K tok/s/GPU (cached + input + output) at 80 tok/s per user.'
        self.assertFalse(measurement_issues(accounting,'Скорость для пользователя — 80 токенов в секунду.'))

    def test_tco_efficiency_is_not_api_pricing(self):
        source='Serving delivers 2B tokens per dollar TCO.'
        self.assertFalse(measurement_issues(source,'Эффективность — 2 млрд токенов за доллар TCO.'))
        self.assertTrue(measurement_issues(source,'Цена API — 2 млрд токенов за доллар.'))

    def test_cost_efficiency_does_not_inherit_a_later_gpu_rate_scope(self):
        source='Serving delivers 2B tokens per dollar TCO: throughput is 900K tok/s/GPU.'
        self.assertEqual(bindings(source)[0]['scope'],'gpu')
        efficiency=next(row for row in bindings(source) if row['unit']=='tokens/USD')
        self.assertEqual(efficiency['scope'],'')
        self.assertFalse(measurement_issues(source,'Эффективность — 2 млрд токенов за доллар TCO.'))

    def test_preference_is_not_complaint_count(self):
        source='On Praise vs Complaint, the lab sits at +27 points over average.'
        self.assertFalse(measurement_issues(source,'Показатель предпочтений — +27 пунктов выше среднего.'))
        self.assertTrue(measurement_issues(source,'Показатель по жалобам — +27 пунктов выше среднего.'))

    def test_group_values_above_average_are_not_gaps_to_the_leader(self):
        source='On Praise vs Complaint, Lab A is +40 points over average. Lab B lands between +5 and +17.'
        with self.assertRaisesRegex(ValueError,'reference baseline'):
            check_semantic_claims(source,'Lab A выше среднего на 40 пунктов, остальные отстают на 5–17.')
        check_semantic_claims(source,'Lab A на 40 пунктов выше среднего. Lab B показывает от +5 до +17 относительно среднего.')

    def test_tuple_keeps_subject_source_and_conditions_for_audit(self):
        row=bindings('Throughput: 10K tokens/s per GPU on B200.',subject='Aster serving',source='https://official.example/report')[0]
        self.assertEqual((row['metric'],row['value'],row['unit'],row['scope']),('aggregate_rate','1E+4','tokens/s','gpu'))
        self.assertEqual(row['object'],'Aster serving')
        self.assertEqual(row['source'],'https://official.example/report')
        self.assertEqual(row['conditions']['hardware'],['B200'])

    def test_numeric_equivalence_keeps_decimal_and_scaled_quantities(self):
        self.assertEqual(numeric_values('3.0%'),numeric_values('3%'))
        self.assertEqual(numeric_values('800K tokens'),numeric_values('0.8 млн токенов'))
        self.assertEqual(numeric_values('1,400 pull requests'),numeric_values('1400 PR'))
        self.assertEqual(numeric_values('5 max'),{'5'})
        self.assertIn('17',numeric_values('2026-10-17'))
        self.assertEqual(numeric_values('1M tokens'),numeric_values('1 миллион токенов'))
        self.assertEqual(numeric_values('Five engineers in two weeks.'),numeric_values('5 инженеров за 2 недели.'))

    def test_vendor_results_do_not_establish_independent_measurements(self):
        with self.assertRaisesRegex(ValueError,'independent'):
            check_semantic_claims('The vendor reports a benchmark.','Независимые измерения показали ускорение.')
        check_semantic_claims('An independent evaluation reports improvements.','Независимые измерения показали ускорение.')

    def test_comparison_inherits_units_without_inventing_device_ownership(self):
        source='Throughput is 7,230 vs 6,110 tok/s/GPU at 70 tok/s/user.'
        rows=[r for r in bindings(source) if r['scope']=='gpu']
        self.assertEqual([(r['value'],r['comparison_position']) for r in rows],[('7.23E+3','left'),('6.11E+3','right')])
        self.assertFalse(measurement_issues(source,'Совокупная скорость — 7230 токенов в секунду на GPU при 70 токенов в секунду на пользователя.'))
        self.assertTrue(measurement_issues(source,'Скорость генерации — 7230 токенов в секунду на GPU при 70 токенов в секунду на пользователя.'))

    def test_new_counts_do_not_become_total_participant_counts(self):
        source='Two new teams and three new models have joined the benchmark.'
        self.assertTrue(measurement_issues(source,'Три новые модели от двух команд появились в рейтинге.'))
        self.assertFalse(measurement_issues(source,'Появились две новые команды и три новые модели.'))
        self.assertIn('2',numeric_values(source))
        self.assertFalse(bindings('GPT-14 новая модель.'))

    def test_top_rank_does_not_mean_first_ever_in_its_class(self):
        source='Breeze is the #1 European open model on the benchmark.'
        with self.assertRaisesRegex(ValueError,'first place'):
            check_semantic_claims(source,'Breeze стала первой открытой моделью Европы.')
        check_semantic_claims(source,'Breeze заняла первое место среди открытых моделей Европы в этом тесте.')

    def test_power_normalized_rate_does_not_borrow_an_earlier_user_scope(self):
        source='At 80 tokens/s per user, B200 leads with throughput of 180M tokens/s per MW.'
        rate=next(row for row in bindings(source) if row['value']=='1.8E+8')
        self.assertEqual((rate['scope'],rate['metric']),('mw','aggregate_rate'))
        valid='Совокупная скорость B200 — 180 млн токенов в секунду на МВт при 80 токенов в секунду на пользователя.'
        self.assertFalse(measurement_issues(source,valid))
        self.assertTrue(measurement_issues(source,valid.replace(' на МВт','')))

    def test_grouped_spaces_are_numeric_formatting_not_extra_values(self):
        for text in ['192 512 токенов','192\u00a0512 токенов','192\u202f512 токенов']:
            self.assertEqual(numeric_values('192,512 tokens'),numeric_values(text))

    def test_company_pronoun_cannot_transfer_an_explicit_product_owner(self):
        source="Aster released Dawn. Boreal’s first model Breeze is also relevant."
        with self.assertRaisesRegex(ValueError,'developer attribution'):
            check_semantic_claims(source,'Компания Aster выпустила Dawn. Также компания анонсировала модель Boreal Breeze.')
        check_semantic_claims(source,'Компания Aster выпустила Dawn. Компания Boreal представила Breeze.')
        check_semantic_claims("Aster Research’s first model Breeze is released.",'Aster представила модель Breeze.')

    def test_near_a_model_is_not_better_than_it(self):
        source='Dawn scores above Aster 2.0, near Boreal 3.0.'
        with self.assertRaisesRegex(ValueError,'Comparable performance'):
            check_semantic_claims(source,'Dawn выше Aster 2.0 и Boreal 3.0.')
        check_semantic_claims(source,'Dawn выше Aster 2.0, но на уровне Boreal 3.0.')

    def test_dataset_does_not_establish_a_teacher_and_rl_is_not_rlhf(self):
        source='This lecture covers distillation as an alternative to reinforcement learning. Loading the Dawn MATH dataset.'
        with self.assertRaisesRegex(ValueError,'teacher model'):
            check_semantic_claims(source,'В качестве учителя использовали модель Dawn.')
        with self.assertRaisesRegex(ValueError,'human feedback'):
            check_semantic_claims(source,'Это альтернатива методам обратной связи от пользователя.')
        check_semantic_claims(source,'Урок посвящён дистилляции как альтернативе обучению с подкреплением.')
        check_semantic_claims(source+' Distillation from the teacher Dawn.', 'В качестве учителя использовали модель Dawn.')


class ClaimVerification(unittest.TestCase):
    source='Aster released a 7B model for local use.'
    text='Модель Aster выпущена. Она работает локально.'

    def checks(self, **change):
        rows=[{'id':i,'status':'supported','evidence_ids':[0],'issue':''} for i in range(2)]
        rows[0].update(change)
        return {'checks':rows}

    def test_each_claim_needs_a_source_bound_verdict(self):
        with patch('ainews.pipeline.ollama_json',return_value=self.checks()) as model:
            verify_draft({'_source_url':'https://official.example/report'},'Aster release',self.source,self.text)
        payload=json.loads(model.call_args.args[1])
        self.assertEqual([c['id'] for c in payload['claims']],[0,1])
        self.assertIn('measurements',payload)
        self.assertEqual(model.call_args.args[2]['properties']['checks']['minItems'],2)
        self.assertEqual(model.call_args.args[2]['properties']['checks']['maxItems'],2)
        items=model.call_args.args[2]['properties']['checks']['items']['properties']
        self.assertEqual(items['id']['enum'],[0,1])
        self.assertEqual(items['evidence_ids']['items']['enum'],[0])

    def test_missing_duplicate_and_unknown_claim_ids_are_rejected(self):
        for ids in [[0],[0,0],[0,3]]:
            result=self.checks();result['checks']=[{**result['checks'][0],'id':i} for i in ids]
            with self.subTest(ids=ids),patch('ainews.pipeline.ollama_json',return_value=result),self.assertRaises(VerificationProtocolError):
                verify_draft({},'Aster',self.source,self.text)

    def test_approval_with_a_contradictory_issue_or_fabricated_reference_fails(self):
        for change in [{'evidence_ids':[999]},{'evidence_ids':[]},{'issue':'Not confirmed.'}]:
            with self.subTest(change=change),patch('ainews.pipeline.ollama_json',return_value=self.checks(**change)),self.assertRaises(VerificationProtocolError):
                verify_draft({},'Aster',self.source,self.text)

    def test_uncertainty_is_not_approval_and_does_not_trigger_a_second_verdict(self):
        with patch('ainews.pipeline.ollama_json',return_value=self.checks(status='uncertain',evidence_ids=[],issue='Ownership unknown.')) as model:
            with self.assertRaisesRegex(VerificationFailure,'Ownership unknown'):
                verify_draft({},'Aster',self.source,self.text)
        model.assert_called_once()

    def test_legacy_boolean_cannot_bypass_per_claim_verification(self):
        with patch('ainews.pipeline.ollama_json',return_value={'supported':True,'unsupported_claims':[]}),self.assertRaises(VerificationProtocolError):
            verify_draft({},'Aster',self.source,self.text)

    def test_source_ids_derive_exact_quotes_and_origin_without_mutating_model_output(self):
        documents=[{'url':'https://official.example/post','text':'Aster is released.'},
                   {'url':'https://official.example/report','text':self.source,'role':'linked_background'}]
        events=[]
        result={'checks':[{'id':0,'status':'supported','evidence_ids':[1],'issue':''}]}
        with patch('ainews.pipeline.ollama_json',return_value=result):
            verify_draft({'_source_documents':documents,'_audit':lambda stage,data:events.append((stage,data))},
                         'Aster', 'Aster is released. '+self.source,'Модель содержит 7 млрд параметров.')
        derived=next(d for stage,d in events if stage=='verified_claims')['checks'][0]
        self.assertEqual(derived['quotes'],[self.source])
        self.assertEqual(derived['sources'],['https://official.example/report'])
        self.assertNotIn('quotes',result['checks'][0])

    def test_non_integer_source_reference_is_not_coerced(self):
        for reference in ['0',True,{},[]]:
            with self.subTest(reference=reference),patch('ainews.pipeline.ollama_json',return_value=self.checks(evidence_ids=[reference])),self.assertRaises(VerificationProtocolError):
                verify_draft({},'Aster',self.source,self.text)


class TargetedRepair(unittest.TestCase):
    source='Aster released a 7B model for local use.'

    def draft(self):
        return {'relevant':True,'confidence':'high','headline':'Aster получила обновление',
                'what_happened':'Выпущена модель Aster с 7 млрд параметров.',
                'simple_explanation':'Она помогает всем профессиям.',
                'why_it_matters':'','caveat':'','evidence':self.source}

    def failure(self,text,reject):
        claims=verification_claims(text)
        return VerificationFailure(claims,[{'id':c['id'],'status':'unsupported' if reject(c['text']) else 'supported',
            'quote':self.source,'issue':'No evidence.' if reject(c['text']) else ''} for c in claims])

    def test_only_optional_unsupported_sentence_is_removed(self):
        draft=self.draft();text=draft_text(draft,self.source)
        repaired=verified_subset(draft,text,self.failure(text,lambda s:'профессиям' in s),self.source,'Aster')
        self.assertIsNotNone(repaired)
        self.assertNotIn('профессиям',repaired[1]);self.assertIn('7 млрд',repaired[1])
        self.assertIn('профессиям',draft['simple_explanation'])

    def test_main_event_headline_and_restrictions_cannot_be_dropped(self):
        draft=self.draft();draft['simple_explanation']='Доступна только подписчикам.'
        source=self.source+' Access is only for subscribers.'
        text=draft_text(draft,source)
        for fragment in ['Aster получила','7 млрд','только']:
            with self.subTest(fragment=fragment):
                self.assertIsNone(verified_subset(draft,text,self.failure(text,lambda s:fragment in s),source,'Aster'))

    def test_complete_impact_counts_precede_optional_explanation_in_compaction(self):
        fields={'headline':'Aster автоматизирует поддержку', 'what':'Команда автоматизировала поддержку кода.',
                'simple':'Пять инженеров подготовили 1200 PR за 2 недели.',
                'why':'Автоматизация уменьшает объём ручной работы при типовых задачах обслуживания большого проекта.','caveat':''}
        text=card(fields,max_chars=170,detail_first=True)
        self.assertIn('1200 PR за 2 недели',text)
        self.assertNotIn('объём ручной работы',text)

    def test_style_cannot_move_quantified_properties_to_another_product(self):
        original={**self.draft(),'caveat':'Доступна только подписчикам.'}
        edited={**original,'what_happened':'Инструмент Engine имеет 70 млрд параметров.', 'caveat':''}
        with patch('ainews.pipeline.ollama_json',return_value=edited):
            result=polish_draft({},'Aster',self.source,original)
        self.assertEqual(result['what_happened'],original['what_happened'])
        self.assertEqual(result['caveat'],original['caveat'])

    def test_style_is_not_called_without_editable_explanations(self):
        original={**self.draft(),'simple_explanation':''}
        with patch('ainews.pipeline.ollama_json') as model:
            self.assertEqual(polish_draft({},'Aster',self.source,original),original)
        model.assert_not_called()

    def test_targeted_revision_keeps_unaffected_quantitative_paragraph(self):
        original={**self.draft(),'simple_explanation':'','why_it_matters':'Модель ускоряет работу без потери качества.'}
        edited={**original,'what_happened':'Вышла другая модель.', 'why_it_matters':''}
        with patch('ainews.pipeline.ollama_json',return_value=edited):
            result=revise_draft({},'Aster',self.source,original,'Source does not establish a no-loss quality or accuracy guarantee')
        self.assertEqual(result['what_happened'],original['what_happened'])
        self.assertEqual(result['why_it_matters'],'')

    def test_unproven_optional_guarantee_does_not_discard_the_main_facts(self):
        draft={**self.draft(),'simple_explanation':'',
               'why_it_matters':'Модель работает без потери качества.'}
        text=draft_text(draft,self.source)
        self.assertIn('7 млрд',text);self.assertNotIn('без потери',text)
        self.assertIn('без потери',draft['why_it_matters'])
        draft['what_happened']+=' Она работает без потери качества.'
        with self.assertRaisesRegex(ValueError,'no-loss quality'):
            draft_text(draft,self.source)

    def test_repairing_ownership_retains_untouched_quantitative_sentences(self):
        source="Boreal’s first model Breeze is released. The model has 7B parameters."
        original={**self.draft(),'what_happened':'Aster представила модель Breeze. Модель имеет 7 млрд параметров.'}
        edited={**original,'what_happened':'Boreal представила модель Breeze.'}
        with patch('ainews.pipeline.ollama_json',return_value=edited):
            result=revise_draft({},'Breeze',source,original,'Product ownership differs from the explicit source')
        self.assertEqual(result['what_happened'],'Boreal представила модель Breeze. Модель имеет 7 млрд параметров.')
        check_semantic_claims(source,result['what_happened'])

    def test_source_handles_become_plain_names_but_unknown_mentions_stay_blocked(self):
        source=self.source+' Built by @AsterLab.'
        draft={**self.draft(),'what_happened':self.draft()['what_happened']+' Разработчик — @AsterLab.'}
        text=draft_text(draft,source)
        self.assertIn('AsterLab',text);self.assertNotIn('@',text)
        self.assertIn('@AsterLab',source);self.assertIn('@AsterLab',draft['what_happened'])
        draft['what_happened']=draft['what_happened'].replace('@AsterLab','@UnknownLab')
        with self.assertRaisesRegex(ValueError,'link or handle'):
            draft_text(draft,source)

    def test_source_window_retains_count_units_duration_and_ownership(self):
        fact='Five engineers merged 1,200 pull requests, deleting 700k lines of code in two weeks.'
        owner='This tool is not affiliated with any model provider.'
        source='Intro. '*400+fact+' Context. '*400+owner+' Footer. '*200
        result=source_window(source,2500)
        self.assertLessEqual(len(result),2500)
        self.assertIn(fact,result);self.assertIn(owner,result)

    def test_weights_are_not_source_code_even_when_both_are_open(self):
        with self.assertRaisesRegex(ValueError,'weights are parameters'):
            check_semantic_claims('Model source code and weights are released.','Доступен открытый исходный код весов модели.')

    def test_neighboring_company_cannot_own_an_explicitly_attributed_product(self):
        source="Aster led with Dawn, but Boreal’s first model Breeze is also relevant."
        with self.assertRaisesRegex(ValueError,'developer attribution'):
            check_semantic_claims(source,'Также Aster анонсировала модель Boreal Breeze.')
        check_semantic_claims(source,'Boreal выпустила модель Breeze.')


class SourceEnrichment(unittest.TestCase):
    def test_same_frozen_post_fetches_linked_primary_once_without_overwriting_dates(self):
        with tempfile.TemporaryDirectory() as temp,closing(Store(Path(temp)/'test.db')) as store:
            url='https://x.com/official/status/123'
            summary='Our engineers shared a report: https://developers.openai.com/blog/example'
            store.add_feed('official',[Entry('official','Engineering report',url,datetime.now(timezone.utc).isoformat(),summary)],include_existing=True)
            row=store.db.execute('SELECT * FROM items').fetchone()
            with patch('ainews.pipeline.article_details',return_value=('Five engineers merged 1200 PRs in two weeks.','2025-01-01')) as fetch:
                first=enrich_primary_post({},store,row,summary)
                second=enrich_primary_post({},store,row,summary)
            fetch.assert_called_once();self.assertEqual(first,second)
            self.assertIn('1200 PRs',first);self.assertIn('не дата нового события',first)
            saved=store.db.execute('SELECT * FROM items').fetchone()
            self.assertEqual(saved['summary'],summary)
            self.assertIsNone(store.db.execute('SELECT original_published FROM source_dates').fetchone()[0])

    def test_optional_source_failure_does_not_fabricate_content(self):
        with tempfile.TemporaryDirectory() as temp,closing(Store(Path(temp)/'test.db')) as store:
            summary='Announcement https://github.com/example/project'
            row={'url':'https://x.com/official/status/123','summary':summary}
            with patch('ainews.pipeline.article_details',side_effect=TimeoutError) as fetch:
                self.assertEqual(enrich_primary_post({},store,row,summary),summary)
                self.assertEqual(enrich_primary_post({},store,row,summary),summary)
            fetch.assert_called_once()

    def test_old_linked_release_date_is_not_a_current_integration_date(self):
        with tempfile.TemporaryDirectory() as temp,closing(Store(Path(temp)/'test.db')) as store:
            summary='Runtime now supports Aster 2.0. https://developers.openai.com/blog/example'
            store.add_feed('official',[Entry('official','Runtime supports Aster 2.0','https://x.com/official/status/123',
                datetime.now(timezone.utc).isoformat(),summary)],include_existing=True)
            config={'publication_mode':'daily','sources':[{'name':'official','type':'x','primary_account':True,'auto_publish':True}]}
            with patch('ainews.pipeline.article_details',return_value=('Release Date: January 1, 2025. Aster model announcement.', '2025-01-01')), \
                 patch('ainews.pipeline.generate_draft',return_value={'relevant':False}):
                prepare(config,store,limit=1)
            dates=store.db.execute('SELECT original_published,event_date FROM source_dates').fetchone()
            self.assertEqual(tuple(dates),(None,None))

    def test_joined_release_candidate_suffix_is_not_a_stable_release(self):
        for tag in ['v2.8.0rc3','v2.8.0beta1','v2.8.0-alpha.2']:
            self.assertTrue(prerelease_url('https://github.com/example/project/releases/tag/'+tag))
        self.assertFalse(prerelease_url('https://github.com/example/project/releases/tag/v2.8.0'))


class RepairIntegration(unittest.TestCase):
    source=TargetedRepair.source
    draft=TargetedRepair.draft
    failure=TargetedRepair.failure

    def run_preparation(self, verifier, revise):
        with tempfile.TemporaryDirectory() as temp,closing(Store(Path(temp)/'test.db')) as store:
            store.add_feed('official',[Entry('official','Aster model release','https://official.example/release',
                datetime.now(timezone.utc).isoformat(),self.source)],include_existing=True)
            config={'publication_mode':'daily','sources':[{'name':'official','hosts':['official.example'],'auto_publish':True,'content_from_feed':True}]}
            with patch('ainews.pipeline.article_details',return_value=(self.source,None)), \
                 patch('ainews.pipeline.generate_draft',return_value=self.draft()), \
                 patch('ainews.pipeline.polish_draft',side_effect=lambda config,title,source,draft:draft), \
                 patch('ainews.pipeline.verify_draft',side_effect=verifier) as verify, \
                 patch('ainews.pipeline.revise_draft',side_effect=revise) as revision:
                prepare(config,store,limit=1)
            return dict(store.db.execute('SELECT * FROM items').fetchone()),verify.call_count,revision.call_count

    def test_unchanged_revision_stops_without_reverification(self):
        row,checks,revisions=self.run_preparation(ValueError('Unsupported main event'),lambda *args:self.draft())
        self.assertEqual((row['state'],checks,revisions),('needs_review',1,1))

    def test_protocol_error_does_not_rewrite_facts(self):
        row,checks,revisions=self.run_preparation(VerificationProtocolError('Missing ids'),lambda *args:self.fail('Unexpected rewrite'))
        self.assertEqual((row['state'],checks,revisions),('needs_review',1,0))

    def test_verified_optional_subset_is_published_without_a_second_model_call(self):
        def verifier(config,title,source,text,**kwargs):
            raise self.failure(text,lambda s:'профессиям' in s)
        row,checks,revisions=self.run_preparation(verifier,lambda *args:self.fail('Unexpected rewrite'))
        self.assertEqual((row['state'],checks,revisions),('ready',1,0))
        self.assertIn('7 млрд',row['draft']);self.assertNotIn('профессиям',row['draft'])

    def test_secondary_headline_cannot_supply_missing_primary_numbers(self):
        with tempfile.TemporaryDirectory() as temp,closing(Store(Path(temp)/'test.db')) as store:
            store.add_feed('repost',[Entry('repost','Aster reached 500 tokens/s','https://t.me/example/123',
                datetime.now(timezone.utc).isoformat(),'Details: https://huggingface.co/blog/example')],include_existing=True)
            config={'publication_mode':'daily','sources':[{'name':'repost','type':'telegram','auto_publish':True}]}
            draft={**self.draft(),'what_happened':'Модель генерирует 500 токенов в секунду.'}
            with patch('ainews.pipeline.article_details',return_value=(self.source,None)), \
                 patch('ainews.pipeline.generate_draft',return_value=draft) as writer, \
                 patch('ainews.pipeline.polish_draft',side_effect=lambda config,title,source,draft:draft), \
                 patch('ainews.pipeline.revise_draft',return_value=draft),patch('ainews.pipeline.verify_draft') as verifier:
                prepare(config,store,limit=1)
            verifier.assert_not_called()
            row=store.db.execute('SELECT * FROM items').fetchone()
            self.assertEqual(row['state'],'needs_review');self.assertIn('numbers absent',row['error'])
            self.assertTrue(writer.call_args.args[0]['_signal_title_unverified'])

    def test_http_call_audit_distinguishes_actual_calls_from_editorial_stages(self):
        events=[]
        response=BytesIO(json.dumps({'response':'{"value":1}'}).encode())
        with patch('ainews.pipeline.urllib.request.urlopen',return_value=response):
            result=ollama_json({'model':'mock','ollama_url':'http://localhost','_llm_stage':'writer',
                               '_audit':lambda stage,data:events.append((stage,data))},'Prompt',{'type':'object'})
        self.assertEqual(result,{'value':1})
        self.assertEqual(len(events),1)
        self.assertEqual((events[0][0],events[0][1]['stage']),('llm_call','writer'))
