import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from ainews.feeds import Entry
from ainews.pipeline import collect
from ainews.store import Store
from ainews.x_rss import parse_x_rss, read_x_source


class XTests(unittest.TestCase):
    def test_canonical_ids_preserve_text_and_skip_reposts(self):
        xml = '''<rss><channel><title>OpenAI</title>
        <item><title>Model launch</title><link>https://nitter.example/OpenAI/status/2100000000000000000</link>
        <pubDate>Wed, 30 Sep 2026 12:00:00 GMT</pubDate>
        <description>&lt;p&gt;We released a new model for coding and local agents.&lt;/p&gt;</description></item>
        <item><title>RT by @OpenAI: other claim</title><link>https://nitter.example/other/status/42</link></item>
        <item><title>Other claim without RT label</title><link>https://nitter.example/other/status/43</link></item>
        <item><title>R to @someone: yes</title><link>https://nitter.example/OpenAI/status/44</link></item>
        </channel></rss>'''
        entries = parse_x_rss(xml, {"name": "X @OpenAI", "handle": "OpenAI"})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].url, "https://x.com/OpenAI/status/2100000000000000000")
        self.assertIn("coding and local agents", entries[0].summary)
        self.assertEqual(entries[0].published, "2026-09-30T12:00:00+00:00")
        with self.assertRaises(ValueError):
            parse_x_rss('<html><title>Challenge</title></html>', {"name": "X @OpenAI", "handle": "OpenAI"})

    def test_x_catchup_dedup_and_independent_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "news.db")
            sources = [{"name": "X @OpenAI", "handle": "OpenAI", "type": "x", "poll_seconds": 60},
                       {"name": "X @bad", "handle": "bad", "type": "x", "poll_seconds": 60}]
            config = {"sources": sources, "digest_lookback_hours": 6}
            now = datetime.now(timezone.utc)
            fresh = Entry("X @OpenAI", "Launch", "https://x.com/OpenAI/status/42", format_datetime(now), "Model launch details")
            old = Entry("X @OpenAI", "Old", "https://x.com/OpenAI/status/41", format_datetime(now-timedelta(days=1)), "Old details")
            def read(source, *args):
                if source["handle"] == "bad":
                    raise ValueError("HTTP 403")
                return [fresh, old], None, None
            with patch("ainews.pipeline._read_source", side_effect=read):
                report = collect(config, store, only_platform="x", respect_schedule=True)
                self.assertTrue(any("1 new" in line for line in report))
                self.assertTrue(any("ERROR" in line for line in report))
                self.assertEqual(store.db.execute("select state from items").fetchall()[0][0], "pending")
                self.assertEqual(store.db.execute("select count(*) from items").fetchone()[0], 1)
                self.assertIn("Нет источников", collect(config, store, only_platform="x", respect_schedule=True)[0])
                collect(config, store, only_platform="x")
                self.assertEqual(store.db.execute("select count(*) from items").fetchone()[0], 1)
            store.close()

    def test_invalid_handle_never_contacts_network(self):
        with patch("ainews.x_rss.source_open") as get:
            with self.assertRaises(ValueError):
                read_x_source({"handle": "bad/path", "name": "Bad"})
            get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
