import re
import random
import time
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from boss_analyzer.config import EDUCATION_LEVELS, RISK_KEYWORDS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, FAST_DELAY_MIN, FAST_DELAY_MAX

logger = logging.getLogger("boss_analyzer")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def random_delay():
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    time.sleep(delay)


def fast_random_delay():
    delay = random.uniform(FAST_DELAY_MIN, FAST_DELAY_MAX)
    time.sleep(delay)


def parse_salary(salary_str: str) -> tuple[int, int]:
    salary_str = str(salary_str or "").strip()
    if not salary_str or "面议" in salary_str:
        return 0, 0
    if re.search(r"(元\s*)?/+\s*(天|日|时|小时)", salary_str):
        return 0, 0

    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~·]\s*(\d+(?:\.\d+)?)\s*([Kk千万])?", salary_str)
    if not m:
        return 0, 0

    low, high = float(m.group(1)), float(m.group(2))
    unit = m.group(3) or ""
    if unit in ["K", "k", "千"]:
        pass
    elif unit == "万":
        low, high = low * 10, high * 10
    elif "元" in salary_str:
        return 0, 0

    if "年" in salary_str and "万" in salary_str:
        low, high = low / 12, high / 12
    if high <= 0 or low <= 0 or low > high:
        return 0, 0
    return int(round(low)), int(round(high))


def parse_experience(exp_str: str) -> tuple[int, int]:
    if "经验不限" in exp_str or "不限" in exp_str:
        return 0, 99
    m = re.search(r"(\d+)\s*[-~·]\s*(\d+)", exp_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*年以上", exp_str)
    if m:
        return int(m.group(1)), 99
    m = re.search(r"(\d+)\s*年以下", exp_str)
    if m:
        return 0, int(m.group(1))
    return 0, 99


def parse_capital(capital_str: str) -> float:
    if not capital_str:
        return 0
    m = re.search(r"([\d.]+)\s*(万|亿)", capital_str)
    if m:
        val = float(m.group(1))
        if m.group(2) == "亿":
            val *= 10000
        return val
    m = re.search(r"([\d.]+)", capital_str)
    if m:
        return float(m.group(1)) / 10000
    return 0


def education_level(edu_str: str) -> int:
    for key, val in EDUCATION_LEVELS.items():
        if key in edu_str:
            return val
    return 0


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def check_risk_keywords(text: str) -> list[str]:
    return [kw for kw in RISK_KEYWORDS if kw in text]


def parse_active_time(time_str: str) -> int:
    if not time_str:
        return 999
    if "刚刚" in time_str or "在线" in time_str:
        return 0
    m = re.search(r"(\d+)\s*分钟", time_str)
    if m:
        return 0
    m = re.search(r"(\d+)\s*小时", time_str)
    if m:
        return 0
    if "今日" in time_str or "今天" in time_str:
        return 0
    if "昨日" in time_str or "昨天" in time_str:
        return 1
    m = re.search(r"(\d+)\s*日", time_str)
    if m:
        return int(m.group(1))
    if "本周" in time_str:
        return 3
    if "本月" in time_str:
        return 15
    m = re.search(r"(\d+)\s*周", time_str)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r"(\d+)\s*月", time_str)
    if m:
        return int(m.group(1)) * 30
    return 999


def calculate_company_age(founded_str: str) -> float:
    if not founded_str:
        return 0
    m = re.search(r"(\d{4})", founded_str)
    if m:
        year = int(m.group(1))
        return max(0, datetime.now().year - year + (datetime.now().month / 12))
    return 0


def clamp(value: float, min_val: float = 0, max_val: float = 100) -> float:
    return max(min_val, min(max_val, value))
