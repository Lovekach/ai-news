"""Delivery incident controls: real pipeline, temporary data, no real send."""
import runpy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO
from datetime import timedelta

import test_daily
from ainews.daily import publish_daily


class DeliveryIncidentTests(unittest.TestCase):
    setUp = test_daily.DailyTests.setUp
    tearDown = test_daily.DailyTests.tearDown
    add = test_daily.DailyTests.add
    publish = test_daily.DailyTests.publish

    def test_disabled_publication_explains_refusal_without_preparing_or_sending(self):
        with patch('ainews.daily.compose_daily') as compose:
            self.config['auto_publish']=False
            report=self.publish()
        self.assertIn('automatic publishing is disabled',report[0])
        compose.assert_not_called()
        self.sender.assert_not_called()

    def test_missing_channel_explains_refusal_without_touching_ledger(self):
        self.config['channel_id']=None
        report=self.publish()
        self.assertIn('channel is not configured',report[0])
        self.sender.assert_not_called()
        self.assertIsNone(self.store.digest('daily:2026-10-12'))

    def test_deferred_morning_run_explains_time_window_without_token_or_archive(self):
        self.add()
        with patch('ainews.daily.compose_daily') as compose, patch('ainews.telegram.read_token') as token:
            report=self.publish(self.now.replace(hour=5,minute=44))
        self.assertIn('outside 20:56–21:04 MSK publication window',report[0])
        self.assertIn('no late catch-up',report[0])
        compose.assert_not_called()
        token.assert_not_called()
        self.sender.assert_not_called()
        self.assertFalse((self.root/'output').exists())

    def test_successful_receipt_is_reported_and_repeat_send_is_blocked(self):
        self.add()
        self.publish()
        report=self.publish(self.now+timedelta(minutes=1))
        self.assertIn('already reserved (sent)',report[0])
        self.sender.assert_called_once()

    def test_telegram_error_keeps_conservative_receipt_and_blocks_retry(self):
        self.add()
        with patch('ainews.telegram.urllib.request.urlopen', side_effect=HTTPError(
                'https://api.telegram.org/mock',403,'Forbidden',{},BytesIO(b'{"description":"Forbidden"}'))) as network:
            for _ in range(2):
                publish_daily(self.config,self.store,self.root,now=self.now,token_reader=lambda:'mock-only')
        network.assert_called_once()
        self.assertEqual(self.store.digest('daily:2026-10-12')['state'],'send_uncertain')

    def test_hard_interruption_after_reservation_blocks_another_send(self):
        self.add()
        self.sender.side_effect = KeyboardInterrupt('Simulated process termination after reservation')
        with self.assertRaises(KeyboardInterrupt):
            self.publish()
        self.assertEqual(self.store.digest('daily:2026-10-12')['state'],'sending')
        self.publish()
        self.sender.assert_called_once()

    def test_hidden_runner_timeout_is_logged_and_returns_failure(self):
        source=Path(__file__).resolve().parents[1]/'scripts/run_hidden.pyw'
        with patch('sys.argv',['run_hidden.pyw','daily']):
            runner=runpy.run_path(str(source))
        with patch.dict(runner['main'].__globals__,LOG_PATH=self.root/'daily.log'), \
             patch('subprocess.run',side_effect=subprocess.TimeoutExpired('mock-child',120)):
            self.assertEqual(runner['main'](),124)
        text=(self.root/'daily.log').read_text(encoding='utf8')
        self.assertIn('start (hidden)',text)
        self.assertIn('task timed out',text)
        self.assertIsNone(self.store.digest('daily:2026-10-12'))

    def test_child_launch_refusal_logs_failure_without_entering_publisher(self):
        source=Path(__file__).resolve().parents[1]/'scripts/run_hidden.pyw'
        with patch('sys.argv',['run_hidden.pyw','daily']):
            runner=runpy.run_path(str(source))
        with patch.dict(runner['main'].__globals__,LOG_PATH=self.root/'daily.log'), \
             patch('subprocess.run',side_effect=PermissionError('Simulated child launch refusal')) as launch:
            self.assertEqual(runner['main'](),1)
        launch.assert_called_once()
        text=(self.root/'daily.log').read_text(encoding='utf8')
        self.assertIn('PermissionError',text)
        self.assertIsNone(self.store.digest('daily:2026-10-12'))
