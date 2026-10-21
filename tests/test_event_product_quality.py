"""Synthetic regressions; real editorial snapshots remain private."""
import unittest
from unittest.mock import patch

from ainews.daily import final_public_issues
from ainews.digest import NEWS_SEPARATOR
from ainews.events import identity, same_event
from ainews.measurements import measurement_issues
from ainews.pipeline import polish_draft
from ainews.quality import check_semantic_claims, headline_issues


def row(title='Nova 2.0 доступна в ServiceOne', body=None, *, url='https://x.com/vendor/status/100',
        date='2026-10-20T10:00:00+00:00'):
    body = body or 'Nova 2.0 is available on ServiceOne. https://x.com/service/status/90'
    return dict(title=title, article=body, summary=body, url=url, published=date,
                draft='🧠 ' + title + '\n\nЧто произошло: Модель доступна для работы с документами.')


class EventProductQualityTests(unittest.TestCase):
    def test_named_integrations_are_distinct(self):
        first = identity(row())
        second = identity(row('Nova 2.0 доступна в ServiceTwo', 'Nova 2.0 is available on ServiceTwo.'))
        self.assertFalse(same_event(first, second))
        self.assertEqual(first.platform, 'serviceone')

    def test_linked_next_day_echo_is_same_integration(self):
        first = identity(row())
        echo = identity(row('Nova 2.0 теперь доступна в ServiceOne', date='2026-10-21T09:00:00+00:00'))
        self.assertTrue(same_event(first, echo))

    def test_unlinked_different_days_not_automatically_merged(self):
        self.assertFalse(same_event(identity(row(body='Nova 2.0 on ServiceOne.')),
                                    identity(row(body='Nova 2.0 on ServiceOne.', url='https://x.com/vendor/status/101',
                                                 date='2026-10-21T10:00:00+00:00'))))

    def test_different_explicit_event_days_override_same_publication_day(self):
        self.assertFalse(same_event(identity(row(), event_date='2026-10-18'),
                                    identity(row(), event_date='2026-10-19')))

    def test_different_version_not_merged(self):
        self.assertFalse(same_event(identity(row()), identity(row('Nova 2.1 доступна в ServiceOne',
                                                   'Nova 2.1 available on ServiceOne.'))))

    def test_mirror_hostname_is_not_a_repository(self):
        event = identity(row(body='Nova 2.0 available on ServiceOne. https://mirror.example/ServiceOne'))
        self.assertNotIn('repo', event.product)

    def test_unversioned_repository_echo_merges(self):
        source = 'Introducing FastEngine: GitHub vendor/FastEngine. https://x.com/vendor/status/90'
        a = identity(row('FastEngine открыт для разработчиков', source))
        b = identity(row('Команда открыла FastEngine', source, url='https://x.com/echo/status/101'))
        self.assertTrue(same_event(a, b))
        self.assertEqual(a.company, 'vendor')

    def test_model_release_and_integration_remain_distinct(self):
        release = identity(row('Nova 2.0 новая модель', 'Nova 2.0 new model release.'))
        self.assertFalse(same_event(release, identity(row())))

    def test_repository_url_and_preview_have_the_same_subject(self):
        a = identity(row('FastEngine открыт для разработчиков', 'GitHub vendor/FastEngine.'))
        b = identity(row('FastEngine открыт для разработчиков', 'See https://github.com/vendor/FastEngine'))
        self.assertEqual(a.product, b.product)

    def test_repository_release_and_benchmark_are_distinct(self):
        a = identity(row('FastEngine открыт для разработчиков', 'GitHub vendor/FastEngine.'))
        b = identity(row('FastEngine benchmark в Task Arena', 'GitHub vendor/FastEngine benchmark on Task Arena.'))
        self.assertFalse(same_event(a, b))

    def test_update_and_benchmark_are_distinct(self):
        a = identity(row('Nova 2.0 update', 'Nova 2.0 updated.'))
        b = identity(row('Nova 2.0 benchmark', 'Nova 2.0 scores in benchmark.'))
        self.assertFalse(same_event(a, b))

    def test_same_model_different_benchmark_is_not_one_event(self):
        a = identity(row('Nova 2.0 заняла первое место в Task Arena', 'Nova 2.0 ranks first on Task Arena.'))
        b = identity(row('Nova 2.0 заняла первое место в Code Arena', 'Nova 2.0 ranks first on Code Arena.'))
        self.assertFalse(same_event(a, b))

    def test_previous_version_cannot_be_imported_from_another_benchmark(self):
        source = 'Task Arena: +6.2% net improvement. Code Arena: +40 points vs previous version.'
        self.assertTrue(measurement_issues(source, 'Эффективность выросла на 6,2% относительно предыдущей версии.'))
        self.assertFalse(measurement_issues(source, 'В Task Arena показатель net improvement составил 6,2%.'))

    def test_genuine_previous_version_comparison_and_rounding(self):
        source = 'Accuracy improves 6.23% over the previous version.'
        self.assertFalse(measurement_issues(source, 'Точность выросла на 6,2% относительно предыдущей версии.'))

    def test_percentage_points_are_not_relative_percent(self):
        source = 'Accuracy improved by 5 percentage points.'
        self.assertTrue(measurement_issues(source, 'Точность выросла на 5%.'))
        self.assertFalse(measurement_issues(source, 'Точность выросла на 5 процентных пунктов.'))

    def test_noncommercial_open_weights_preserve_license(self):
        source = 'Open weights are released under a non-commercial license.'
        with self.assertRaises(ValueError):
            check_semantic_claims(source, 'Модель с открытыми весами можно использовать в приложениях.')
        check_semantic_claims(source, 'Модель с открытыми весами доступна для некоммерческого использования.')

    def test_style_schema_saturation_keeps_complete_writer_title(self):
        original = dict(relevant=True, confidence='high', headline='Nova 2.0 появилась в ServiceOne',
                        what_happened='Модель доступна.', simple_explanation='', why_it_matters='',
                        caveat='', evidence='Original evidence.')
        broken = {**original, 'headline': 'Nova 2.0 ' + 'д' * 91}
        self.assertEqual(len(broken['headline']), 100)
        with patch('ainews.pipeline.ollama_json', return_value=broken):
            result = polish_draft({}, 'Release', original['evidence'], original)
        self.assertEqual(result['headline'], original['headline'])
        self.assertTrue(headline_issues(broken['headline']))

    def test_final_gate_detects_duplicate_event_across_distinct_cards(self):
        a, b = row(), row('Nova 2.0 теперь доступна в ServiceOne')
        cards = [(a['draft'], [a]), (b['draft'], [b])]
        findings = final_public_issues(NEWS_SEPARATOR.join(t for t, _ in cards), cards, 3900)
        self.assertTrue(any('repeat the same' in issue for issue in findings))

    def test_final_gate_binds_exact_payload_and_checks_links_and_tail(self):
        a = row()
        cards = [(a['draft'], [a])]
        for bad in (a['draft'] + ' https://example.org/path', a['draft'] + ' ~', a['draft'] + ' Different.'):
            self.assertTrue(final_public_issues(bad, cards, 3900))
        self.assertFalse(final_public_issues(a['draft'], cards, 3900))


if __name__ == '__main__':
    unittest.main()
