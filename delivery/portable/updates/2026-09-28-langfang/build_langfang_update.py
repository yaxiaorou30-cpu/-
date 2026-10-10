"""Derive a Langfang-only cumulative update without editing the Tianjin app."""
import ast
import hashlib
import json
from pathlib import Path
from pprint import pformat
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE_ZIP = HERE.parent / "2026-09-25/AI舆情检测系统-Windows11-累计更新-20260925.zip"
BASE_SHA256 = "22e5f79bb51195f18146ad373fbe479c13fbfd3a2850b920df1039e30fa1a2df"
OUTPUT_ZIP = HERE / "AI舆情检测系统-Windows11-廊坊累计更新-20260928.zip"
LOCAL_SOURCES = [
    {
        "name": "河北省公安厅公安要闻",
        "parser": "official_listing",
        "priority": 5,
        "timeout": 15,
        "enabled": True,
        # Provincial coverage must not be skipped when the user selects Langfang.
        "source_region": "",
        "url_template": "http://gat.hebei.gov.cn/default.php?mod=article&fid=14",
        "link_selectors": ['.link_14 a[href*="do=detail"]'],
        "article_path_prefixes": ["/default.php"],
        "require_date": True,
        "date_context_levels": 3,
    },
    {
        "name": "河北省政府新闻发布会",
        "parser": "official_listing",
        "priority": 15,
        "timeout": 15,
        "enabled": True,
        "source_region": "",
        "url_template": "https://www.hebei.gov.cn/columns/6b529089-3c22-40ef-8d24-fda72cb33bf5/index.html",
        "link_selectors": [".fang_zhuti a"],
        "article_path_prefixes": ["/columns/6b529089-3c22-40ef-8d24-fda72cb33bf5/"],
        "require_date": True,
    },
    {
        "name": "廊坊市应急管理局工作动态",
        "parser": "official_listing",
        "priority": 20,
        "timeout": 15,
        "enabled": True,
        "source_region": "河北省廊坊市",
        "url_template": "https://yjglj.lf.gov.cn/aqsc",
        "link_selectors": ['a[href^="/aqsc/info/"]'],
        "article_path_prefixes": ["/aqsc/info/"],
        "require_date": True,
    },
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def build_payload():
    if sha256(BASE_ZIP.read_bytes()) != BASE_SHA256:
        raise ValueError("Common cumulative update checksum mismatch")
    with ZipFile(BASE_ZIP) as base:
        payload = {name: base.read(name) for name in base.namelist()}
    source = payload["src/crawler.py"].decode("utf-8-sig")
    registry = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STABLE_SOURCE_REGISTRY" for t in n.targets))
    old_sources = ast.literal_eval(registry.value)
    if len(old_sources) != 11 or not all("天津" in c["name"] for c in old_sources[:4]):
        raise ValueError("Unexpected source registry; review before rebuilding")
    lines = source.splitlines(keepends=True)
    replacement = "STABLE_SOURCE_REGISTRY = " + pformat(LOCAL_SOURCES + old_sources[4:], sort_dicts=False, width=100) + "\n"
    source = "".join(lines[:registry.lineno - 1]) + replacement + "".join(lines[registry.end_lineno:])
    old_context = "ancestor = link.parent\n            for _ in range(2):"
    if source.count(old_context) != 1:
        raise ValueError("Unexpected date parser; review before rebuilding")
    source = source.replace(old_context, 'ancestor = link.parent\n            for _ in range(int(source_config.get("date_context_levels", 2))):')
    compile(source, "src/crawler.py", "exec")
    payload["src/crawler.py"] = source.encode("utf-8")
    html = payload["web/index.html"].decode("utf-8-sig")
    old_description = "优先接入国家级业务官网和天津本地公安、政府发布、应急信息栏目；仅显示已真实核对的来源。"
    if html.count(old_description) != 1:
        raise ValueError("Unexpected official-source description")
    payload["web/index.html"] = html.replace(old_description, "接入国家级业务官网、河北省公安厅公安要闻、河北省政府新闻发布会和廊坊市应急管理局工作动态；出入境信息保留国家移民管理局来源。").encode("utf-8")
    payload["更新说明.txt"] = (HERE / "更新说明.txt").read_bytes()
    manifest = json.loads(payload["manifest.json"])
    manifest.update({"variant": "langfang-20260928", "common_update_sha256": BASE_SHA256, "official_sources": LOCAL_SOURCES})
    manifest["file_sha256"] = {name: sha256(payload[name]) for name in manifest["file_sha256"]}
    payload["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return payload


if __name__ == "__main__":
    payload = build_payload()
    with ZipFile(OUTPUT_ZIP, "x", compression=ZIP_DEFLATED) as update:
        for name, data in payload.items():
            update.writestr(name, data)
    with ZipFile(OUTPUT_ZIP) as update:
        assert update.testzip() is None
        assert set(update.namelist()) == set(payload)
        assert all(update.read(name) == data for name, data in payload.items())
    (HERE / "SHA256SUMS.txt").write_text(f"{sha256(OUTPUT_ZIP.read_bytes())}  {OUTPUT_ZIP.name}\n", encoding="utf-8")
    print(OUTPUT_ZIP)
