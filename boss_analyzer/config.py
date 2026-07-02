LEGITIMACY_WEIGHTS = {
    "registration": 0.25,
    "business_status": 0.20,
    "company_age": 0.15,
    "registered_capital": 0.10,
    "insurance_match": 0.15,
    "online_presence": 0.15,
}

FRESHNESS_WEIGHTS = {
    "hr_activity": 0.25,
    "update_frequency": 0.20,
    "description_quality": 0.20,
    "salary_rationality": 0.15,
    "job_count_rationality": 0.10,
    "duplicate_detection": 0.10,
}

FITNESS_WEIGHTS = {
    "experience_match": 0.25,
    "skill_match": 0.30,
    "education_match": 0.15,
    "salary_match": 0.30,
}

COMPANY_SCALE_MAP = {
    "0-20人": (0, 20),
    "20-99人": (20, 99),
    "100-499人": (100, 499),
    "500-999人": (500, 999),
    "1000-9999人": (1000, 9999),
    "10000人以上": (10000, 100000),
}

EDUCATION_LEVELS = {
    "初中及以下": 1,
    "中专/中技": 2,
    "高中": 3,
    "大专": 4,
    "本科": 5,
    "硕士": 6,
    "博士": 7,
}

RISK_KEYWORDS = [
    "传销", "刷单", "兼职日结", "押金", "培训费", "保证金",
    "高薪日结", "轻松月入", "躺赚", "零投入",
]

REQUEST_TIMEOUT = 15
MAX_JOBS_TO_SCRAPE = 10
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 5.0

REPORT_OUTPUT_DIR = "./reports"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]
