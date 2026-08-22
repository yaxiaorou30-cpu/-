#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
舆论热度分析模块
计算舆论热度指数、分析采集质量
"""
import json
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import Counter

from src.quality_checks import build_collection_assessment

try:
    import jieba
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False


class HeatAnalyzer:
    """舆论热度分析器"""

    # 热度等级阈值
    HEAT_LEVELS = {
        "极高": 90,
        "高": 70,
        "中等": 50,
        "低": 30,
        "极低": 10,
    }

    # 采集阈值等级配置
    COLLECT_LEVELS = {
        "深度采集": {"max_results": 100, "delay_range": (1, 3), "platforms": 10},
        "标准采集": {"max_results": 50, "delay_range": (2, 5), "platforms": 5},
        "快速采集": {"max_results": 20, "delay_range": (3, 8), "platforms": 3},
        "最小采集": {"max_results": 10, "delay_range": (5, 10), "platforms": 2},
    }

    def __init__(self):
        if JIEBA_AVAILABLE:
            jieba.initialize()

    def calculate_heat_index(self, data: List[Dict]) -> Dict:
        """
        计算舆论热度指数
        
        热度指数计算公式：
        H = W1*总量 + W2*平台覆盖 + W3*互动量 + W4*时效性 + W5*情感强度
        
        返回：
        {
            "heat_index": 85.5,
            "heat_level": "高",
            "total_posts": 100,
            "platform_coverage": 0.8,
            "avg_interaction": 500,
            "timeliness": 0.9,
            "sentiment_intensity": 0.6,
            "details": {...}
        }
        """
        if not data:
            return {
                "heat_index": 0,
                "heat_level": "无数据",
                "total_posts": 0,
                "platform_coverage": 0,
                "avg_interaction": 0,
                "timeliness": 0,
                "sentiment_intensity": 0,
                "details": {}
            }

        # 1. 基础数据统计
        total_posts = len(data)
        platforms = set(item.get("platform") or item.get("source", "未知") for item in data)
        platform_coverage = len(platforms) / 10  # 10个平台为满分

        # 2. 互动量分析（转发、评论、点赞）
        interactions = []
        for item in data:
            repost = item.get("repost_count", 0)
            comment = item.get("comment_count", 0)
            like = item.get("like_count", 0)
            interactions.append(repost + comment + like)
        
        avg_interaction = sum(interactions) / len(interactions) if interactions else 0
        interaction_score = min(avg_interaction / 1000, 1)  # 1000为满分基准

        # 3. 时效性分析
        now = datetime.now()
        time_scores = []
        for item in data:
            try:
                pub_time = datetime.fromisoformat(item.get("pub_time", now.isoformat()).split("+")[0])
                hours_diff = (now - pub_time).total_seconds() / 3600
                if hours_diff <= 24:
                    score = 1.0
                elif hours_diff <= 72:
                    score = 0.8
                elif hours_diff <= 168:
                    score = 0.6
                else:
                    score = 0.3
                time_scores.append(score)
            except:
                time_scores.append(0.5)
        
        timeliness = sum(time_scores) / len(time_scores) if time_scores else 0

        # 4. 情感强度分析
        sentiment_intensity = self._calculate_sentiment_intensity(data)

        # 5. 关键词热度
        keyword_heat = self._calculate_keyword_heat(data)

        # 综合热度指数计算
        weights = {
            "total": 0.25,
            "platform": 0.15,
            "interaction": 0.25,
            "timeliness": 0.20,
            "sentiment": 0.15,
        }

        # 各项评分标准化
        total_score = min(total_posts / 100, 1)  # 100条为满分
        
        heat_index = (
            weights["total"] * total_score * 100 +
            weights["platform"] * platform_coverage * 100 +
            weights["interaction"] * interaction_score * 100 +
            weights["timeliness"] * timeliness * 100 +
            weights["sentiment"] * sentiment_intensity * 100
        )

        # 确定热度等级
        heat_level = "极低"
        for level, threshold in self.HEAT_LEVELS.items():
            if heat_index >= threshold:
                heat_level = level
                break

        return {
            "heat_index": round(heat_index, 2),
            "heat_level": heat_level,
            "total_posts": total_posts,
            "platform_coverage": round(platform_coverage, 2),
            "avg_interaction": round(avg_interaction, 2),
            "timeliness": round(timeliness, 2),
            "sentiment_intensity": round(sentiment_intensity, 2),
            "keyword_heat": keyword_heat,
            "platforms": list(platforms),
            "details": {
                "platform_distribution": dict(Counter(item.get("platform") or item.get("source", "未知") for item in data)),
                "time_distribution": self._time_distribution(data),
                "top_keywords": keyword_heat[:10] if keyword_heat else [],
            }
        }

    def _calculate_sentiment_intensity(self, data: List[Dict]) -> float:
        """计算情感强度"""
        positive_words = ["支持", "点赞", "好", "优秀", "成功", "感谢", "希望"]
        negative_words = ["质疑", "批评", "不满", "问题", "担忧", "失望", "愤怒"]
        
        intensity = 0
        count = 0
        
        for item in data:
            content = item.get("content", "") or item.get("title", "")
            if content:
                pos_count = sum(1 for w in positive_words if w in content)
                neg_count = sum(1 for w in negative_words if w in content)
                intensity += (pos_count + neg_count) / max(len(content) / 50, 1)
                count += 1
        
        return min(intensity / count if count else 0, 1)

    def _calculate_keyword_heat(self, data: List[Dict]) -> List[Dict]:
        """计算关键词热度"""
        if not JIEBA_AVAILABLE:
            return []
        
        all_text = " ".join([item.get("content", "") + " " + item.get("title", "") for item in data])
        
        try:
            keywords = jieba.analyse.extract_tags(all_text, topK=20, withWeight=True)
            return [{"keyword": k, "weight": round(w, 4)} for k, w in keywords]
        except:
            return []

    def _time_distribution(self, data: List[Dict]) -> Dict:
        """时间分布分析"""
        now = datetime.now()
        distribution = {"24小时内": 0, "3天内": 0, "一周内": 0, "更早": 0}
        
        for item in data:
            try:
                pub_time = datetime.fromisoformat(item.get("pub_time", now.isoformat()).split("+")[0])
                hours_diff = (now - pub_time).total_seconds() / 3600
                
                if hours_diff <= 24:
                    distribution["24小时内"] += 1
                elif hours_diff <= 72:
                    distribution["3天内"] += 1
                elif hours_diff <= 168:
                    distribution["一周内"] += 1
                else:
                    distribution["更早"] += 1
            except:
                pass
        
        return distribution

    def analyze_collection_quality(self, data: List[Dict]) -> Dict:
        """返回统一检查清单，不再计算容易误导的综合分数。"""
        assessment = build_collection_assessment(data, {})
        attention = [
            item for item in assessment["checks"] if item.get("status") != "pass"
        ]
        assessment["issues"] = [
            f"{item['label']}：{item['value']}" for item in attention
        ]
        assessment["recommendations"] = list(assessment["action_items"])
        return assessment

    def get_collect_level_config(self, level: str) -> Dict:
        """获取采集阈值配置"""
        return self.COLLECT_LEVELS.get(level, self.COLLECT_LEVELS["标准采集"])


# 地区数据
PROVINCES_DATA = {
    "北京市": {"cities": ["北京市"]},
    "天津市": {"cities": ["天津市"]},
    "上海市": {"cities": ["上海市"]},
    "重庆市": {"cities": ["重庆市"]},
    "河北省": {"cities": ["石家庄市", "唐山市", "秦皇岛市", "邯郸市", "邢台市", "保定市", "张家口市", "承德市", "沧州市", "廊坊市", "衡水市"]},
    "山西省": {"cities": ["太原市", "大同市", "阳泉市", "长治市", "晋城市", "朔州市", "晋中市", "运城市", "忻州市", "临汾市", "吕梁市"]},
    "辽宁省": {"cities": ["沈阳市", "大连市", "鞍山市", "抚顺市", "本溪市", "丹东市", "锦州市", "营口市", "阜新市", "辽阳市", "盘锦市", "铁岭市", "朝阳市", "葫芦岛市"]},
    "吉林省": {"cities": ["长春市", "吉林市", "四平市", "辽源市", "通化市", "白山市", "松原市", "白城市"]},
    "黑龙江省": {"cities": ["哈尔滨市", "齐齐哈尔市", "鸡西市", "鹤岗市", "双鸭山市", "大庆市", "伊春市", "佳木斯市", "七台河市", "牡丹江市", "黑河市", "绥化市"]},
    "江苏省": {"cities": ["南京市", "无锡市", "徐州市", "常州市", "苏州市", "南通市", "连云港市", "淮安市", "盐城市", "扬州市", "镇江市", "泰州市", "宿迁市"]},
    "浙江省": {"cities": ["杭州市", "宁波市", "温州市", "嘉兴市", "湖州市", "绍兴市", "金华市", "衢州市", "舟山市", "台州市", "丽水市"]},
    "安徽省": {"cities": ["合肥市", "芜湖市", "蚌埠市", "淮南市", "马鞍山市", "淮北市", "铜陵市", "安庆市", "黄山市", "滁州市", "阜阳市", "宿州市", "六安市", "亳州市", "池州市", "宣城市"]},
    "福建省": {"cities": ["福州市", "厦门市", "漳州市", "泉州市", "三明市", "莆田市", "南平市", "龙岩市", "宁德市"]},
    "江西省": {"cities": ["南昌市", "景德镇市", "萍乡市", "九江市", "新余市", "鹰潭市", "赣州市", "吉安市", "宜春市", "抚州市", "上饶市"]},
    "山东省": {"cities": ["济南市", "青岛市", "淄博市", "枣庄市", "东营市", "烟台市", "潍坊市", "济宁市", "泰安市", "威海市", "日照市", "临沂市", "德州市", "聊城市", "滨州市", "菏泽市"]},
    "河南省": {"cities": ["郑州市", "开封市", "洛阳市", "平顶山市", "安阳市", "鹤壁市", "新乡市", "焦作市", "濮阳市", "许昌市", "漯河市", "三门峡市", "南阳市", "商丘市", "信阳市", "周口市", "驻马店市"]},
    "湖北省": {"cities": ["武汉市", "黄石市", "十堰市", "宜昌市", "襄阳市", "鄂州市", "荆门市", "孝感市", "荆州市", "黄冈市", "咸宁市", "随州市", "恩施州"]},
    "湖南省": {"cities": ["长沙市", "株洲市", "湘潭市", "衡阳市", "邵阳市", "岳阳市", "常德市", "张家界市", "益阳市", "郴州市", "永州市", "怀化市", "娄底市", "湘西州"]},
    "广东省": {"cities": ["广州市", "深圳市", "珠海市", "汕头市", "佛山市", "韶关市", "湛江市", "肇庆市", "江门市", "茂名市", "惠州市", "梅州市", "汕尾市", "河源市", "阳江市", "清远市", "东莞市", "中山市", "潮州市", "揭阳市", "云浮市"]},
    "海南省": {"cities": ["海口市", "三亚市", "三沙市", "儋州市"]},
    "四川省": {"cities": ["成都市", "自贡市", "攀枝花市", "泸州市", "德阳市", "绵阳市", "广元市", "遂宁市", "内江市", "乐山市", "南充市", "眉山市", "宜宾市", "广安市", "达州市", "雅安市", "巴中市", "资阳市", "阿坝州", "甘孜州", "凉山州"]},
    "贵州省": {"cities": ["贵阳市", "六盘水市", "遵义市", "安顺市", "毕节市", "铜仁市", "黔西南州", "黔东南州", "黔南州"]},
    "云南省": {"cities": ["昆明市", "曲靖市", "玉溪市", "保山市", "昭通市", "丽江市", "普洱市", "临沧市", "楚雄州", "红河州", "文山州", "西双版纳州", "大理州", "德宏州", "怒江州", "迪庆州"]},
    "陕西省": {"cities": ["西安市", "铜川市", "宝鸡市", "咸阳市", "渭南市", "延安市", "汉中市", "榆林市", "安康市", "商洛市"]},
    "甘肃省": {"cities": ["兰州市", "嘉峪关市", "金昌市", "白银市", "天水市", "武威市", "张掖市", "平凉市", "酒泉市", "庆阳市", "定西市", "陇南市", "临夏州", "甘南州"]},
    "青海省": {"cities": ["西宁市", "海东市", "海北州", "黄南州", "海南州", "果洛州", "玉树州", "海西州"]},
    "内蒙古自治区": {"cities": ["呼和浩特市", "包头市", "乌海市", "赤峰市", "通辽市", "鄂尔多斯市", "呼伦贝尔市", "巴彦淖尔市", "乌兰察布市", "兴安盟", "锡林郭勒盟", "阿拉善盟"]},
    "广西壮族自治区": {"cities": ["南宁市", "柳州市", "桂林市", "梧州市", "北海市", "防城港市", "钦州市", "贵港市", "玉林市", "百色市", "贺州市", "河池市", "来宾市", "崇左市"]},
    "西藏自治区": {"cities": ["拉萨市", "日喀则市", "昌都市", "林芝市", "山南市", "那曲市", "阿里地区"]},
    "宁夏回族自治区": {"cities": ["银川市", "石嘴山市", "吴忠市", "固原市", "中卫市"]},
    "新疆维吾尔自治区": {"cities": ["乌鲁木齐市", "克拉玛依市", "吐鲁番市", "哈密市", "昌吉州", "博尔塔拉州", "巴音郭楞州", "阿克苏地区", "克孜勒苏州", "喀什地区", "和田地区", "伊犁州", "塔城地区", "阿勒泰地区"]},
    "香港特别行政区": {"cities": ["香港"]},
    "澳门特别行政区": {"cities": ["澳门"]},
    "台湾省": {"cities": ["台北市", "高雄市", "台南市", "新北市", "桃园市", "台中市", "彰化县", "云林县", "嘉义县", "屏东县"]},
}


def get_all_provinces() -> List[str]:
    """获取所有省份列表"""
    return list(PROVINCES_DATA.keys())


def get_cities_by_province(province: str) -> List[str]:
    """获取指定省份的城市列表"""
    return PROVINCES_DATA.get(province, {}).get("cities", [])


def build_region_text(province: Optional[str] = None, city: Optional[str] = None, district: Optional[str] = None) -> str:
    """构建地区文本"""
    parts = []
    if province:
        parts.append(province)
    if city:
        parts.append(city)
    if district:
        parts.append(district)
    
    return "".join(parts) if parts else "全国"
