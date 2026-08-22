from typing import Dict, Any, List, Optional

from src.models import RawRecord, AnalysisContext, DocumentContext, TemplateConfig
from src.analyzer import Analyzer
from src.template_manager import TemplateManager
from src.generators import build_generator_registry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Pipeline:
    def __init__(self, template_manager: TemplateManager, analyzer: Analyzer, llm_config: dict = None):
        self.template_manager = template_manager
        self.analyzer = analyzer
        self.generator_registry = build_generator_registry(llm_config or {})

    def run(self, records: List[RawRecord], template_id: str, prebuilt_context: Optional[AnalysisContext] = None) -> DocumentContext:
        logger.info(f"管道启动，模板: {template_id}")

        template = self.template_manager.load_template(template_id)
        
        if prebuilt_context is not None:
            context = prebuilt_context
            logger.info("使用预构建的分析上下文")
        else:
            context = self.analyzer.analyze(records)

        section_order = [s.id for s in template.sections]
        section_names = {s.id: s.name for s in template.sections if s.name}
        section_review = {s.id: s.require_manual_review for s in template.sections if s.require_manual_review}

        doc = DocumentContext(
            template_id=template_id,
            title="",
            metadata={
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "section_order": section_order,
                "section_names": section_names,
                "section_review": section_review,
            },
            event_keyword=context.event_keyword,
        )

        for section in template.sections:
            generator = self._resolve_generator(section)
            text = generator.generate(context, section)
            doc.sections[section.id] = text
            if section.is_title:
                doc.title = text
            logger.info(f"章节生成完成: {section.id} ({section.name or '无名称'})")

        doc.event_keyword = context.event_keyword

        logger.info("管道执行完毕")
        return doc

    def _resolve_generator(self, section_config):
        gtype = section_config.generator
        if gtype == "rule" and section_config.rule_class:
            gen = self.generator_registry.get(section_config.rule_class)
            if gen:
                return gen
            raise ValueError(f"规则生成器未注册: {section_config.rule_class}")
        gen = self.generator_registry.get(gtype)
        if not gen:
            raise ValueError(f"生成器类型未注册: {gtype}")
        return gen
