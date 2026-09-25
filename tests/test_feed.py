import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_all
from run_all import Item, HF_VARIANT, important, make_item, render_feed


class FeedBehaviorTests(unittest.TestCase):
    def test_guid_is_stable_and_xml_escapes_text(self):
        item1 = make_item("Qwen", "A & B", "https://example.com/?a=1&b=2",
                          "2026-09-20", "A < B")
        item2 = make_item("Qwen", "A & B", "https://example.com/?a=1&b=2",
                          "2026-09-20", "A < B")
        self.assertEqual(item1.guid, item2.guid)
        root = ET.fromstring(render_feed("测试", "desc", [item1]))
        parsed = root.find("./channel/item")
        self.assertEqual(parsed.findtext("title"), "[Qwen] A & B")
        self.assertEqual(parsed.findtext("description"), "A < B")

    def test_importance_filter_checks_article_title(self):
        when = datetime(2026, 9, 20, tzinfo=timezone.utc)
        self.assertFalse(important(Item("1", "[Kimi] PerceptionBench", "x", when, "")))
        self.assertFalse(important(Item("2", "[Qwen] Qwen 操作教程", "x", when, "")))
        self.assertFalse(important(Item("4", "[Kimi] Kimi API 限时特惠", "x", when, "")))
        self.assertTrue(important(Item("3", "[DeepSeek] DeepSeek-V4 发布", "x", when, "")))

    def test_hf_variant_filter(self):
        self.assertIsNotNone(HF_VARIANT.search("Qwen-Image-2.1-GGUF"))
        self.assertIsNone(HF_VARIANT.search("Qwen-Image-2.1"))

    def test_existing_items_survive_source_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            original_dir = run_all.FEED_DIR
            run_all.FEED_DIR = Path(temp)
            try:
                item = make_item("Qwen", "Qwen4 发布", "https://example.com/qwen4",
                                 run_all.NOW.isoformat())
                path = Path(temp) / "china-ai-official.xml"
                path.write_bytes(render_feed("国产 AI｜重大官方动态",
                                             run_all.FEED_INFO["official"][1], [item]))
                before = path.read_bytes()
                self.assertEqual(run_all.write_feed("official", []), 1)
                self.assertEqual(path.read_bytes(), before)
            finally:
                run_all.FEED_DIR = original_dir

    def test_daily_papers_uses_submission_date_and_stable_paper_link(self):
        paper = {
            "paper": {
                "id": "2609.12345",
                "title": "A new model",
                "summary": "Research abstract",
                "publishedAt": "2026-09-20T00:00:00Z",
                "submittedOnDailyAt": "2026-09-25T00:00:00Z",
            }
        }
        response = Mock()
        response.json.side_effect = [[paper], [], [], [], []]
        with patch.object(run_all, "get", return_value=response):
            items = run_all.huggingface_papers(Mock())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published, datetime(2026, 9, 25, tzinfo=timezone.utc))
        self.assertEqual(items[0].link, "https://huggingface.co/papers/2609.12345")
        self.assertEqual(items[0].description, "Research abstract")


if __name__ == "__main__":
    unittest.main()
