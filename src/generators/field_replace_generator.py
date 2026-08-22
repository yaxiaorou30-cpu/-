from jinja2 import Template

from src.models import AnalysisContext, SectionConfig
from src.generators.base import BaseGenerator


class FieldReplaceGenerator(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        content_tpl = section_config.content or ""
        data = context.to_dict()
        return Template(content_tpl).render(**data)
