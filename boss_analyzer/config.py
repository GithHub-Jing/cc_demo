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
FAST_DELAY_MIN = 0.5
FAST_DELAY_MAX = 1.5

REPORT_OUTPUT_DIR = "./reports"
TRACKING_DB_PATH = "./data/boss_tracking.db"
STALE_DAYS = 30

SEARCH_LIMIT = 20

CITY_CODES = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "成都": "101270100",
    "杭州": "101210100",
    "武汉": "101200100",
    "南京": "101190100",
    "西安": "101110100",
    "重庆": "101040100",
    "天津": "101030100",
    "苏州": "101190400",
    "长沙": "101250100",
    "郑州": "101180100",
    "厦门": "101230200",
    "青岛": "101120200",
    "合肥": "101220100",
    "宁波": "101210400",
    "福州": "101230100",
    "南昌": "101240100",
    "济南": "101120100",
    "石家庄": "101090100",
    "太原": "101100100",
    "长春": "101060100",
    "哈尔滨": "101050100",
    "昆明": "101290100",
    "贵阳": "101260100",
    "南宁": "101300100",
    "沈阳": "101070100",
    "大连": "101070200",
    "济南": "101120100",
    "兰州": "101160100",
    "乌鲁木齐": "101130100",
    "海口": "101310100",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]
