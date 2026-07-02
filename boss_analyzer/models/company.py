from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    name: str
    full_name: str = ""
    industry: str = ""
    scale: str = ""
    stage: str = ""
    founded_date: str = ""
    legal_representative: str = ""
    registered_capital: str = ""
    registered_address: str = ""
    business_status: str = ""
    website: str = ""
    description: str = ""
    boss_url: str = ""
    social_insurance_count: Optional[int] = None
    tags: list[str] = field(default_factory=list)

    # 天眼查补充字段
    tianyancha_verified: bool = False
    penalties: int = 0
    lawsuits: int = 0
    risk_count: int = 0
    actual_capital: str = ""

    # 搜索引擎补充字段
    has_official_website: bool = False
    multi_platform_presence: bool = False
    news_count: int = 0
    search_result_count: int = 0
