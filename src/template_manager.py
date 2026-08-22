import os
from typing import Optional

import yaml

from src.models import TemplateConfig, SectionConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TemplateManager:
    def __init__(self, templates_dir: str):
        self.templates_dir = templates_dir
        self._cache = {}

    def load_template(self, template_id: str) -> TemplateConfig:
        if template_id in self._cache:
            return self._cache[template_id]

        path = os.path.join(self.templates_dir, f"{template_id}.yaml")
        if not os.path.exists(path):
            raise FileNotFoundError(f"模板文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        sections = []
        for sec in data.get("sections", []):
            sections.append(
                SectionConfig(
                    id=sec["id"],
                    name=sec.get("name"),
                    generator=sec.get("generator", "rule"),
                    rule_class=sec.get("rule_class"),
                    prompt_template=sec.get("prompt_template"),
                    dependencies=sec.get("dependencies", []),
                    min_words=sec.get("min_words", 0),
                    max_words=sec.get("max_words", 1000),
                    is_title=sec.get("is_title", False),
                    content=sec.get("content"),
                    require_manual_review=sec.get("require_manual_review", False),
                )
            )

        config = TemplateConfig(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            sections=sections,
        )
        self._cache[template_id] = config
        logger.info(f"模板已加载: {template_id} ({config.name})")
        return config

    def list_templates(self) -> list:
        result = []
        if not os.path.exists(self.templates_dir):
            return result
        for fn in os.listdir(self.templates_dir):
            if fn.endswith(".yaml"):
                tid = fn[:-5]
                try:
                    cfg = self.load_template(tid)
                    result.append({"id": cfg.id, "name": cfg.name, "description": cfg.description})
                except Exception as e:
                    logger.warning(f"加载模板 {fn} 失败: {e}")
        return result
