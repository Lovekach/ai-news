import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from ainews.feeds import SourceRedirectHandler, download_feed
from ainews.pipeline import collect
from ainews.security import redact
from ainews.store import Store
from ainews.telegram import call, check_channel_access


class SecurityTests(unittest.TestCase):
    def test_redacts_bot_token_inside_telegram_request_path(self):
        token = ''.join(['123456789', ':', 'x' * 35])
        text = redact('https://api.telegram.org/bot' + token + '/getMe')
        self.assertNotIn(token, text)
        self.assertIn('/getMe', text)

    def test_redacts_url_credentials_query_and_authorization(self):
        message = 'https://user:example-password@example.com/feed?api_key=example-key&limit=2 Bearer example-session'
        cleaned = redact(message)
        for secret in ('example-password', 'example-key', 'example-session'):
            self.assertNotIn(secret, cleaned)
        self.assertIn('limit=2', cleaned)

    def test_telegram_http_and_api_descriptions_cannot_echo_token(self):
        token = 'unit-test-only-placeholder'
        error = HTTPError('https://api.telegram.org/', 400, 'Bad Request', {},
                          io.BytesIO(json.dumps({'description': token}).encode()))
        with patch('ainews.telegram.urllib.request.urlopen', side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                call(token, 'getMe')
        self.assertNotIn(token, str(caught.exception))
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(json.dumps({'ok': False, 'description': token}).encode())
        with patch('ainews.telegram.urllib.request.urlopen', return_value=response):
            with self.assertRaises(RuntimeError) as caught:
                call(token, 'getMe')
        self.assertNotIn(token, str(caught.exception))

    def test_unexpected_telegram_transport_error_hides_request_url(self):
        token = 'unit-test-only-placeholder'
        with patch('ainews.telegram.urllib.request.urlopen', side_effect=OSError('bot' + token)):
            with self.assertRaises(RuntimeError) as caught:
                call(token, 'getMe')
        self.assertNotIn(token, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_collect_persists_only_redacted_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            try:
                config = {'sources': [{'name': 'Test', 'feed': 'https://example.com/feed', 'hosts': ['example.com']}]}
                with patch('ainews.pipeline.download_feed', side_effect=ValueError('https://u:example-password@example.com/?token=example-key')):
                    report = collect(config, store)
                saved = store.poll_state('Test')['last_error']
                for text in (saved, *report):
                    self.assertNotIn('example-password', text)
                    self.assertNotIn('example-key', text)
            finally:
                store.close()

    def test_redirect_rejected_before_connecting_to_unapproved_host(self):
        handler = SourceRedirectHandler(['example.com'])
        request = Request('https://example.com/feed')
        for url in ('https://127.0.0.1/private', 'http://example.com/feed', 'https://u:p@example.com/feed'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, 'Moved', {}, url)
        self.assertEqual(handler.redirect_request(request, None, 302, 'Moved', {}, 'https://example.com/new').full_url,
                         'https://example.com/new')

    def test_initial_invalid_feed_url_makes_no_request(self):
        with patch('ainews.feeds.urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError):
                download_feed('https://u:p@example.com/feed', allowed_hosts=['example.com'])
        opener.assert_not_called()

    def test_mirror_redirects_require_public_https_before_request(self):
        # A dispatcher can choose another public host, but each hop is checked.
        handler = SourceRedirectHandler(None)
        request = Request('https://example.com/rss')
        targets = ('http://mirror.example/rss', 'https://u:p@mirror.example/rss',
                   'https://127.0.0.1/rss', 'https://[::1]/rss',
                   'https://[fc00::1]/rss', 'https://localhost/rss')
        for url in targets:
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, 'Moved', {}, url)
        self.assertEqual(handler.redirect_request(request, None, 302, 'Moved', {},
                                                 'https://mirror.example/rss').full_url,
                         'https://mirror.example/rss')

    def test_custom_bot_username_retains_channel_access_check(self):
        with patch('ainews.telegram.call', side_effect=[{'username': 'TestNewsBot', 'id': 1},
                {'type': 'channel', 'title': 'Test'}, {'status': 'administrator', 'can_post_messages': True}]):
            self.assertEqual(check_channel_access('mock-only', 123, expected_username='@TestNewsBot'), 'Test')


if __name__ == '__main__':
    unittest.main()
