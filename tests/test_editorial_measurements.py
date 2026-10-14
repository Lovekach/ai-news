import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from ainews.daily import MSK, groups, merge_stories, priority
from ainews.digest import card
from ainews.feeds import Entry
from ainews.pipeline import draft_text, verify_draft, revise_draft, normalize_literal_translations, ollama_json
from ainews.quality import check_semantic_claims, event_signature, measurement_issues
from ainews.store import Store


class MeasurementTests(unittest.TestCase):
    def test_explicit_developer_measurement_is_attribution(self):
        source = 'We evaluated Nova 2.0 in our benchmarks.'
        check_semantic_claims(source, 'Разработчики оценили Nova 2.0 в тесте: модель быстрее конкурента.')
        check_semantic_claims(source, 'Nova 2.0 быстрее конкурента. Результаты измерены разработчиками.')
        check_semantic_claims(source, 'Новый словарь для улучшения работы с нелатиницей.')
        with self.assertRaisesRegex(ValueError, 'attribution'):
            check_semantic_claims(source, 'Nova 2.0 быстрее конкурента.')

    def test_expert_count_is_scoped_to_each_block(self):
        source = '64 experts per MoE block with top-4 routing.'
        with self.assertRaisesRegex(ValueError, 'entire model'):
            check_semantic_claims(source, 'Внутри модели 64 эксперта.')
        check_semantic_claims(source, 'В каждом MoE-блоке 64 эксперта.')

    def test_aggregate_score_is_not_assigned_to_a_subtest(self):
        source = 'Vera 1.13 scores 58 on the Acme Decision Index. It covers Acme-Knowledge-Decision.'
        with self.assertRaisesRegex(ValueError, 'subtest'):
            check_semantic_claims(source, 'В тесте Acme-Knowledge-Decision Vera 1.13 набрала 58 баллов.')
        check_semantic_claims(source, 'Vera 1.13 набрала 58 баллов в Acme Decision Index.')

    def test_availability_is_not_a_new_release(self):
        with self.assertRaisesRegex(ValueError, 'model release'):
            check_semantic_claims('Nova 2.0 is now globally available.', 'Компания выпустила модель Nova 2.0.')
        check_semantic_claims('Nova 2.0 is now globally available.', 'Nova 2.0 стала доступна по всему миру.')
        check_semantic_claims('Introducing our new model Nova 2.0, now available.', 'Компания выпустила модель Nova 2.0.')

    def test_multiple_errors_are_reported_in_one_revision(self):
        source = 'It is reasoning-only. The context window grows to 131K tokens.'
        issues = measurement_issues(source, 'Контекст — 131 тыс. символов. Работает только как агент.')
        self.assertEqual(len(issues), 2)

    def test_context_tokens_are_not_characters(self):
        source = 'The context window grows from 32K to 131K tokens.'
        with self.assertRaisesRegex(ValueError, 'characters'):
            check_semantic_claims(source, 'Контекст расширен с 32 тыс. до 131 тыс. символов.')
        check_semantic_claims(source, 'Контекст расширен до 131 тыс. токенов.')

    def test_vocabulary_units_do_not_get_mislabeled_as_context(self):
        source = 'The context window is 131K tokens. The vocabulary grows to 128K tokens.'
        issues = measurement_issues(source, 'Контекст — 131K токенов, словарь — 128K символов.')
        self.assertEqual(issues, ['Vocabulary measured in tokens was rewritten as characters'])
        check_semantic_claims(source, 'Контекст — 131K токенов, словарь — 128K токенов.')

    def test_unit_translation_repair_requires_the_source_unit(self):
        source = 'The context window is 131K tokens. The vocabulary is 128K tokens.'
        value = normalize_literal_translations('Контекст — 131K символов, словарь — 128K символов.', source)
        self.assertEqual(value, 'Контекст — 131K токенов, словарь — 128K токенов.')
        self.assertEqual(normalize_literal_translations('Контекст — 131 символов.', 'Context length is 131 characters.'),
                         'Контекст — 131 символов.')

    def test_throughput_translation_repair_is_specific_to_the_cited_rate(self):
        source = '500 output tokens per second at high concurrency on H100.'
        value = normalize_literal_translations('На H100 — 500 токенов/с при высокой нагрузке.', source)
        self.assertIn('суммарно при параллельных запросах', value)
        self.assertEqual(normalize_literal_translations('400 токенов/с при высокой нагрузке.', source),
                         '400 токенов/с при высокой нагрузке.')

    def test_index_translation_repair_keeps_score_and_source_metric(self):
        source = 'Vera 1.13 scores 58 on the Acme Decision Index. It covers Acme-Knowledge-Decision.'
        value = normalize_literal_translations('В тесте Acme-Knowledge-Decision Vera 1.13 набрала 58 баллов.', source)
        self.assertEqual(value, 'В индексе Acme Decision Index Vera 1.13 набрала 58 баллов.')
        self.assertIn('В тесте', normalize_literal_translations('В тесте Acme-Knowledge-Decision — 50 баллов.', source))

    def test_index_score_retains_metric_and_measured_reasoning_setting(self):
        source = 'Vega Light 5.5 (Low) scores 61 on the Decision Index.'
        value = normalize_literal_translations('Vega Light 5.5 показала результат по точности (61 балл).', source)
        self.assertEqual(value, 'Vega Light 5.5 (Low) показала результат в индексе Decision Index (61 балл).')
        self.assertEqual(normalize_literal_translations(value, source), value)

    def test_reasoning_model_headline_drops_agent_descriptor_for_exact_subject(self):
        source = 'Acme released Nova2.0. Nova2.0 is reasoning-only, with reasoning before each answer.'
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'Acme выпустила Nova2.0: агент с рассуждениями',
                 'what_happened': 'Модель рассуждает перед каждым ответом.', 'evidence': source}
        text = draft_text(draft, source)
        self.assertEqual(text.splitlines()[0], '🧠 Acme выпустила Nova2.0')
        other_source = 'Tool2.0 is an agent using Nova2.0. Nova2.0 is reasoning-only.'
        other = {**draft, 'headline': 'Acme выпустила Tool2.0: агент с рассуждениями', 'evidence': other_source}
        self.assertIn('агент', draft_text(other, other_source).splitlines()[0])

    def test_pronoun_reasoning_mode_needs_single_main_subject(self):
        source = 'Acme released Nova2.0. Unlike its predecessor, it is a reasoning-only model.'
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'Acme выпустила Nova2.0: агент с рассуждениями',
                 'what_happened': 'Модель рассуждает перед ответом.', 'evidence': source}
        self.assertNotIn('агент', draft_text(draft, source).splitlines()[0])

    def test_primary_title_anchors_reasoning_model_before_a_competitor_in_article(self):
        source = 'Nova2.0 competes with Vera3.6. Unlike its predecessor, it is a reasoning-only model.'
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'Acme выпустила Nova2.0: агент с рассуждениями',
                 'what_happened': 'Модель рассуждает перед ответом.', 'evidence': source}
        self.assertNotIn('агент', draft_text(draft, source, source_title='Nova2.0 new model').splitlines()[0])

    def test_verifier_receives_separate_original_documents_for_a_merge(self):
        import json
        documents = [{'title': 'App', 'published': '2026-10-13', 'text': 'App subscribers only.'},
                     {'title': 'API', 'published': '2026-10-13', 'text': 'API paid tier.'}]
        with patch('ainews.pipeline.ollama_json', return_value={'supported': True, 'unsupported_claims': []}) as model:
            verify_draft({'_daily_merge': True, '_source_documents': documents}, 'Rollout',
                         'App subscribers only. API paid tier.', 'Открыт доступ.')
        self.assertEqual(json.loads(model.call_args.args[1])['source'], documents)

    def test_many_source_documents_cannot_expand_existing_evidence_budget(self):
        import json
        documents = [{'title': 'Announcement', 'text': 'Original source. '*600}]*5
        with patch('ainews.pipeline.ollama_json', return_value={'supported': True, 'unsupported_claims': []}) as model:
            verify_draft({'_daily_merge': True, '_source_documents': documents}, 'Rollout',
                         'Original source. '*1200, 'Подтверждённое сообщение.')
        source = json.loads(model.call_args.args[1])['source']
        self.assertIsInstance(source, str)
        self.assertLessEqual(len(source), 7000)

    def test_editorial_availability_instruction_is_not_published_as_a_fact(self):
        source = 'Nova2.0 is now globally available on the paid API tier.'
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'Nova2.0 доступна глобально',
                 'what_happened': 'Nova2.0 стала доступна глобально. Доступность не означает выпуск как новый продукт или все тарифы.',
                 'caveat': 'Доступ открыт на платном тарифе API.', 'evidence': source}
        text = draft_text(draft, source)
        self.assertNotIn('не означает', text)
        self.assertIn('платном тарифе', text)

    def test_reasoning_definition_is_not_repeated_across_fields(self):
        fields = {'headline': 'Nova2.0', 'what': 'Модель работает в режиме reasoning-only и рассуждает перед ответом.',
                  'simple': 'Режим reasoning-only означает, что модель рассуждает перед ответом. '
                  'В каждом блоке — 64 эксперта.', 'why': '', 'caveat': ''}
        text = card(fields)
        self.assertEqual(text.count('reasoning-only'), 1)
        self.assertIn('64 эксперта', text)

    def test_chosen_answer_probability_is_not_error_probability(self):
        source = 'Across probability levels for chosen answers, accuracy falls below that probability.'
        value = normalize_literal_translations('Ответ с вероятностью ошибки.', source)
        self.assertEqual(value, 'Ответ с вероятностью выбранного ответа.')
        self.assertEqual(normalize_literal_translations('Вероятность ошибки.', 'We report error probability.'),
                         'Вероятность ошибки.')

    def test_reasoning_mode_does_not_restrict_tasks_to_agents(self):
        with self.assertRaisesRegex(ValueError, 'agent-only'):
            check_semantic_claims('It is a reasoning-only model.', 'Она работает только как агент.')
        check_semantic_claims('It is a reasoning-only model.', 'Модель рассуждает перед ответом.')

    def test_aggregate_throughput_requires_parallel_condition(self):
        source = 'Reaching over 21K output tokens per second at high concurrency on a single B300.'
        with self.assertRaisesRegex(ValueError, 'concurrency'):
            check_semantic_claims(source, 'На B300 модель генерирует 21 тыс токенов в секунду.')
        check_semantic_claims(source, 'На B300 суммарная скорость — 21 тыс токенов в секунду при параллельных запросах.')

    def test_small_expert_count_is_not_hundreds(self):
        with self.assertRaisesRegex(ValueError, 'hundreds'):
            check_semantic_claims('64 experts per MoE block with top-4 routing.', 'В слое сотни экспертов.')
        check_semantic_claims('256 experts per MoE block.', 'В блоке сотни экспертов.')

    def test_active_parameters_do_not_change_expert_routing(self):
        source = '128 experts per MoE block with top-8 routing. 2B active parameters.'
        with self.assertRaisesRegex(ValueError, 'routing count'):
            check_semantic_claims(source, 'В модели активны только два эксперта.')
        check_semantic_claims(source, 'В модели активны восемь экспертов и 2 млрд параметров.')

    def test_open_weight_singular_is_not_source_code(self):
        with self.assertRaisesRegex(ValueError, 'source code'):
            check_semantic_claims('An open-weight model.', 'Модель доступна для установки из исходного кода.')
        check_semantic_claims('An open-weight model.', 'Опубликованы веса модели.')

    def test_latency_units(self):
        with self.assertRaisesRegex(ValueError, 'milliseconds'):
            check_semantic_claims('The latency is 50 ms.', 'Задержка — 50 секунд.')
        check_semantic_claims('The latency is 50 ms.', 'Задержка — 50 миллисекунд.')

    def test_active_parameters_are_not_token_counts(self):
        with self.assertRaisesRegex(ValueError, 'Parameter count'):
            check_semantic_claims('2B active parameters.', 'Использует 2 млрд активных токенов.')
        check_semantic_claims('2B active parameters.', 'Использует 2 млрд активных параметров.')

    def test_throughput_batch_size_is_preserved(self):
        source = 'Measured 500 tokens per second with batch size 32.'
        with self.assertRaisesRegex(ValueError, 'batch size'):
            check_semantic_claims(source, 'Скорость — 500 токенов в секунду.')
        check_semantic_claims(source, 'Скорость — 500 токенов в секунду при батче 32.')

    def test_hardware_specifications_are_substantive(self):
        source = 'The new GPU uses an air-cooled PCIe 5.0 card.'
        with self.assertRaisesRegex(ValueError, 'PCIe'):
            check_semantic_claims(source, 'Вышла новая GPU с воздушным охлаждением.')
        with self.assertRaisesRegex(ValueError, 'air cooling'):
            check_semantic_claims(source, 'Вышла новая GPU с PCIe 5.0.')
        check_semantic_claims(source, 'Вышла новая GPU с PCIe 5.0 и воздушным охлаждением.')

    def test_parallel_throughput_keeps_device_and_abbreviated_units(self):
        source = '21K output tokens per second at high concurrency on a single B300.'
        with self.assertRaisesRegex(ValueError, 'concurrency'):
            check_semantic_claims(source, 'Скорость на B300 — 21 тыс. токенов в секунду.')
        with self.assertRaisesRegex(ValueError, 'hardware'):
            check_semantic_claims(source, 'Суммарная скорость — 21 тыс. токенов в секунду.')
        check_semantic_claims(source, 'Суммарная скорость на B300 — 21 тыс. токенов в секунду.')

    def test_vendor_benchmark_claim_needs_attribution(self):
        source = 'We evaluated the models on 16 benchmarks. Nova scores 48.'
        with self.assertRaisesRegex(ValueError, 'attribution'):
            check_semantic_claims(source, 'Nova показывает лучшие результаты: 48 баллов.')
        check_semantic_claims(source, 'По данным компании, Nova показывает лучшие результаты: 48 баллов.')

    def test_named_evaluator_index_is_attribution(self):
        source = 'Acme Research Decision Index: Vera scores 58, ahead of competitors on the benchmark.'
        check_semantic_claims(source, 'В индексе Acme Research модель Vera получила 58 баллов и обошла конкурентов в тесте.')
        with self.assertRaisesRegex(ValueError, 'attribution'):
            check_semantic_claims('We evaluated all models.', 'Vera — лучшая модель в тесте.')

    def test_index_winner_is_not_speed_or_cost_winner(self):
        source = ('Vera 2.0 leads the Decision Index. Budget v1.1 27B has the lowest Cost per Task. '
                  'Swift-1 Decision has the fastest Time per Task.')
        with self.assertRaisesRegex(ValueError, 'record'):
            check_semantic_claims(source, 'Vera 2.0 лидирует по скорости и цене\nРезультат индекса — 58.')
        check_semantic_claims(source, 'Vera 2.0 лидирует по суммарному индексу\nЭто результат теста.')

    def test_verifier_cannot_erase_a_rejection_with_later_approvals(self):
        replies = [{'supported': False, 'unsupported_claims': ['Wrong unit']},
                   {'supported': True, 'unsupported_claims': []}]
        with patch('ainews.pipeline.ollama_json', side_effect=replies) as model:
            with self.assertRaisesRegex(ValueError, 'Wrong unit'):
                verify_draft({}, 'Model', 'Context is large.', 'Контекст большой.')
        model.assert_called_once()
        self.assertIn('_chat_system', model.call_args.args[0])
        self.assertEqual(model.call_args.kwargs['max_predict'], 500)

    def test_native_chat_protocol_keeps_instructions_and_evidence_separate(self):
        import json
        from io import BytesIO
        response = BytesIO(json.dumps({'message': {'content': '{"supported":true,"unsupported_claims":[]}'}}).encode())
        with patch('ainews.pipeline.urllib.request.urlopen', return_value=response) as open_url:
            result = ollama_json({'model': 'local', 'ollama_url': 'http://localhost', '_chat_system': 'Verify facts.'},
                                 'Untrusted evidence.', {'type': 'object'}, max_predict=500)
        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(request.full_url.endswith('/api/chat'))
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': 'Verify facts.'})
        self.assertEqual(payload['messages'][1]['content'], 'Untrusted evidence.')
        self.assertFalse(payload['think'])
        self.assertTrue(result['supported'])

    def test_revision_preserves_evidence_and_receives_specific_objection(self):
        import json
        old = {'headline': 'Nova 2.0', 'what_happened': 'Контекст — 131K символов.'}
        with patch('ainews.pipeline.ollama_json', return_value={}) as model:
            revise_draft({}, 'Nova 2.0', 'The context window is 131K tokens.', old, 'Use tokens, not characters.')
        data = json.loads(model.call_args.args[1])
        self.assertEqual(data['previous'], old)
        self.assertEqual(data['source'], 'The context window is 131K tokens.')
        self.assertEqual(data['problem'], 'Use tokens, not characters.')
        self.assertIn('_chat_system', model.call_args.args[0])

    def test_context_provider_and_event_type_separation(self):
        availability = event_signature('Nova 2.0 is now globally available', '')
        self.assertEqual(availability, event_signature('Nova 2.0 comes to the app', ''))
        self.assertNotEqual(availability, event_signature('Nova 2.0: new model release', ''))
        self.assertNotEqual(availability, event_signature('Nova 2.0 new model available via API', ''))
        self.assertNotEqual(availability, event_signature('Nova 2.1 is now available', ''))
        self.assertNotEqual(availability, event_signature('Nova 2.0 benchmark', ''))
        self.assertNotEqual(availability, event_signature('Nova 2.0 API update', ''))
        self.assertNotEqual(event_signature('Nova 2.0 available on Bedrock', ''), availability)

    def test_subject_is_not_a_competitor_in_body(self):
        signature = event_signature('LFM2.5-24B-A2B: release', 'Ahead of Qwen3.6-35B-A3B.')
        self.assertIn('lfm2.5', signature[1])
        self.assertEqual(signature[0], 'liquidai')
        self.assertIsNone(event_signature('A new evaluation service', 'Uses Claude Haiku 5.5.'))

    def test_unknown_main_product_precedes_known_competitor_in_headline(self):
        signature = event_signature('Nova 2.0 compared with Qwen3.6-35B-A3B', '')
        self.assertIn('nova', signature[1])
        self.assertNotIn('qwen', signature[1])

    def test_named_index_is_the_subject_not_a_compared_model(self):
        signature = event_signature('Introducing Acme Decision Index, benchmarking Claude Haiku 5.5',
                                    'Acme Decision Index v1.0 compares models.')
        self.assertEqual(signature[1], 'acme decision index 1.0')
        self.assertNotEqual(signature, event_signature('Acme Decision Index v2.0 benchmark', ''))

    def test_shortening_preserves_measurement_conditions(self):
        fields = {'headline': 'Nova 2.0', 'what': 'Вышла новая модель. '
                  'На GPU суммарная скорость при параллельных запросах — 21 тыс токенов в секунду.',
                  'simple': 'Новый способ работать с текстом.', 'why': '', 'caveat': ''}
        short = card(fields, max_chars=180, detail_first=True)
        self.assertIn('параллельных', short)
        self.assertEqual(card(fields, max_chars=60, detail_first=True), '')

    def test_shortening_preserves_access_conditions_outside_main_field(self):
        fields = {'headline': 'Nova2.0 доступна', 'what': 'Открыт доступ к модели. '
                  'Появились новые возможности для повседневных задач и сложных проектов.',
                  'simple': 'API доступен на платном тарифе.',
                  'why': 'Приложение открыто подписчикам Pro и Ultra.', 'caveat': ''}
        text = card(fields, max_chars=170, detail_first=True)
        self.assertIn('платном тарифе', text)
        self.assertIn('подписчикам Pro и Ultra', text)
        self.assertNotIn('повседневных', text)

    def test_shortening_prefers_hardware_spec_over_filler(self):
        fields = {'headline': 'GPU', 'what': 'Представлена новая видеокарта. '
                  'Пользователи получают больше возможностей для своих задач. '
                  'Карта использует PCIe 5.0 и воздушное охлаждение.', 'why': '', 'simple': '', 'caveat': ''}
        text = card(fields, max_chars=130, detail_first=True)
        self.assertIn('PCIe 5.0', text)
        self.assertNotIn('больше возможностей', text)


class RolloutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'news.db')
        self.now = datetime(2026, 10, 13, 21, tzinfo=MSK)
        self.config = {'sources': [{'name': 'official', 'auto_publish': True}], 'max_digest_chars': 3900}

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add(self, url, title, what, source):
        self.store.add_feed('official', [Entry('official', title, url,
                            (self.now-timedelta(hours=1)).isoformat(), source)], include_existing=True)
        self.store.set_state(url, 'ready', article=source,
                             draft=f'🧠 {title}\n\nЧто произошло: {what}')

    def test_all_rollout_channels_group_into_one_event(self):
        self.add('app', 'Nova 2.0 comes to the app', 'Модель добавлена в приложение.', 'App supports Nova 2.0.')
        self.add('api', 'Nova 2.0 now available for developers', 'Доступ открыт через API.', 'API supports Nova 2.0.')
        self.add('global', 'Nova 2.0 is now globally available', 'Доступ расширен по всему миру.', 'Global availability.')
        grouped, _ = groups(self.config, self.store, self.now)
        self.assertEqual([len(group) for group in grouped], [3])

    def test_model_release_ranks_above_advisory_service(self):
        release = {'title': 'Nova 2.0 new model', 'draft': '', 'summary': 'Model released.'}
        service = {'title': 'New advisory service', 'draft': 'AI models agents research API cost developer', 'summary': ''}
        self.assertGreater(priority(release), priority(service))

    def test_merge_verifies_original_evidence_not_approved_paraphrases(self):
        self.add('one', 'Nova 2.0 available in app', 'Добавлена в приложение.', 'Original: app subscribers only.')
        self.add('two', 'Nova 2.0 available via API', 'Открыт API.', 'Original: paid API tier.')
        draft = {'relevant': True, 'confidence': 'high', 'evidence': 'Original: app subscribers only.',
                 'headline': 'Nova 2.0 доступна в приложении и API',
                 'what_happened': 'Доступ открыт подписчикам приложения и платного API.',
                 'simple_explanation': '', 'why_it_matters': '', 'caveat': ''}
        with patch('ainews.daily.ollama_json', return_value=draft), \
             patch('ainews.daily.draft_text', return_value='🧠 Nova 2.0 доступна\n\nЧто произошло: Открыт платный API.'), \
             patch('ainews.daily.verify_draft') as verify:
            merge_stories(self.config, self.store, self.now)
        evidence = verify.call_args.args[2]
        self.assertIn('Original: paid API tier.', evidence)
        self.assertIn('Original: app subscribers only.', evidence)

    def test_failed_merge_is_revised_and_verified_before_caching(self):
        self.add('one', 'Nova 2.0 new model release', 'Добавлена в приложение.', 'App subscribers only.')
        self.add('two', 'Nova 2.0 new model release', 'Открыт API.', 'Paid API tier.')
        bad = {'relevant': True, 'confidence': 'high', 'headline': 'Nova 2.0',
               'what_happened': 'Доступ открыт всем.', 'evidence': 'App subscribers only.'}
        fixed = {**bad, 'what_happened': 'Доступ открыт подписчикам приложения и платного API.'}
        with patch('ainews.daily.ollama_json', return_value=bad), \
             patch('ainews.daily.align_evidence', side_effect=lambda draft, source: draft), \
             patch('ainews.daily.draft_text', side_effect=['bad text', 'fixed text']), \
             patch('ainews.daily.verify_draft', side_effect=[ValueError('Access limited'), None]) as verify, \
             patch('ainews.daily.revise_draft', return_value=fixed) as revise:
            result = merge_stories(self.config, self.store, self.now)
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(revise.call_count, 1)
        self.assertEqual(result, ['Merged verified story: 2 sources'])
        self.assertEqual(self.store.db.execute('SELECT draft FROM daily_story_drafts').fetchone()[0], 'fixed text')

    def test_rollout_copy_preserves_complementary_conditions_without_new_prose(self):
        self.add('one', 'Nova 2.0 available in app', 'Приложение доступно подписчикам Pro.', 'Nova 2.0 app available to Pro subscribers.')
        self.add('two', 'Nova 2.0 available via API', 'API открыт на платном тарифе.', 'Nova 2.0 API available on the paid tier.')
        with patch('ainews.daily.verify_draft') as verify, patch('ainews.daily.ollama_json') as writer:
            result = merge_stories(self.config, self.store, self.now)
        self.assertEqual(result, ['Merged verified story: 2 sources'])
        writer.assert_not_called()
        text = verify.call_args.args[3]
        self.assertIn('подписчикам Pro', text)
        self.assertIn('платном тарифе', text)
        self.assertIn('Nova 2.0 app available to Pro subscribers.', verify.call_args.args[2])

    def test_rollout_copy_cannot_skip_contradiction_check(self):
        self.add('one', 'Nova 2.0 available in app', 'Доступ открыт.', 'Access to Nova 2.0 has been granted.')
        self.add('two', 'Nova 2.0 availability update', 'Доступ отменён.', 'Access to Nova 2.0 is now withdrawn.')
        # Explicit updates remain a different event. For a same-type withdrawal,
        # no combined text may be cached when the original-evidence check fails.
        self.store.db.execute("UPDATE items SET title='Nova 2.0 available in app' WHERE url='two'")
        self.store.db.commit()
        for error in (ValueError('Access withdrawn'), TimeoutError('Verifier unavailable')):
            with self.subTest(error=type(error).__name__), \
                 patch('ainews.daily.verify_draft', side_effect=error) as verify, \
                 patch('ainews.daily.ollama_json', side_effect=ValueError('Generation failed')):
                merge_stories(self.config, self.store, self.now)
            verify.assert_called_once()
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM daily_story_drafts').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
