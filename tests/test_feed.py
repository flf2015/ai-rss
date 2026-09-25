import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
        self.assertTrue(important(Item("3", "[DeepSeek] DeepSeek-V4 发布", "x", when, "")))

    def test_hf_variant_filter(self):
        self.assertIsNotNone(HF_VARIANT.search("Qwen-Image-2.1-GGUF"))
        self.assertIsNone(HF_VARIANT.search("Qwen-Image-2.1"))


if __name__ == "__main__":
    unittest.main()
