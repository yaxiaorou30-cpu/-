#!/usr/bin/env python3
import argparse
import json
import sys
import os
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.template_manager import TemplateManager
from src.crawler import crawl_and_save, TIME_RANGE_MAP, PLATFORM_LIST, COLLECT_LEVELS, STABLE_SOURCE_REGISTRY
from src.heat_analyzer import get_all_provinces, get_cities_by_province
from src.file_namer import generate_filename, ensure_unique_path


def generate_all_reports(input_json: str, output_dir: str = "output", region: str = None):
    from src.orchestrator import generate_report

    tm = TemplateManager("config/templates")
    templates = tm.list_templates()

    print(f"[AI+舆情检测系统] 一键生成所有报告 ({len(templates)} 个)...")

    os.makedirs(output_dir, exist_ok=True)
    is_same = len(templates) > 1

    for template in templates:
        template_id = template["id"]
        filename = generate_filename(
            region=region,
            template_name=template["name"],
            is_same_region_time=is_same
        )
        output_path = ensure_unique_path(output_dir, filename)

        print(f"\n--- 正在生成: {template['name']} ---")
        print(f"  输出: {output_path}")

        try:
            generate_report(
                input_json=input_json,
                template_id=template_id,
                output_docx=output_path,
            )
            print(f"  [成功] 生成完成")
        except Exception as e:
            print(f"  [失败] {e}")

    print(f"\n[完成] 所有报告已保存至: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(description="AI+舆情检测系统 - 舆情通报生成器")

    parser.add_argument("--input", "-i", default="data/sample_input.json", help="输入 JSON 文件路径")
    parser.add_argument("--template", "-t", default="event_report", help="模板 ID")
    parser.add_argument("--output", "-o", default=None, help="输出 Word 文件路径（留空则自动命名）")
    parser.add_argument("--docx-template", default=None, help="Word 模板文件路径（可选）")
    parser.add_argument("--config", "-c", default="config/app_settings.yaml", help="配置文件路径")

    parser.add_argument("--list-templates", action="store_true", help="列出可用模板")
    parser.add_argument("--all", "-a", action="store_true", help="一键生成所有模板报告")

    parser.add_argument("--crawl", action="store_true", help="实时采集新闻数据")
    parser.add_argument("--keywords", "-k", nargs="+", default=["警情通报", "案件通报", "警方通报"], help="采集关键词")
    parser.add_argument("--region", "-r", default=None, help="地区筛选（省/市，例如：湖北省武汉市）")
    parser.add_argument("--time-range", default="近一周",
                       choices=list(TIME_RANGE_MAP.keys()),
                       help="时间范围筛选")
    parser.add_argument("--collect-level", default="标准采集",
                       choices=list(COLLECT_LEVELS.keys()),
                       help="采集阈值等级")
    stable_source_names = [source["name"] for source in STABLE_SOURCE_REGISTRY if source.get("enabled", True)]
    parser.add_argument("--stable-source", nargs="+", default=None,
                       choices=stable_source_names,
                       help=f"稳定公开源，可多选（默认全部），可选: {', '.join(stable_source_names)}")
    parser.add_argument("--social-platform", nargs="+", default=None,
                       choices=PLATFORM_LIST,
                       help=f"社交增强平台，可多选（默认前置公开增强），可选: {', '.join(PLATFORM_LIST)}")
    parser.add_argument("--platform", "-p", nargs="+", default=None,
                       choices=PLATFORM_LIST,
                       help="兼容旧参数：等同于 --social-platform")
    parser.add_argument("--source-strategy", default="stable_first",
                       choices=["stable_first", "stable", "social", "hybrid"],
                       help="数据源策略：stable_first=稳定公开源优先，stable=只跑稳定源，social=只跑社交公开页，hybrid=stable_first 兼容别名")
    parser.add_argument("--min-real-results", type=int, default=None,
                       help="最低真实数据条数，低于该值会在 meta 中标记质量风险")

    args = parser.parse_args()

    if args.list_templates:
        tm = TemplateManager("config/templates")
        templates = tm.list_templates()
        print("可用模板列表：")
        for t in templates:
            print(f"  - {t['id']}: {t['name']} ({t['description']})")
        return

    if args.crawl:
        print(f"[AI+舆情检测系统] 正在采集实时新闻数据...")
        print(f"  地区: {args.region or '全国'}")
        print(f"  时间范围: {args.time_range}")
        print(f"  采集等级: {args.collect_level}")
        print(f"  数据源策略: {args.source_strategy}")
        print(f"  关键词: {', '.join(args.keywords)}")
        social_platforms = args.social_platform or args.platform
        print(f"  稳定公开源: {', '.join(args.stable_source) if args.stable_source else '全部启用源'}")
        print(f"  社交增强平台: {', '.join(social_platforms) if social_platforms else '默认'}")

        input_file = crawl_and_save(
            keywords=args.keywords,
            region=args.region,
            time_range=args.time_range,
            social_platforms=social_platforms,
            stable_sources=args.stable_source,
            collect_level=args.collect_level,
            source_strategy=args.source_strategy,
            min_real_results=args.min_real_results,
        )
        print(f"  采集完成！数据已保存至: {input_file}")
        print(f"  采集元数据: data/latest_news_meta.json")
        meta_path = os.path.splitext(input_file)[0] + "_meta.json"
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            summary = meta.get("summary", {})
            print(
                "  采集检查: "
                f"真实 {summary.get('real_count', 0)} 条，"
                f"稳定源 {summary.get('stable_real_count', 0)} 条，"
                f"社交增强 {summary.get('social_real_count', 0)} 条，"
                f"状态 {summary.get('check_status_label', '未检查')}"
            )

        if args.all:
            generate_all_reports(input_file, region=args.region)
            return
        args.input = input_file

    if args.all:
        generate_all_reports(args.input, region=args.region)
        return

    print(f"[AI+舆情检测系统] 正在生成通报...")
    print(f"  输入: {args.input}")
    print(f"  模板: {args.template}")

    if args.output:
        output_path = args.output
    else:
        os.makedirs("output", exist_ok=True)
        tm = TemplateManager("config/templates")
        templates = tm.list_templates()
        template_name = next((t["name"] for t in templates if t["id"] == args.template), "报告")
        filename = generate_filename(
            region=args.region,
            template_name=template_name,
            is_same_region_time=False
        )
        output_path = ensure_unique_path("output", filename)

    print(f"  输出: {output_path}")

    from src.orchestrator import generate_report

    generate_report(
        input_json=args.input,
        template_id=args.template,
        output_docx=output_path,
        docx_template_path=args.docx_template,
        config_path=args.config,
    )

    print(f"[完成] 文档已保存至: {output_path}")


if __name__ == "__main__":
    main()
