from typing import Dict, Iterable, List, Tuple

from src.generators.base import BaseGenerator
from src.models import AnalysisContext, SectionConfig


THEME_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("核心事实与进展", ("宣布", "公布", "发布", "通报", "颁发", "获奖", "举行", "现场", "进展", "回应", "结果", "名单")),
    ("专业解释与背景", ("研究", "科普", "原理", "原因", "为何", "方程", "猜想", "专业", "解读", "到底", "重要")),
    ("人物经历与机构关联", ("经历", "成长", "履历", "大学", "北大", "高校", "博士", "教授", "个人", "迷茫", "科研")),
    ("公众态度与评价", ("恭喜", "祝贺", "争议", "尴尬", "破防", "质疑", "支持", "感动", "致敬", "评价")),
    ("风险与待核查信息", ("风险", "谣言", "造谣", "未经证实", "网传", "担忧", "投诉", "质疑", "假消息")),
    ("公共安全与现场影响", ("台风", "暴雨", "大风", "积水", "洪水", "内涝", "受伤", "死亡", "失联", "灾害")),
    ("交通与公共服务", ("航班", "延误", "取消", "道路", "地铁", "机场", "停运", "停课", "学校", "教育局", "出行")),
    ("预警与权威信息", ("预警", "应急", "通报", "发布", "防御", "提醒", "气象", "官方")),
]


class EvidenceGeneratorBase(BaseGenerator):
    """只根据采集样本和分析统计生成内容，不补写未出现的事件事实。"""

    def _topic(self, context: AnalysisContext) -> str:
        return context.task_topic or context.event_keyword or "本次舆情任务"

    @staticmethod
    def _samples(context: AnalysisContext) -> List[Dict]:
        return [
            sample
            for sample in context.evidence_samples
            if isinstance(sample, dict) and sample.get("reference_id")
        ]

    @staticmethod
    def _short(value, limit: int = 72) -> str:
        text = str(value or "")
        text = text.replace("\u200b", "").replace("【", "").replace("】", "")
        text = " ".join(text.split()).strip(" ，,；;。")
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}…"

    @classmethod
    def _sample_statement(cls, sample: Dict, include_time: bool = False) -> str:
        ref = sample.get("reference_id")
        platform = cls._short(sample.get("platform") or "未知平台", 20)
        source = cls._short(sample.get("source") or sample.get("author") or "未知来源", 28)
        title = cls._short(sample.get("title") or sample.get("content_excerpt") or "未命名内容", 88)
        prefix = ""
        if include_time and cls._has_confirmed_time(sample):
            prefix = f"{cls._format_time(sample.get('pub_time'))}，"
        return f"{prefix}{platform}来源“{source}”发布内容“{title}”[{ref}]"

    @staticmethod
    def _has_confirmed_time(sample: Dict) -> bool:
        pub_time = str(sample.get("pub_time") or "").strip()
        return bool(pub_time and pub_time not in {"-", "unknown", "未知"}
                    and sample.get("time_basis") != "unknown")

    @staticmethod
    def _format_time(value) -> str:
        text = str(value or "").strip().replace("T", " ")
        return text[:16] if len(text) >= 16 else text

    @classmethod
    def _themes(cls, samples: Iterable[Dict]) -> List[Dict]:
        matched = []
        for theme_name, keywords in THEME_RULES:
            refs = []
            hit_words = []
            for sample in samples:
                haystack = f"{sample.get('title', '')} {sample.get('content_excerpt', '')}"
                sample_hits = [keyword for keyword in keywords if keyword in haystack]
                if sample_hits:
                    refs.append(str(sample.get("reference_id")))
                    hit_words.extend(sample_hits)
            if refs:
                matched.append({
                    "name": theme_name,
                    "refs": cls._unique(refs)[:4],
                    "keywords": cls._unique(hit_words)[:5],
                })
        return matched

    @staticmethod
    def _unique(values: Iterable[str]) -> List[str]:
        result = []
        seen = set()
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @staticmethod
    def _refs(refs: Iterable[str]) -> str:
        return "".join(f"[{ref}]" for ref in refs)

    @staticmethod
    def _platform_distribution(context: AnalysisContext) -> str:
        items = sorted(context.platform_dist.items(), key=lambda item: (-item[1], item[0]))
        return "、".join(f"{name}{count}条" for name, count in items) or "无"

    @staticmethod
    def _sentiment(context: AnalysisContext) -> str:
        labels = (
            (("positive", "正面", "正向"), "正向"),
            (("neutral", "中性"), "中性"),
            (("negative", "负面", "负向"), "负向"),
        )
        values = []
        for keys, label in labels:
            ratio = next(
                (
                    float(context.sentiment_ratio.get(key, 0) or 0)
                    for key in keys
                    if key in context.sentiment_ratio
                ),
                0.0,
            )
            values.append(f"{label}{ratio:.0%}")
        return "、".join(values)

    @staticmethod
    def _content_categories(context: AnalysisContext) -> str:
        items = sorted(
            context.content_category_dist.items(),
            key=lambda item: (-item[1], item[0]),
        )
        return "、".join(f"{name}{count}条" for name, count in items) or "无"

    @staticmethod
    def _paragraphs(lines: Iterable[str]) -> str:
        return "\n".join(line.strip() for line in lines if str(line or "").strip())


class GroundedSummaryRule(EvidenceGeneratorBase):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        samples = self._samples(context)
        lines = [
            (
                f"本报告围绕“{self._topic(context)}”整理本次采集结果。"
                f"共获得{context.total_posts}条记录，覆盖{len(context.platform_dist)}个平台；"
                f"各平台样本量为：{self._platform_distribution(context)}。"
                "正文中的具体内容均以文末重点样本编号回指原始链接，样本陈述不等同于已核实事实。"
            )
        ]
        if samples:
            themes = self._themes(samples)
            if themes:
                lines.append("综合重点样本，本次内容主要集中在：")
                for index, theme in enumerate(themes[:4], 1):
                    words = "、".join(theme["keywords"])
                    lines.append(
                        f"{index}. {theme['name']}：相关样本出现“{words}”等内容"
                        f"{self._refs(theme['refs'])}。"
                    )
            else:
                lines.append("本次较具代表性的采集内容包括：")
                lines.extend(
                    f"{index + 1}. {self._sample_statement(sample)}。"
                    for index, sample in enumerate(samples[:3])
                )
        else:
            lines.append("当前没有可引用的重点样本，不能形成内容性结论。")
        if context.data_limitations:
            lines.append(f"数据边界：{'；'.join(context.data_limitations)}。")
        return self._paragraphs(lines)


class GroundedKeywordsRule(EvidenceGeneratorBase):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        samples = self._samples(context)
        query_keywords = "、".join(context.query_keywords) or "未单独记录"
        extracted = [word for word in context.top_keywords if word not in context.query_keywords]
        keywords = "、".join(extracted[:8]) or "未提取到其他稳定高频词"
        lines = [
            f"本次任务关键词为：{query_keywords}；样本中自动提取的高频词为：{keywords}。"
            "自动提取结果用于辅助浏览，不直接代表事件定性。"
        ]
        themes = self._themes(samples)
        if themes:
            lines.append("按重点样本内容，可归纳出以下关注点：")
            for index, theme in enumerate(themes[:4], 1):
                words = "、".join(theme["keywords"])
                lines.append(
                    f"{index}. {theme['name']}：样本中出现“{words}”等表述"
                    f"{self._refs(theme['refs'])}。"
                )
        else:
            lines.append("重点样本未形成可稳定归类的具体关注点，建议逐条打开原链接复核。")
        return self._paragraphs(lines)


class GroundedBackgroundRule(EvidenceGeneratorBase):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        samples = self._samples(context)
        timed = [sample for sample in samples if self._has_confirmed_time(sample)]
        timed.sort(key=lambda sample: str(sample.get("pub_time") or ""))
        lines = [
            (
                f"本次{context.total_posts}条采集记录中，"
                f"{context.confirmed_time_count}条具有可用于排序的发布时间。"
                "以下传播背景仅复述采集页面的发布信息，不对页面所述事实作独立确认。"
            )
        ]
        if timed:
            for index, sample in enumerate(timed[:5], 1):
                lines.append(f"{index}. {self._sample_statement(sample, include_time=True)}。")
        else:
            lines.append("没有具有可靠发布时间的重点样本，因此不生成事件先后顺序。")

        untimed_refs = [
            str(sample.get("reference_id"))
            for sample in samples
            if not self._has_confirmed_time(sample)
        ]
        if untimed_refs:
            lines.append(
                f"其余重点样本因缺少可靠发布时间，不纳入时间先后判断"
                f"{self._refs(untimed_refs[:4])}。"
            )
        if not any(sample.get("source_group") == "stable" for sample in samples):
            lines.append(
                "本次采集范围未包含政府官网样本。涉及事件结果、人物身份与经历、机构关系、"
                "时间和数量等可核查事实时，不能仅依据当前社交平台样本形成正式判断。"
            )
        return self._paragraphs(lines)


class GroundedAnalysisRule(EvidenceGeneratorBase):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        samples = self._samples(context)
        themes = self._themes(samples)
        lines = [
            (
                f"样本覆盖结构为：{self._platform_distribution(context)}。"
                "该分布反映本次采集任务的结果构成，不代表全网内容的真实占比。"
            )
        ]
        if context.content_category_dist:
            review_basis = (
                f"其中{context.human_reviewed_count}条已经人工确认"
                if context.human_reviewed_count
                else "当前均为机器初步分类"
            )
            lines.append(
                f"内容分类结果为：{self._content_categories(context)}；{review_basis}。"
                "分类用于辅助整理，不等同于事实定性。"
            )
        if themes:
            lines.append("从重点样本可直接观察到的主要观点为：")
            sample_by_ref = {
                str(sample.get("reference_id")): sample
                for sample in samples
            }
            for index, theme in enumerate(themes[:4], 1):
                words = "、".join(theme["keywords"])
                lines.append(
                    f"{index}. {theme['name']}：样本中出现“{words}”等相关表述"
                    f"{self._refs(theme['refs'])}。"
                )
            lines.append(
                "以上仅为当前样本中的观点归纳，其事实性、代表性和上下文仍需结合原文及可靠来源人工判断。"
            )

            representative_refs = self._unique(
                ref
                for theme in themes[:4]
                for ref in theme["refs"]
                if ref in sample_by_ref
            )[:5]
            if representative_refs:
                lines.append("代表内容线索（每条仅列一次）：")
                lines.extend(
                    f"{index}. {self._sample_statement(sample_by_ref[ref])}。"
                    for index, ref in enumerate(representative_refs, 1)
                )
        else:
            lines.append("重点样本不足以提炼稳定内容线索，不作风险定性。")
        lines.append(
            f"情感分析程序给出的参考标签为：{self._sentiment(context)}。"
            "统计优先采用已经人工确认的逐条标签；未人工修改部分仍使用机器初判。"
            "机器结果可能受标题措辞、反讽、转述和平台语境影响，"
            "只能作为筛选线索，不能据此推断公众总体态度。"
        )
        if context.data_limitations:
            lines.append(f"影响结论可靠性的限制包括：{'；'.join(context.data_limitations)}。")
        return self._paragraphs(lines)


class GroundedRecommendationsRule(EvidenceGeneratorBase):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        samples = self._samples(context)
        themes = {theme["name"]: theme for theme in self._themes(samples)}
        actions = []

        def add_action(label: str, text: str, theme_names: Iterable[str]):
            refs = []
            for name in theme_names:
                refs.extend(themes.get(name, {}).get("refs", []))
            if refs:
                actions.append(f"{label}：{text}{self._refs(self._unique(refs)[:4])}。")

        add_action(
            "核实核心事实与进展",
            "把样本中的事件结果、发生时间和进展与相关机构公开信息逐项比对，未取得权威依据前标为待核实",
            ("核心事实与进展", "预警与权威信息"),
        )
        add_action(
            "复核专业解释",
            "对研究、原理、数据和专业术语另找可靠机构或专业材料核对，避免把平台科普直接写成事实结论",
            ("专业解释与背景",),
        )
        add_action(
            "核实人物和机构信息",
            "对人物身份、教育经历、任职经历及机构关系逐项核对权威履历，不根据评论推断归属或贡献",
            ("人物经历与机构关联",),
        )
        add_action(
            "区分事实与观点",
            "把祝贺、质疑、争议和评价类表达标为平台观点，保留原文语境，不改写成已经证实的事实",
            ("公众态度与评价", "风险与待核查信息"),
        )
        add_action(
            "核实公共安全和服务状态",
            "对人员安全、灾害影响、交通和公共服务信息分别比对属地部门或运营单位公开信息",
            ("公共安全与现场影响", "交通与公共服务"),
        )

        if not actions and samples:
            refs = [str(sample.get("reference_id")) for sample in samples[:3]]
            actions.append(
                "逐条内容复核：打开原始链接核对正文、发布主体和发布时间，"
                f"在无法交叉验证前不作事件定性{self._refs(refs)}。"
            )
        elif not actions:
            actions.append("当前没有可回溯样本，应先补充采集和人工审核，再形成工作建议。")

        lines = ["建议按以下顺序处理，本节是基于当前样本形成的工作清单，不代表已经采取相关措施："]
        lines.extend(f"{index}. {action}" for index, action in enumerate(actions, 1))
        lines.append(
            "报告提交前，应点击文末来源链接复核被引用样本；无法从采集内容或权威来源确认的信息应删除或标注“待核实”。"
        )
        return self._paragraphs(lines)


EVIDENCE_GENERATOR_REGISTRY = {
    "GroundedSummaryRule": GroundedSummaryRule,
    "GroundedKeywordsRule": GroundedKeywordsRule,
    "GroundedBackgroundRule": GroundedBackgroundRule,
    "GroundedAnalysisRule": GroundedAnalysisRule,
    "GroundedRecommendationsRule": GroundedRecommendationsRule,
}
