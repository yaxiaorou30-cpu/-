from src.models import AnalysisContext, SectionConfig
from src.generators.base import BaseGenerator


class OverviewRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        time_str = ""
        if start and end:
            time_str = f"{start.strftime('%Y年%m月%d日%H:%M')}至{end.strftime('%Y年%m月%d日%H:%M')}"
        platform_str = "、".join([f"{k}({v}条)" for k, v in context.platform_dist.items()])
        keywords_str = "、".join(context.top_keywords[:5])

        text = (
            f"近期，关于{context.event_keyword}的舆情信息引发社会关注。"
            f"据统计，监测时段内（{time_str}）共采集到相关舆情信息{context.total_posts}条，"
            f"主要分布于{platform_str}。"
            f"高频关键词包括：{keywords_str}。"
            f"整体热度指数为{context.heat_index}，舆情总体呈{'上升趋势' if context.heat_index > 70 else '平稳态势'}，"
            f"需持续关注后续发展。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class CaseInvestigationRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        events_str = "；".join(context.key_events[:3]) if context.key_events else "事件正在调查中"
        risks_str = "、".join(context.risk_points[:3]) if context.risk_points else "暂无明确风险"

        text = (
            f"关于{context.event_keyword}，目前案件侦办进展情况如下："
            f"一是事件基本情况。{events_str}。"
            f"二是侦办进展。{context.case_progress}。"
            f"三是风险研判。经初步分析，当前存在以下关注重点：{risks_str}。"
            f"下一步，相关部门将继续依法依规推进调查处置工作，并及时向社会通报进展。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class RiskWarningRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        sentiment_desc = "偏负面" if context.sentiment_ratio.get("负面", 0) > 0.3 else "总体平稳"
        risks_str = "、".join(context.risk_points[:3]) if context.risk_points else "需持续关注"

        text = (
            f"当前舆情态势{sentiment_desc}，主要风险点包括：{risks_str}。"
            f"热度指数为{context.heat_index}，{'舆情存在升温风险，建议加强监测和引导' if context.heat_index > 75 else '舆情整体可控'}。"
            f"下一步工作建议：一是持续跟踪舆情动态，及时发现新情况；"
            f"二是加强权威信息发布，回应公众关切；"
            f"三是做好风险预案，防止舆情发酵升级。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class AppendixRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        urls = context.top_urls[:5]
        if not urls:
            return "附件：相关舆情链接（暂无）"
        lines = "\n".join([f"{i + 1}. {url}" for i, url in enumerate(urls)])
        return f"附件：热度较高的相关舆情链接\n{lines}"


class EventBackgroundRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        time_str = ""
        if start and end:
            time_str = f"{start.strftime('%Y年%m月%d日')}"
        keywords_str = "、".join(context.top_keywords[:5])
        platform_str = "、".join(context.platform_dist.keys())

        text = (
            f"{time_str}起，关于{context.event_keyword}的信息在{platform_str}等平台传播，"
            f"引发网民广泛关注。本次事件涉及的主要话题包括：{keywords_str}。"
            f"截至目前，共监测到相关信息{context.total_posts}条，"
            f"舆情整体呈现{'持续发酵' if context.heat_index > 70 else '平稳发展'}态势。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class PublicReactionRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        pos = context.sentiment_ratio.get("正面", 0)
        neg = context.sentiment_ratio.get("负面", 0)
        neu = context.sentiment_ratio.get("中性", 0)

        opinions_str = "；".join(context.netizen_opinions[:3]) if context.netizen_opinions else "观点多元"
        official_str = "；".join(context.official_responses[:2]) if context.official_responses else "暂无官方回应"

        text = (
            f"从情感分布看，正面占比{pos:.0%}，中性占比{neu:.0%}，负面占比{neg:.0%}。"
            f"网民主要观点包括：{opinions_str}。"
            f"官方层面，{official_str}。"
            f"总体来看，公众对事件关注度较高，{'部分网民存在疑虑，建议加强沟通' if neg > 0.2 else '舆论整体理性有序'}。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class ConclusionRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        text = (
            f"综上所述，关于{context.event_keyword}的舆情目前{'整体可控' if context.heat_index < 70 else '仍需高度关注'}。"
            f"建议相关部门继续保持监测，及时回应社会关切，"
            f"做好信息发布和舆论引导工作，确保社会稳定。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class RiskOverviewRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        time_str = ""
        if start and end:
            time_str = f"{start.strftime('%Y年%m月%d日')}至{end.strftime('%Y年%m月%d日')}"
        pos = context.sentiment_ratio.get("正面", 0)
        neg = context.sentiment_ratio.get("负面", 0)

        text = (
            f"本次研判针对{context.event_keyword}相关舆情。"
            f"监测时段为{time_str}，共采集有效信息{context.total_posts}条，"
            f"整体热度指数{context.heat_index}。"
            f"情感分布方面，正面占比{pos:.0%}，负面占比{neg:.0%}。"
            f"当前舆情{'处于高位运行，风险等级较高' if context.heat_index > 75 else '总体平稳，风险可控'}。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class KeyRiskPointsRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        risks_str = "、".join(context.risk_points[:5]) if context.risk_points else "有待进一步分析"
        keywords_str = "、".join(context.top_keywords[:5])

        text = (
            f"经过分析，当前主要风险点包括：{risks_str}。"
            f"核心舆情关键词为：{keywords_str}。"
            f"其中，{'负面情绪较为突出，存在舆情发酵风险' if context.sentiment_ratio.get('负面', 0) > 0.3 else '公众情绪总体平稳，但需关注后续变化'}。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class TrendAnalysisRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        platform_str = "、".join([f"{k}({v}条)" for k, v in context.platform_dist.items()]) if context.platform_dist else "多个平台"

        if start and end:
            time_str = f"{start.strftime('%Y年%m月%d日')}至{end.strftime('%Y年%m月%d日')}"
        elif start:
            time_str = f"{start.strftime('%Y年%m月%d日')}至今"
        else:
            time_str = "近一段时间"

        heat_val = context.heat_index if context.heat_index else 50

        text = (
            f"从传播渠道看，舆情主要分布于{platform_str}。"
            f"监测时段为{time_str}。"
            f"当前热度指数{heat_val}，{'呈上升趋势，需加强关注' if heat_val > 70 else '保持稳定'}。"
            f"预计未来24-48小时内，舆情{'可能继续发酵，建议做好应对准备' if heat_val > 75 else '将逐步回落，保持监测即可'}。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


class CountermeasuresRule(BaseGenerator):
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        risks_str = "、".join(context.risk_points[:3]) if context.risk_points else ""
        official_str = "；".join(context.official_responses[:2]) if context.official_responses else "尚未发布"

        text = (
            f"针对当前舆情态势，建议采取以下应对措施："
            f"一是加强监测预警。密切关注{risks_str}等重点领域，及时发现苗头性问题。"
            f"二是及时回应关切。当前官方回应情况：{official_str}。建议{'加快信息发布节奏，主动回应热点问题' if not context.official_responses else '继续做好信息发布工作，保持与公众的沟通'}。"
            f"三是做好风险预案。针对可能出现的舆情升级情况，提前制定应对方案。"
            f"四是加强部门协作。建立联动机制，形成工作合力。"
        )
        return self._ensure_word_count(text, section_config.min_words, section_config.max_words)


# ===== 新增：按用户要求格式生成的规则 =====


class EventDescriptionRule(BaseGenerator):
    """事件阐述 - 事件背景描述（包含具体的主事件）"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        if start and end:
            time_str = f"{start.strftime('%Y年%m月%d日')}至{end.strftime('%Y年%m月%d日')}"
        else:
            time_str = "近期"

        platform_str = "、".join(list(context.platform_dist.keys())[:5]) if context.platform_dist else "多个网络平台"

        has_fact = context.case_location or context.case_type or context.injury_count

        if has_fact:
            type_str = context.case_type if context.case_type else "事件"
            location_str = f"{context.case_location}发生一起{type_str}" if context.case_location else f"发生一起{type_str}"
            injury_str = f"，造成{context.injury_count}" if context.injury_count else ""
            
            text = (
                f"{location_str}{injury_str}，相关信息在{platform_str}等网络平台迅速传播，引发广泛关注。\n\n"
                f"监测时段内（{time_str}），共采集到相关舆情信息{context.total_posts}条，"
                f"舆情热度指数达到{context.heat_index}（满值100，低于30属平稳区间），{'呈现快速上升趋势' if context.heat_index > 70 else '整体趋于平稳'}。\n\n"
                f"根据官方通报：{context.main_event[:150] if context.main_event else '案件基本情况正在核查中'}。"
            )
        else:
            text = (
                f"【待案件信息披露后补充】\n\n"
                f"{time_str}，{context.event_keyword}相关舆情在网络平台引发关注。"
                f"案件基本情况正在核查中，相关部门将依法依规开展调查工作。"
                f"监测时段内，共采集到相关舆情信息{context.total_posts}条，"
                f"舆情热度指数达到{context.heat_index}（满值100，低于30属平稳区间）。"
            )

        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class BasicInfoRule(BaseGenerator):
    """基本情况 - 结构化信息"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        if start:
            start_str = start.strftime('%Y年%m月%d日%H:%M')
        else:
            start_str = "监测起始"
        if end:
            end_str = end.strftime('%Y年%m月%d日%H:%M')
        else:
            end_str = "当前"

        platform_items = list(context.platform_dist.items())
        main_platforms = platform_items[:5]
        other_count = sum(v for _, v in platform_items[5:]) if len(platform_items) > 5 else 0

        platform_parts = [f"{k}({v}条)" for k, v in main_platforms]
        if other_count > 0:
            platform_parts.append(f"其他({other_count}条)")
        platform_str = "、".join(platform_parts)

        keywords_str = "、".join(context.top_keywords[:5])

        location_str = f"事发地点：{context.case_location}。\n" if context.case_location else ""
        type_str = f"事件类型：{context.case_type}。\n" if context.case_type else ""
        injury_str = f"伤亡情况：{context.injury_count}。\n" if context.injury_count else ""

        text = (
            f"监测时间：{start_str}至{end_str}。\n"
            f"{location_str}"
            f"{type_str}"
            f"{injury_str}"
            f"监测范围：{platform_str}。\n"
            f"采集数量：共采集到相关信息{context.total_posts}条。\n"
            f"热度指数：{context.heat_index}（满值100，{'高热度' if context.heat_index > 70 else '中等热度' if context.heat_index > 40 else '低热度'}）。\n"
            f"核心关键词：{keywords_str}。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class RiskAnalysisRule(BaseGenerator):
    """存在风险 - 风险点列表（与情感分析结果对齐）"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        neg_ratio = context.sentiment_ratio.get("负面", 0)
        heat = context.heat_index

        if neg_ratio < 0.1 and heat < 50:
            risks = ["信息真空可能引发的谣言风险", "公众对案件细节的过度猜测", "部分平台信息传播存在滞后，需加强覆盖"]
        elif neg_ratio < 0.2 and heat < 70:
            risks = ["局部负面舆情扩散风险", "信息不对称引发的误解", "个别媒体片面报道风险"]
        else:
            risks = context.risk_points[:5] if context.risk_points else ["舆情发酵风险", "信息传播风险"]

        risk_lines = []
        for i, risk in enumerate(risks, 1):
            risk_lines.append(f"{i}. {risk}。")

        risk_text = "\n".join(risk_lines)

        text = (
            f"经分析研判，当前舆情存在以下风险点：\n{risk_text}\n"
            f"负面舆情占比{neg_ratio:.0%}，{'需重点关注负面情绪传播' if neg_ratio > 0.3 else '公众情绪总体平稳'}。"
            f"综合热度指数{heat}（满值100），{'舆情处于高位运行状态，存在进一步发酵可能' if heat > 75 else '舆情整体可控'}。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class NextStepsRule(BaseGenerator):
    """下一步工作措施 - 措施列表"""
    
    TOPIC_MAPPINGS = {
        "通报": "信息发布",
        "解读": "舆论引导",
        "观察": "舆情研判",
        "事件": "事件处置",
        "案件": "案件侦办",
        "警方": "执法规范",
        "官方": "权威发布",
        "关注": "公众关切",
        "讨论": "舆论热点",
        "疑问": "信息透明度",
        "质疑": "公信力建设",
        "谣言": "谣言治理",
        "进展": "工作进度",
        "调查": "调查取证",
        "安全": "公共安全",
        "交通": "交通管理",
        "医疗": "医疗保障",
        "教育": "教育管理",
        "市场": "市场监管",
        "环保": "环境保护",
    }

    def _map_to_topic(self, text: str) -> str:
        for keyword, topic in self.TOPIC_MAPPINGS.items():
            if keyword in text:
                return topic
        return "重点领域"

    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        risks = context.risk_points[:3] if context.risk_points else ["舆情监测"]
        risk_topics = [self._map_to_topic(r) for r in risks]
        official = context.official_responses[:2] if context.official_responses else []

        measures = [
            "持续加强舆情监测。实时关注各平台动态，及时掌握舆情走向。",
            f"强化信息发布工作。{'当前已发布官方回应' if official else '尽快发布权威信息'}，主动回应公众关切。",
            f"做好风险防控。针对{risk_topics[0]}等重点领域，提前制定应对预案。",
            "加强部门协同联动。建立信息共享机制，形成工作合力。",
            "密切关注后续发展。做好长期跟踪监测，防止舆情反复。",
        ]

        text = "建议采取以下工作措施：\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(measures[:5])])
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class NoticeContentRule(BaseGenerator):
    """情况通报 - 通报正文（使用结构化字段，避免复制main_event全文）"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        has_fact = context.case_location or context.case_type or context.injury_count
        event_title = self._smart_keyword(context.event_keyword, "")
        
        if has_fact:
            location_str = f"事发地点：{context.case_location}。" if context.case_location else ""
            type_str = context.case_type if context.case_type else "案件"
            injury_str = f"造成{context.injury_count}。" if context.injury_count else ""
            progress = context.case_progress if context.case_progress else "调查工作正在有序推进"
            
            event_summary = f"{location_str}{injury_str}事件类型：{type_str}。"
            
            text = (
                f"关于{event_title}，现将有关情况通报如下：\n\n"
                f"一、事件基本情况。{event_summary}\n\n"
                f"二、处置进展。{progress}。\n\n"
                f"三、官方回应。{context.official_responses[0] if context.official_responses else '官方将适时发布权威信息'}。\n\n"
                f"有关部门将继续依法依规开展工作，及时向社会公布进展。请广大网民不信谣、不传谣，以官方通报为准。"
            )
        else:
            text = (
                f"【待案件信息披露后补充】\n\n"
                f"关于{event_title}，有关情况通报如下：\n\n"
                f"一、事件基本情况。案件基本情况正在核查中。\n\n"
                f"二、处置进展。相关部门正在依法开展调查工作。\n\n"
                f"三、官方回应。官方将适时发布权威信息，请以官方通报为准。\n\n"
                f"请广大网民不信谣、不传谣，共同维护良好网络环境。"
            )

        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class CaseBasicInfoRule(BaseGenerator):
    """案件侦办类基本情况"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        if start:
            start_str = start.strftime('%Y年%m月%d日')
        else:
            start_str = "案件发生"

        platform_str = "、".join([f"{k}({v}条)" for k, v in list(context.platform_dist.items())[:4]])
        progress = context.case_progress if context.case_progress else "案件正在侦办中"

        text = (
            f"案件发生时间：{start_str}。\n"
            f"舆情传播范围：{platform_str}。\n"
            f"监测信息总量：{context.total_posts}条。\n"
            f"侦办进展情况：{progress}。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class PoliceNextStepsRule(BaseGenerator):
    """案件侦办类下一步措施"""
    
    TOPIC_MAPPINGS = {
        "通报": "信息发布",
        "解读": "舆论引导",
        "观察": "舆情研判",
        "事件": "事件处置",
        "案件": "案件侦办",
        "警方": "执法规范",
        "官方": "权威发布",
        "关注": "公众关切",
        "讨论": "舆论热点",
        "疑问": "信息透明度",
        "质疑": "公信力建设",
        "谣言": "谣言治理",
        "进展": "工作进度",
        "调查": "调查取证",
        "安全": "公共安全",
        "交通": "交通管理",
        "医疗": "医疗保障",
        "教育": "教育管理",
        "市场": "市场监管",
        "环保": "环境保护",
    }

    def _map_to_topic(self, text: str) -> str:
        for keyword, topic in self.TOPIC_MAPPINGS.items():
            if keyword in text:
                return topic
        return "重点领域"

    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        risks = context.risk_points[:3] if context.risk_points else ["案件侦办"]
        risk_topics = [self._map_to_topic(r) for r in risks]
        progress = context.case_progress if context.case_progress else "案件侦办工作有序推进"

        measures = [
            "加快推进案件侦办。依法依规开展调查取证，确保案件处理公正透明。",
            f"做好舆情监测预警。重点关注{risk_topics[0]}等领域，及时发现异常情况。",
            "适时发布案情通报。在保障案件侦办的前提下，及时回应公众关切。",
            "加强法治宣传教育。引导公众理性看待案件，不信谣、不传谣。",
            "完善应急处置机制。针对可能出现的舆情波动，提前做好应对准备。",
        ]

        text = "下一步工作措施：\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(measures)])
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class PoliceNoticeRule(BaseGenerator):
    """案件侦办类情况通报"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        events = "；".join(context.key_events[:2]) if context.key_events else "案件正在侦办"
        progress = context.case_progress if context.case_progress else "侦办工作正在有序进行"

        text = (
            f"关于{context.event_keyword}案件，现将侦办情况通报如下：\n\n"
            f"一、案件概况。{events}。\n\n"
            f"二、侦办进展。{progress}。\n\n"
            f"公安机关将继续依法开展案件侦办工作，确保案件处理公正合法。"
            f"调查结果将按程序向社会公布，请公众理性关注，以官方发布为准。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class RiskBasicInfoRule(BaseGenerator):
    """风险研判类基本情况"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        start, end = context.time_range
        if start and end:
            time_str = f"{start.strftime('%Y年%m月%d日')}至{end.strftime('%Y年%m月%d日')}"
        else:
            time_str = "监测周期内"

        pos = context.sentiment_ratio.get("正面", 0)
        neg = context.sentiment_ratio.get("负面", 0)
        neu = context.sentiment_ratio.get("中性", 0)

        text = (
            f"研判时间范围：{time_str}。\n"
            f"采集信息总量：{context.total_posts}条。\n"
            f"舆情热度指数：{context.heat_index}（满值100，{'高热' if context.heat_index > 70 else '中热' if context.heat_index > 40 else '低热'}）。\n"
            f"情感分布情况：正面{pos:.0%}、中性{neu:.0%}、负面{neg:.0%}。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class DeepRiskAnalysisRule(BaseGenerator):
    """深度风险研判"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        neg_ratio = context.sentiment_ratio.get("负面", 0)
        heat = context.heat_index

        if neg_ratio < 0.1 and heat < 50:
            risks = ["信息真空可能引发的谣言风险", "公众对案件细节的过度猜测", "部分平台信息传播存在滞后，需加强覆盖"]
        elif neg_ratio < 0.2 and heat < 70:
            risks = ["局部负面舆情扩散风险", "信息不对称引发的误解", "个别媒体片面报道风险"]
        else:
            risks = context.risk_points[:5] if context.risk_points else ["舆情发酵风险"]

        risk_lines = [f"{i+1}. {r}。" for i, r in enumerate(risks)]
        risk_text = "\n".join(risk_lines)

        text = (
            f"经深度研判，当前存在以下风险点：\n{risk_text}\n\n"
            f"风险研判结论：负面舆情占比{neg_ratio:.0%}，热度指数{heat}（满值100）。"
            f"{'舆情处于高风险状态，需立即采取应对措施' if heat > 80 else '舆情风险等级中等，需加强监测' if heat > 50 else '舆情风险可控，保持常规监测'}。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class RiskNextStepsRule(BaseGenerator):
    """风险研判类下一步措施"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        heat = context.heat_index
        neg = context.sentiment_ratio.get("负面", 0)

        urgency = "紧急" if heat > 80 else "重点" if heat > 50 else "常规"

        measures = [
            f"启动{urgency}监测机制。全天候关注舆情动态，确保第一时间发现异常。",
            "强化风险预警。建立预警指标体系，对关键风险点进行实时监测。",
            "制定分级应对预案。针对不同风险等级，准备相应处置方案。",
            f"{'加大正面信息投放力度，主动引导舆论走向' if neg > 0.3 else '持续做好信息公开，保持舆情透明'}。",
            "建立长效机制。总结本次研判经验，完善风险应对体系。",
        ]

        text = "下一步工作措施：\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(measures)])
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


class RiskNoticeRule(BaseGenerator):
    """风险研判类情况通报"""
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        neg_ratio = context.sentiment_ratio.get("负面", 0)
        heat = context.heat_index

        if neg_ratio < 0.1 and heat < 50:
            risks = "信息真空风险、公众猜测风险"
        elif neg_ratio < 0.2 and heat < 70:
            risks = "局部负面扩散风险、信息不对称风险"
        else:
            risks = "、".join(context.risk_points[:3]) if context.risk_points else "相关风险点"

        level = "高" if heat > 80 else "中" if heat > 50 else "低"

        text = (
            f"关于{context.event_keyword}的风险研判情况通报如下：\n\n"
            f"一、研判结论。本次舆情风险等级为{level}级。\n\n"
            f"二、主要风险点。包括：{risks}。\n\n"
            f"三、应对建议。{'建议立即启动应急响应机制' if heat > 80 else '建议加强日常监测预警' if heat > 50 else '建议保持常规监测'}。\n\n"
            f"请相关部门高度重视，按照研判结论落实相应工作措施。"
        )
        return self._clean_text(self._ensure_word_count(text, section_config.min_words, section_config.max_words))


RULE_GENERATOR_REGISTRY = {
    # 旧版规则（保留兼容）
    "OverviewRule": OverviewRule,
    "CaseInvestigationRule": CaseInvestigationRule,
    "RiskWarningRule": RiskWarningRule,
    "AppendixRule": AppendixRule,
    "EventBackgroundRule": EventBackgroundRule,
    "PublicReactionRule": PublicReactionRule,
    "ConclusionRule": ConclusionRule,
    "RiskOverviewRule": RiskOverviewRule,
    "KeyRiskPointsRule": KeyRiskPointsRule,
    "TrendAnalysisRule": TrendAnalysisRule,
    "CountermeasuresRule": CountermeasuresRule,
    # 新版规则（用户要求格式）
    "EventDescriptionRule": EventDescriptionRule,
    "BasicInfoRule": BasicInfoRule,
    "RiskAnalysisRule": RiskAnalysisRule,
    "NextStepsRule": NextStepsRule,
    "NoticeContentRule": NoticeContentRule,
    "CaseBasicInfoRule": CaseBasicInfoRule,
    "PoliceNextStepsRule": PoliceNextStepsRule,
    "PoliceNoticeRule": PoliceNoticeRule,
    "RiskBasicInfoRule": RiskBasicInfoRule,
    "DeepRiskAnalysisRule": DeepRiskAnalysisRule,
    "RiskNextStepsRule": RiskNextStepsRule,
    "RiskNoticeRule": RiskNoticeRule,
}
