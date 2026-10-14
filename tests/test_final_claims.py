"""Source relations and final-card regressions; no credentials or live LLM."""
import json
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from ainews.daily import MSK, groups, linked_announcement, publish_daily, units
from ainews.digest import card
from ainews.feeds import Entry
from ainews.pipeline import align_evidence, draft_text
from ainews.quality import check_semantic_claims, derived_numbers
from ainews.store import Store


class ClaimRelations(unittest.TestCase):
    def test_difference_binds_two_scores(self):
        with self.assertRaisesRegex(ValueError, 'difference'):
            check_semantic_claims('Batch 4. Model A: 1651 pts; Model B: 1659 pts.',
                                 'Модель A набрала 1651 балл; это на 4 балла ниже B с 1659 баллами.')
        check_semantic_claims('Model A: 1651 pts; Model B: 1659 pts.',
                             'Модель A набрала 1651 балл; это на 8 баллов ниже B с 1659 баллами.')

    def test_explicit_subtraction_and_decimal_comma(self):
        with self.assertRaisesRegex(ValueError, 'subtraction'):
            check_semantic_claims('scores', '1659 − 1651 = 4')
        check_semantic_claims('scores', '6,5 - 2,5 = 4')

    def test_new_difference_requires_both_source_endpoints(self):
        text = 'Модель A набрала 1651 балл; это на 8 баллов ниже B с 1659 баллами.'
        self.assertEqual(derived_numbers('A: 1651 pts; B: 1659 pts.', text), {'8'})
        self.assertEqual(derived_numbers('A: 1651 pts.', text), set())
        self.assertEqual(derived_numbers('A: 1651 pts; B: 1659 pts.', text.replace('8 баллов', '4 балла')), set())

    def test_valid_derived_difference_passes_the_existing_numeric_gate(self):
        source = 'In this benchmark model A scores 1651 points and model B scores 1659 points.'
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'Сравнение моделей в тесте',
                 'what_happened': 'Модель A набрала 1651 балл; это на 8 баллов ниже B с 1659 баллами.',
                 'simple_explanation': '', 'why_it_matters': '', 'caveat': '', 'evidence': source}
        self.assertIn('8 баллов', draft_text(draft, source))
        draft['what_happened'] += ' Ещё один результат — 12345 баллов.'
        with self.assertRaisesRegex(ValueError, 'absent'):
            draft_text(draft, source)

    def test_prices_cannot_support_eightfold_saving(self):
        source = 'At $14.19 versus $3.33 per task.'
        with self.assertRaisesRegex(ValueError, 'Cost ratio'):
            check_semantic_claims(source, 'Почти восьмикратная экономия.')
        check_semantic_claims(source, 'Экономия 77%.')
        with self.assertRaisesRegex(ValueError, 'percentage'):
            check_semantic_claims(source, 'Экономия 90%.')

    def test_distinct_prices_do_not_trigger_ambiguous_calculation(self):
        check_semantic_claims('At $1, $2 and $8 per task.', 'Экономия в 8 раз.')
        check_semantic_claims('At $1 versus $8 per token.', 'Экономия 40%.')

    def test_effort_is_not_a_model(self):
        source = 'Nova 2.0 at max effort versus xhigh. Max generates 4.8 times as many output tokens.'
        for text in ('Модель xhigh дешевле.', 'Версия xhigh получила 63 балла.',
                     'Выбор между Nova 2.0 и xhigh зависит от бюджета.',
                     'Режим xhigh генерирует в 4.8 раза больше токенов.'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_semantic_claims(source, text)
        check_semantic_claims(source, 'Nova 2.0 в режиме xhigh дешевле режима max.')

    def test_foreign_tariff_sentence_is_rejected(self):
        source = 'GPU measurements use development builds.'
        with self.assertRaisesRegex(ValueError, 'Unrelated'):
            check_semantic_claims(source, 'Доступность по всему миру не означает доступ для всех тарифов.')
        check_semantic_claims('Available to Pro subscribers.', 'Доступно подписчикам Pro.')

    def test_advertised_context_is_not_a_verified_measurement(self):
        source = 'Up to 1M context.'
        with self.assertRaisesRegex(ValueError, 'attribution'):
            check_semantic_claims(source, 'Контекст до 1 млн токенов.')
        with self.assertRaisesRegex(ValueError, 'verified'):
            check_semantic_claims(source, 'По данным разработчиков, подтверждённый контекст до 1 млн токенов.')
        check_semantic_claims(source, 'Разработчики заявляют контекст до 1 млн токенов.')
        check_semantic_claims(source, 'Заявленный максимум — не проверенная длина контекста.')

    def test_source_possessive_spacing_restores_exact_original_evidence(self):
        source = 'In the test @Acme ’s Nova model scored 68 points at max effort.'
        draft = {'evidence': "In the test @Acme's Nova model scored 68 points at max effort."}
        self.assertEqual(align_evidence(draft, source)['evidence'], source)
        bad = {'evidence': "In the test @Acme's Nova model scored 69 points at max effort."}
        self.assertEqual(align_evidence(bad, source), bad)

    def test_verified_context_does_not_inherit_advertised_maximum(self):
        source = 'Up to 1M context. Tested context of 128K tokens.'
        with self.assertRaisesRegex(ValueError, 'tested length'):
            check_semantic_claims(source, 'По данным команды, подтверждённый контекст 1 млн токенов.')
        check_semantic_claims(source, 'Команда заявляет до 1 млн токенов. Подтверждённый контекст 128 тыс токенов.')

    def test_opinion_requires_attribution_and_a_scoped_headline(self):
        source = 'I think developers control their software.'
        with self.assertRaisesRegex(ValueError, 'attribution'):
            check_semantic_claims(source, 'Разработчики контролируют весь код.')
        with self.assertRaisesRegex(ValueError, 'prediction'):
            check_semantic_claims(source, '- ИИ не заменит код\nАвтор считает, что программисты контролируют код.')
        check_semantic_claims(source, '- Автор о контроле над кодом\nАвтор считает, что программисты контролируют код.')
        check_semantic_claims(source, '- Мнение: ИИ не заменит код\nАвтор считает, что программисты контролируют код.')

    def test_disclosure_does_not_prove_a_fix(self):
        source = 'Thanks for identifying vulnerabilities and responsibly disclosing them.'
        with self.assertRaisesRegex(ValueError, 'disclosure'):
            check_semantic_claims(source, 'Команда устранила уязвимости.')
        check_semantic_claims(source, 'Команда сообщила о выявленных уязвимостях.')
        check_semantic_claims(source + ' They were patched.', 'Команда устранила уязвимости.')

    def test_day_zero_support_is_not_a_new_technology(self):
        with self.assertRaisesRegex(ValueError, 'release timing'):
            check_semantic_claims('Day-0 support is here.', 'Технология Day-0 ускоряет запуск.')
        check_semantic_claims('Day-0 support is here.', 'Поддержка доступна в день выхода.')

    def test_moe_does_not_prove_unmeasured_speed_and_cost(self):
        with self.assertRaisesRegex(ValueError, 'Sparse'):
            check_semantic_claims('25B active per token.', 'Модель быстрая и дешёвая.')
        check_semantic_claims('We measured fast and cheap MoE inference.', 'По данным разработчиков, модель быстрая и дешёвая.')

    def test_non_leading_rank_cannot_become_leader(self):
        source = 'Model B at #12 with 1659 pts.'
        with self.assertRaisesRegex(ValueError, 'non-leading'):
            check_semantic_claims(source, 'Модель B лидирует с 1659 баллами.')
        check_semantic_claims('Model B at #1 with 1659 pts.', 'Модель B лидирует с 1659 баллами.')

    def test_true_delta_cannot_change_comparison_model(self):
        source = 'It is 11 pts above Vega 4.7 and within 4 pts of Orion 3.0.'
        with self.assertRaisesRegex(ValueError, 'different comparison model'):
            check_semantic_claims(source, 'Модель опередила Orion 3.0 на 11 пунктов.')
        check_semantic_claims(source, 'Модель опередила Vega 4.7 на 11 пунктов.')
        check_semantic_claims(source + ' Another test is 11 pts above Orion 3.0.',
                             'Модель опередила Orion 3.0 на 11 пунктов.')

    def test_throughput_binds_configuration_and_per_user_scope(self):
        source = '685 output tokens/s per user. Running on 4× NVIDIA GB300 with NVFP4.'
        complete = 'По данным команды, 685 токенов в секунду на одного пользователя на четырёх NVIDIA GB300 с NVFP4.'
        check_semantic_claims(source, complete)
        for text in ('685 токенов в секунду на GPU GB300.',
                     complete.replace('четырёх', 'двух'), complete.replace('NVFP4', 'FP8'),
                     complete.replace('на одного пользователя ', '')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_semantic_claims(source, text)

    def test_compaction_keeps_benchmark_sentence(self):
        fields = {'headline': 'Nova: 685 токенов в секунду', 'what':
                  'Команда опубликовала результаты. На четырёх GPU GB300 с NVFP4 — 685 токенов в секунду на одного пользователя.',
                  'simple': 'Это высокая скорость.', 'why': '', 'caveat': ''}
        result = card(fields, 250, detail_first=True)
        self.assertIn('четырёх GPU', result)
        self.assertIn('на одного пользователя', result)
        self.assertEqual(card(fields, 80, detail_first=True), '')

    def test_per_user_rate_does_not_imply_parallel_requests(self):
        source = '500 tokens/s per user.'
        with self.assertRaisesRegex(ValueError, 'parallel workload'):
            check_semantic_claims(source, '500 токенов/с на пользователя при одновременной работе над задачами.')
        check_semantic_claims(source + ' At concurrency 2.',
                             '500 токенов/с на пользователя при одновременной работе с 2 запросами.')


class FinalGateIsolation(unittest.TestCase):
    def test_shortening_failure_holds_only_the_affected_card(self):
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
            now = datetime(2026, 10, 14, 21, tzinfo=MSK)
            config = {'sources': [{'name': 'official', 'auto_publish': True}], 'auto_publish': True, 'channel_id': -1}
            sources = {'good': 'Поддержка файлов добавлена.',
                       'measured': '500 tokens/s per user on 4× NVIDIA GB300 with NVFP4.'}
            drafts = {'good': 'Поддержка файлов добавлена.',
                      'measured': '500 токенов/с на пользователя на четырёх NVIDIA GB300 с NVFP4.'}
            for url in sources:
                store.add_feed('official', [Entry('official', url, url, (now-timedelta(hours=1)).isoformat(), sources[url])], include_existing=True)
                store.set_state(url, 'ready', article=sources[url], draft='🧠 '+url+'\n\nЧто произошло: '+drafts[url])
            def broken_compaction(cards, limit):
                return [(card(fields) if group[0]['url']=='good' else '- measured\n\n500 токенов/с.', group)
                        for fields, group, links in cards]
            sender = Mock(return_value=12)
            with patch('ainews.daily.allocate_cards', side_effect=broken_compaction):
                publish_daily(config, store, Path(temp), now=now, token_reader=lambda: 'mock', sender=sender)
            sender.assert_called_once()
            self.assertNotIn('500', sender.call_args.args[2])
            reason = store.db.execute("SELECT error FROM items WHERE url='measured'").fetchone()[0]
            self.assertIn('after shortening', reason)

    def test_bad_story_held_without_blocking_good_story_or_retrying_send(self):
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
            root = Path(temp)
            config = {'sources': [{'name': 'official', 'auto_publish': True}],
                      'auto_publish': True, 'channel_id': -1, 'max_digest_chars': 3900}
            now = datetime(2026, 10, 14, 21, tzinfo=MSK)
            for url, text in [('good', 'Nova 2.0 получила поддержку файлов.'),
                              ('bad', 'Доступность по всему миру не означает доступ для всех тарифов.')]:
                store.add_feed('official', [Entry('official', url, url, (now - timedelta(hours=1)).isoformat(), 'GPU update.')], include_existing=True)
                store.set_state(url, 'ready', article='GPU update.',
                                draft='🧠 '+url+'\n\nЧто произошло: '+text)
            sender = Mock(return_value=12)
            publish_daily(config, store, root, now=now, token_reader=lambda: 'mock', sender=sender)
            publish_daily(config, store, root, now=now, token_reader=lambda: 'mock', sender=sender)
            sender.assert_called_once()
            self.assertNotIn('тарифов', sender.call_args.args[2])
            self.assertLessEqual(units(sender.call_args.args[2]), 3900)
            self.assertEqual(store.db.execute("SELECT state FROM items WHERE url='bad'").fetchone()[0], 'needs_review')
            audit = store.db.execute("SELECT details FROM editorial_audit WHERE url='bad' AND stage='final_quality_gate'").fetchone()
            self.assertIn('Unrelated', json.loads(audit[0])['reason'])

    def test_official_article_and_its_notice_are_one_story(self):
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp)/'news.db')) as store:
            config = {'sources': [{'name': 'official', 'auto_publish': True}]}
            now = datetime(2026, 10, 14, 21, tzinfo=MSK)
            for url, title, summary in [('https://vendor.example/news/office', 'Acme opens an office', 'Office opened.'),
                                        ('https://x.com/acme/status/123', 'We opened an office', 'Read https://vendor.example/news/office')]:
                store.add_feed('official', [Entry('official', title, url, (now - timedelta(hours=1)).isoformat(), summary)], include_existing=True)
                store.set_state(url, 'ready', article=summary,
                                draft='🧠 '+title+'\n\nЧто произошло: Открыт офис в регионе.')
            self.assertEqual(len(groups(config, store, now)[0]), 1)

    def test_multiple_reference_links_are_not_an_announcement_identity(self):
        article = {'url': 'https://vendor.example/news/office', 'summary': ''}
        notice = {'url': 'https://x.com/acme/status/123', 'summary':
                  'https://vendor.example/news/office https://vendor.example/news/other'}
        self.assertFalse(linked_announcement(article, notice))
