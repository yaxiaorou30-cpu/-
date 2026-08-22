from src.generators.base import BaseGenerator
from src.generators.evidence_generators import EVIDENCE_GENERATOR_REGISTRY
from src.generators.rule_generators import RULE_GENERATOR_REGISTRY
from src.generators.field_replace_generator import FieldReplaceGenerator


class LLMDisabledGenerator(BaseGenerator):
    def generate(self, context, section_config):
        return f"【{section_config.name or '相关章节'}】(LLM未启用，此内容为占位文本。)"


def build_generator_registry(llm_config: dict = None):
    registry = {
        "field_replace": FieldReplaceGenerator(),
        "llm": LLMDisabledGenerator(),
    }
    for name, cls in RULE_GENERATOR_REGISTRY.items():
        registry[name] = cls()
    for name, cls in EVIDENCE_GENERATOR_REGISTRY.items():
        registry[name] = cls()
    return registry
