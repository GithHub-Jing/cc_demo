from dataclasses import dataclass, field

from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job


@dataclass
class DecisionCriteria:
    preferred_cities: list[str] = field(default_factory=list)
    rejected_keywords: list[str] = field(default_factory=lambda: ["外包", "驻场", "外派"])
    cautious_keywords: list[str] = field(default_factory=lambda: ["996", "大小周", "抗压", "狼性"])
    target_keywords: list[str] = field(default_factory=list)


@dataclass
class JobDecision:
    company: Company
    job: Job
    rank: int = 0
    recommendation: str = "C"
    recommendation_label: str = "谨慎"
    overall_score: float = 0.0
    skill_score: float = 0.0
    salary_score: float = 0.0
    stability_score: float = 0.0
    growth_score: float = 0.0
    risk_level: str = "中"
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    upskill_skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    action: str = "先补充信息后再判断"

