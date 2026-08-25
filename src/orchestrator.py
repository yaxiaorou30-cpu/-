import json
import os
from typing import Optional, List

import yaml

from src.models import RawRecord
from src.preprocessor import Preprocessor
from src.analyzer import Analyzer, EventClusterer
from src.template_manager import TemplateManager
from src.pipeline import Pipeline
from src.renderer import Renderer
from src.file_namer import generate_filename, ensure_unique_path
from src.report_builder import attach_report_metadata, select_key_samples
from src.record_analysis import body_review_is_pending
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _require_completed_body_reviews(raw_data: List[dict]) -> None:
    pending_count = sum(
        1 for record in raw_data if body_review_is_pending(record)
    )
    if pending_count:
        raise ValueError(
            f"有 {pending_count} 条记录正文获取失败且尚未人工核查，不能生成报告"
        )


class Orchestrator:
    def __init__(self, config_path: str = "config/app_settings.yaml"):
        self.config = self._load_config(config_path)
        self.preprocessor = Preprocessor()
        self.analyzer = Analyzer(config=self.config.get("analyzer", {}))
        self.template_manager = TemplateManager(self.config.get("templates_dir", "config/templates"))
        self.renderer = Renderer()

    def generate_report(self, input_json: str, template_id: str, output_docx: str,
                        docx_template_path: Optional[str] = None,
                        region: Optional[str] = None,
                        time_range: Optional[str] = None,
                        section_overrides: Optional[dict] = None,
                        raw_data_override: Optional[List[dict]] = None,
                        meta_override: Optional[dict] = None):
        logger.info(f"开始生成报告: input={input_json}, template={template_id}, output={output_docx}")

        raw_data = list(raw_data_override) if raw_data_override is not None else self._load_json(input_json)
        meta = dict(meta_override) if meta_override is not None else self._load_related_meta(input_json)
        _require_completed_body_reviews(raw_data)
        records = self.preprocessor.process(raw_data)
        records = self.preprocessor.deduplicate(records)

        analysis_context = self.analyzer.analyze(
            records,
            topic_hint=self._topic_hint(meta),
            query_keywords=self._query_keywords(meta),
            evidence_samples=select_key_samples(
                raw_data,
                topic_hint=self._topic_hint(meta),
            ),
        )

        llm_config = self.config.get("llm", {})
        pipeline = Pipeline(
            template_manager=self.template_manager,
            analyzer=self.analyzer,
            llm_config=llm_config,
        )

        doc_ctx = pipeline.run(records, template_id, prebuilt_context=analysis_context)
        self._apply_section_overrides(doc_ctx, section_overrides or {})
        report_meta = attach_report_metadata(
            document_context=doc_ctx,
            raw_data=raw_data,
            meta=meta,
            analysis_context=analysis_context,
        )
        self._validate_report_grounding(report_meta, raw_data)

        event_keyword = analysis_context.event_keyword
        if event_keyword and region and time_range:
            template = self.template_manager.load_template(template_id)
            template_name = template.name if template else "舆情通报"
            new_filename = generate_filename(region, time_range, template_name, True, event_keyword=event_keyword)
            dir_name = os.path.dirname(output_docx) or "output"
            output_docx = ensure_unique_path(dir_name, new_filename)

        # 若未指定 docx 模板，尝试自动匹配
        if docx_template_path is None:
            candidate = os.path.join(
                self.config.get("templates_docx_dir", "templates_docx"),
                f"{template_id}_template.docx",
            )
            if os.path.exists(candidate):
                docx_template_path = candidate

        self.renderer.render(doc_ctx, docx_template_path, output_docx)
        logger.info("报告生成完成")
        return output_docx

    def build_report_preview(self, input_json: str, template_id: str,
                             region: Optional[str] = None,
                             time_range: Optional[str] = None,
                             raw_data_override: Optional[List[dict]] = None,
                             meta_override: Optional[dict] = None) -> dict:
        logger.info(f"生成报告预览: input={input_json}, template={template_id}")
        raw_data = list(raw_data_override) if raw_data_override is not None else self._load_json(input_json)
        meta = dict(meta_override) if meta_override is not None else self._load_related_meta(input_json)
        _require_completed_body_reviews(raw_data)
        records = self.preprocessor.process(raw_data)
        records = self.preprocessor.deduplicate(records)
        analysis_context = self.analyzer.analyze(
            records,
            topic_hint=self._topic_hint(meta),
            query_keywords=self._query_keywords(meta),
            evidence_samples=select_key_samples(
                raw_data,
                topic_hint=self._topic_hint(meta),
            ),
        )
        pipeline = Pipeline(
            template_manager=self.template_manager,
            analyzer=self.analyzer,
            llm_config=self.config.get("llm", {}),
        )
        doc_ctx = pipeline.run(records, template_id, prebuilt_context=analysis_context)
        report_meta = attach_report_metadata(
            document_context=doc_ctx,
            raw_data=raw_data,
            meta=meta,
            analysis_context=analysis_context,
        )
        template = self.template_manager.load_template(template_id)
        return {
            "template_id": template_id,
            "template_name": template.name if template else template_id,
            "region": region or "",
            "time_range": time_range or "",
            **report_meta,
        }

    def generate_multi_event_reports(self, input_json: str, output_dir: str = "output",
                                     docx_template_path: Optional[str] = None,
                                     region: Optional[str] = None,
                                     time_range: Optional[str] = None) -> List[str]:
        """多事件报告生成 - 自动聚类并为每个事件生成一套报告"""
        logger.info(f"开始多事件报告生成: input={input_json}")

        raw_data = self._load_json(input_json)
        records = self.preprocessor.process(raw_data)
        records = self.preprocessor.deduplicate(records)

        clusterer = EventClusterer()
        clusters = clusterer.cluster(records)
        logger.info(f"聚类得到 {len(clusters)} 个事件")

        output_files = []
        os.makedirs(output_dir, exist_ok=True)

        templates = self.template_manager.list_templates()
        llm_config = self.config.get("llm", {})

        for idx, cluster_records in enumerate(clusters):
            ctx = self.analyzer.analyze(cluster_records)
            event_keyword = ctx.event_keyword or f"事件{idx+1}"
            logger.info(f"事件{idx+1}: {event_keyword} ({len(cluster_records)}条记录)")

            pipeline = Pipeline(
                template_manager=self.template_manager,
                analyzer=self.analyzer,
                llm_config=llm_config,
            )

            for tmpl in templates:
                template = self.template_manager.load_template(tmpl["id"])
                template_name = template.name if template else "舆情通报"
                filename = generate_filename(
                    region=region,
                    time_range=time_range,
                    template_name=template_name,
                    is_same_region_time=len(templates) > 1,
                    event_keyword=event_keyword,
                )
                output_path = ensure_unique_path(output_dir, filename)

                try:
                    doc_ctx = pipeline.run(cluster_records, tmpl["id"], prebuilt_context=ctx)
                    self.renderer.render(doc_ctx, docx_template_path, output_path)
                    output_files.append(output_path)
                    logger.info(f"  ✓ {output_path}")
                except Exception as e:
                    logger.error(f"  ✗ 生成失败: {e}")

        logger.info(f"多事件报告生成完成，共 {len(output_files)} 个文件")
        return output_files

    @staticmethod
    def _load_config(path: str) -> dict:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _load_json(path: str) -> list:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _load_related_meta(input_json: str) -> dict:
        data_path = os.path.abspath(input_json)
        data_dir = os.path.dirname(data_path)
        data_name = os.path.basename(data_path)
        if data_name == "latest_news.json":
            candidates = [os.path.join(data_dir, "latest_news_meta.json")]
        else:
            stem, _ = os.path.splitext(data_name)
            candidates = [os.path.join(data_dir, f"{stem}_meta.json")]
        for candidate in candidates:
            if os.path.exists(candidate):
                with open(candidate, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        return {}

    @staticmethod
    def _topic_hint(meta: dict) -> str:
        topic = str((meta or {}).get("topic") or "").strip()
        if topic:
            return topic
        keywords = (meta or {}).get("keywords") or []
        if isinstance(keywords, list):
            return "、".join(str(item).strip() for item in keywords if str(item).strip())
        return str(keywords or "").strip()

    @staticmethod
    def _query_keywords(meta: dict) -> List[str]:
        keywords = (meta or {}).get("keywords") or []
        if isinstance(keywords, list):
            return [str(item).strip() for item in keywords if str(item).strip()]
        return [item.strip() for item in str(keywords or "").split(",") if item.strip()]

    @staticmethod
    def _apply_section_overrides(document_context, overrides: dict):
        if not isinstance(overrides, dict):
            return
        for section_id, value in overrides.items():
            if section_id not in document_context.sections:
                continue
            text = str(value or "").strip()
            if not text:
                continue
            document_context.sections[section_id] = text
            if section_id == "title":
                document_context.title = text[:200]

    @staticmethod
    def _validate_report_grounding(report_meta: dict, raw_data: List[dict]):
        if not raw_data:
            raise ValueError("没有可用于报告生成的数据")
        grounding = report_meta.get("grounding") or {}
        unknown_ids = grounding.get("unknown_sample_ids") or []
        if unknown_ids:
            raise ValueError(f"报告正文包含未知样本编号：{'、'.join(unknown_ids)}")
        if int(grounding.get("cited_sample_count") or 0) < 1:
            raise ValueError("报告正文没有可追溯样本引用，请先在预览中保留至少一个 [S编号]")


def generate_report(input_json: str, template_id: str, output_docx: str,
                    docx_template_path: Optional[str] = None,
                    config_path: str = "config/app_settings.yaml",
                    region: Optional[str] = None,
                    time_range: Optional[str] = None,
                    section_overrides: Optional[dict] = None,
                    raw_data_override: Optional[List[dict]] = None,
                    meta_override: Optional[dict] = None):
    orch = Orchestrator(config_path=config_path)
    return orch.generate_report(
        input_json,
        template_id,
        output_docx,
        docx_template_path,
        region,
        time_range,
        section_overrides,
        raw_data_override,
        meta_override,
    )


def build_report_preview(input_json: str, template_id: str,
                         config_path: str = "config/app_settings.yaml",
                         region: Optional[str] = None,
                         time_range: Optional[str] = None,
                         raw_data_override: Optional[List[dict]] = None,
                         meta_override: Optional[dict] = None) -> dict:
    orch = Orchestrator(config_path=config_path)
    return orch.build_report_preview(
        input_json,
        template_id,
        region,
        time_range,
        raw_data_override,
        meta_override,
    )


def generate_multi_event_reports(input_json: str, output_dir: str = "output",
                                 docx_template_path: Optional[str] = None,
                                 config_path: str = "config/app_settings.yaml",
                                 region: Optional[str] = None,
                                 time_range: Optional[str] = None) -> List[str]:
    orch = Orchestrator(config_path=config_path)
    return orch.generate_multi_event_reports(input_json, output_dir, docx_template_path, region, time_range)
