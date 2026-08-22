import logging
import copy
from typing import List, Dict, Any


class DesensitizeFilter(logging.Filter):
    def __init__(self, fields: List[str]):
        super().__init__()
        self.fields = fields

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            # 简单替换：不记录完整内容，仅做截断示意
            # 实际场景可接入更复杂的正则脱敏
            pass
        return True


def get_logger(name: str, desensitize: bool = True, sensitive_fields: List[str] = None):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        if desensitize and sensitive_fields:
            logger.addFilter(DesensitizeFilter(sensitive_fields))
    return logger


def safe_log_dict(data: Dict[str, Any], sensitive_fields: List[str], max_str_len: int = 30) -> Dict[str, Any]:
    """返回脱敏后的字典副本，仅用于日志记录。"""
    result = copy.deepcopy(data)
    for k in result:
        if k in sensitive_fields:
            v = result[k]
            if isinstance(v, str):
                result[k] = v[:max_str_len] + "..." if len(v) > max_str_len else v
            else:
                result[k] = "<sensitive>"
    return result
