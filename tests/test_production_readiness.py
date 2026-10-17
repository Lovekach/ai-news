import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

import test_daily
from ainews.daily import allocate_cards, compose_daily, fitted_card, units
from ainews.digest import card
from ainews.pipeline import original_is_other_moscow_day, polish_draft


class ProductionReadiness(unittest.TestCase):
    setUp = test_daily.DailyTests.setUp
    tearDown = test_daily.DailyTests.tearDown
    add = test_daily.DailyTests.add
    def test_important_story_gets_more_space_and_uses_spare_capacity(self):
        details = ' '.join(f'Подробность {i}: модель выполняет задачу с проверяемым результатом.' for i in range(25))
        fields = {'headline': 'GPT-8 открытая модель и AI-агенты для разработчиков',
                  'what': 'Вышла модель для локального запуска. ' + details,
                  'simple': 'Можно запускать её на своём сервере.', 'why': '', 'caveat': 'Пока доступна только тестовая версия.'}
        less = {**fields, 'headline': 'Изменения компании', 'what': 'Компания провела мероприятие. ' + details}
        self.add('main', headline=fields['headline'])
        self.add('less', headline='Изменения компании', what='Компания провела мероприятие.')
        rows = {r['url']: r for r in self.store.ready()}
        chosen = allocate_cards([(fields, [rows['main']], []), (less, [rows['less']], [])], 1900)
        self.assertEqual(len(chosen), 2)
        self.assertGreater(units(chosen[0][0]), units(chosen[1][0]))
        self.assertLessEqual(units('\n\n\n\n'.join(c[0] for c in chosen)), 1900)
        self.assertGreater(units('\n\n\n\n'.join(c[0] for c in chosen)), 1750)

    def test_short_story_releases_its_space_to_long_story(self):
        self.add('main')
        self.add('brief', headline='GPT-9 обновление')
        rows = self.store.ready()
        long = {'headline': 'GPT-8 новая модель', 'what': 'Модель выпущена. ' + ' '.join(f'Деталь {i} помогает запускать задачи локально.' for i in range(30))}
        short = {'headline': 'GPT-9 обновление', 'what': 'Разработчики открыли веса модели.'}
        chosen = allocate_cards([(long, [rows[0]], []), (short, [rows[1]], [])], 1300)
        self.assertEqual(len(chosen), 2)
        self.assertGreater(units(chosen[0][0]), 1100)
        self.assertEqual(chosen[1][0], card(short))

    def test_concrete_specs_precede_generic_explanation_when_shortening(self):
        fields = {'headline': 'Новая модель', 'what': 'Вышла модель. Контекст составляет 128 тысяч токенов.',
                  'simple': 'Модель помогает быстрее решать разные задачи и работать с документами каждый день.'}
        text = fitted_card(fields, [], 115)
        self.assertIn('128 тысяч токенов', text)
        self.assertNotIn('быстрее решать разные', text)

    def test_official_source_links_remain_private(self):
        self.config['sources'][0]['hosts'] = ['official.example']
        self.add('https://official.example/launch')
        edition = compose_daily(self.config, self.store, self.now)
        self.assertIn('https://official.example/launch', edition.full)
        self.assertNotIn('https://', edition.telegram)
        self.assertLessEqual(units(edition.telegram), 3900)

    def test_tg_links_use_verified_primary_not_channel_link(self):
        self.config['sources'][0]['type'] = 'telegram'
        self.add('https://t.me/channel/42')
        self.store.db.execute("UPDATE items SET summary='Текст с подтверждением https://github.com/example/tool/releases/tag/v1.0' WHERE url=?", ('https://t.me/channel/42',))
        self.store.db.commit()
        edition = compose_daily(self.config, self.store, self.now)
        self.assertIn('https://github.com/example/tool/releases/tag/v1.0', edition.full)
        self.assertNotIn('https://', edition.telegram)

    def test_link_overflow_does_not_cut_sentences_or_caveats(self):
        fields = {'headline': 'GPT-8 🧠', 'what': 'Модель выпущена для работы с документами.',
                  'caveat': 'Доступна только в тестовой версии.'}
        link = 'https://official.example/' + 'x' * 180
        self.assertIn(fields['caveat'], fitted_card(fields, [link], 150))
        text = fitted_card(fields, [link], 400)
        self.assertIn(fields['what'], text)
        self.assertIn(fields['caveat'], text)
        self.assertNotIn(link, text)
        self.assertLessEqual(units(text), 400)

    def test_duplicate_primary_material_needs_only_one_link(self):
        self.config['sources'][0]['hosts'] = ['official.example']
        self.add('https://official.example/one')
        self.add('https://official.example/two')
        edition = compose_daily(self.config, self.store, self.now)
        self.assertEqual(edition.full.count('https://official.example/'), 1)
        self.assertNotIn('https://', edition.telegram)
        self.assertEqual(len(edition.urls), 2)

    def test_earlier_primary_article_is_not_republished_as_today(self):
        self.assertTrue(original_is_other_moscow_day('2026-10-11T12:00:00Z', '2026-10-12T04:00:00Z'))
        self.assertFalse(original_is_other_moscow_day('2026-10-11T22:00:00Z', '2026-10-12T04:00:00Z'))
        self.assertTrue(original_is_other_moscow_day('2026-10-11', '2026-10-12T04:00:00Z'))

    def test_mistral_updates_merge_without_collapsing_different_versions(self):
        self.add('early', headline='Mistral Large 4: новый релиз', what='Модель запускает агентов.')
        self.add('late', headline='Mistral Large 4: детали релиза', what='В модели уточнены параметры.', when=self.now)
        self.add('other', headline='Mistral Large 5: новый релиз', what='Обновлена другая версия.')
        # Exclusive cutoff is intentional: use a moment after the last update.
        from datetime import timedelta
        edition = compose_daily(self.config, self.store, self.now + timedelta(seconds=1))
        self.assertEqual(edition.stories, 2)
        self.assertNotIn('Модель запускает агентов.', edition.telegram)

    def test_final_editor_hard_timeout_precedes_publication(self):
        runtime = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/run_hidden.pyw'))
        timeout = runtime['task_timeout']
        self.assertEqual(timeout('editor', self.now.replace(hour=20, minute=50)), 550)
        self.assertEqual(timeout('editor', self.now.replace(hour=18, minute=0)), 1680)
        self.assertEqual(timeout('editor', self.now), 0)
        self.assertEqual(timeout('daily', self.now), 120)

    def test_observed_literal_translation_is_fixed_before_fact_check(self):
        draft = {'relevant': True, 'confidence': 'high', 'headline': 'Mistral Large 4',
                 'what_happened': 'Модель управляет общими агентами в рамках сложных задач.',
                 'simple_explanation': '', 'why_it_matters': '', 'caveat': '', 'evidence': 'original'}
        with patch('ainews.pipeline.ollama_json', return_value=draft):
            result = polish_draft({}, 'Mistral Large 4', 'general-purpose agents completing complex workflows', draft)
        self.assertEqual(result['what_happened'], 'Модель управляет универсальными агентами для сложных задач.')
        self.assertEqual(result['evidence'], 'original')
