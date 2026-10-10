"""Run with the project's .venv Python; no network or client data required."""
import ast
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from bs4 import BeautifulSoup
from build_langfang_update import BASE_ZIP, build_payload


class LangfangUpdateTests(unittest.TestCase):
    def test_sources_parser_and_unchanged_rules(self):
        payload = build_payload()
        with ZipFile(BASE_ZIP) as base:
            for name in base.namelist():
                if name not in {"src/crawler.py", "web/index.html", "更新说明.txt", "manifest.json"}:
                    self.assertEqual(payload[name], base.read(name))
            original = ast.parse(base.read("src/crawler.py").decode("utf-8-sig"))
        source = payload["src/crawler.py"].decode("utf-8")
        tree = ast.parse(source)
        old_registry = next(n for n in original.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STABLE_SOURCE_REGISTRY" for t in n.targets))
        registry = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STABLE_SOURCE_REGISTRY" for t in n.targets))
        configs = ast.literal_eval(registry.value)
        self.assertEqual(configs[3:], ast.literal_eval(old_registry.value)[4:])
        self.assertFalse(any("天津" in c["name"] for c in configs))
        self.assertTrue(all(c["require_date"] for c in configs[:3]))
        # Only registry metadata and the one date-context lookup may differ.
        original.body.remove(old_registry)
        tree.body.remove(registry)
        old_dump = ast.dump(original)
        restored = source.replace('range(int(source_config.get("date_context_levels", 2)))', 'range(2)')
        restored_tree = ast.parse(restored)
        restored_tree.body = [n for n in restored_tree.body if not (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STABLE_SOURCE_REGISTRY" for t in n.targets))]
        self.assertEqual(ast.dump(restored_tree), old_dump)
        namespace = {"__file__": str(ROOT / "src/crawler.py"), "__name__": "langfang_check"}
        exec(compile(source, namespace["__file__"], "exec"), namespace)
        crawler = namespace["NewsCrawler"].__new__(namespace["NewsCrawler"])
        crawler._source_acceptance_mode = True
        snippets = [
            '<table><tr><td><span><span class="link_14"><a href="default.php?mod=article&amp;do=detail&amp;tid=41750">河北公安机关开展公共安全专项检查</a></span></span><span>[2026-09-24]</span></td></tr></table>',
            '<div class="fangkuang"><div class="fang_zhuti"><a href="/columns/6b529089-3c22-40ef-8d24-fda72cb33bf5/202608/31/test.html">河北省政府举行新闻发布会介绍工作进展</a></div><div class="fang_time">2026-08-28</div></div>',
            '<li><a href="/aqsc/info/14683"><div class="tit">廊坊市开展安全宣传志愿服务活动</div><div class="time">2026-02-03</div></a></li>',
        ]
        for config, html in zip(configs, snippets):
            items = crawler._parse_official_listing(BeautifulSoup(html, "html.parser"), "", config["name"], config["url_template"])
            self.assertEqual(len(items), 1, config["name"])
            self.assertTrue(items[0]["pub_time"])
            missing_date = html.replace(items[0]["pub_time"], "")
            self.assertEqual(crawler._parse_official_listing(BeautifulSoup(missing_date, "html.parser"), "", config["name"], config["url_template"]), [])
        requests = crawler._build_stable_source_requests("测试", "河北省", "廊坊市", [c["name"] for c in configs[:3]])
        self.assertEqual(len(requests), 3)
        self.assertIn("河北", payload["web/index.html"].decode("utf-8"))
        self.assertNotIn("天津本地公安", payload["web/index.html"].decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
