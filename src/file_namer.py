from datetime import datetime
from typing import Optional
import os


def generate_filename(
    region: Optional[str] = None,
    time_range: Optional[str] = None,
    template_name: Optional[str] = None,
    is_same_region_time: bool = False,
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    event_keyword: Optional[str] = None,
) -> str:
    """
    生成文件命名

    命名规则：{地域}{核心事件}舆情通报_{日期}

    格式示例：湖北省武汉市交通事故舆情通报_20240628.docx
    """
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")

    region_part = region if region else "全国"

    GENERIC_KEYWORDS = {"舆情", "警情通报", "通报", "事件", "相关事件", "案件", ""}
    
    if event_keyword and event_keyword not in GENERIC_KEYWORDS:
        keyword_part = event_keyword
        if keyword_part.endswith("通报"):
            keyword_part = keyword_part[:-2]
        if keyword_part.endswith("舆情"):
            keyword_part = keyword_part[:-2]
        base_name = f"{region_part}{keyword_part}舆情通报"
    else:
        base_name = f"{region_part}舆情通报"

    parts = [base_name, date_str]
    return "_".join(parts) + ".docx"


def ensure_unique_path(directory: str, filename: str) -> str:
    """
    确保文件路径唯一，如果已存在则追加序号
    """
    base, ext = os.path.splitext(filename)
    counter = 1
    result = os.path.join(directory, filename)

    while os.path.exists(result):
        result = os.path.join(directory, f"{base}_{counter}{ext}")
        counter += 1

    return result
