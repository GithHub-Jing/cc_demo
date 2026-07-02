from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubScore:
    name: str
    score: float
    weight: float
    detail: str = ""
    risk_level: str = ""


@dataclass
class DimensionResult:
    name: str
    score: float
    sub_scores: list[SubScore] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def risk_level(self) -> str:
        if self.score >= 80:
            return "安全"
        elif self.score >= 60:
            return "注意"
        elif self.score >= 40:
            return "警告"
        return "危险"

    @property
    def risk_color(self) -> str:
        colors = {"安全": "#22c55e", "注意": "#f59e0b", "警告": "#f97316", "危险": "#ef4444"}
        return colors.get(self.risk_level, "#6b7280")


@dataclass
class AnalysisReport:
    company_name: str
    legitimacy: Optional[DimensionResult] = None
    freshness: Optional[DimensionResult] = None
    fitness: Optional[DimensionResult] = None
    generated_at: str = ""

    @property
    def overall_score(self) -> float:
        scores = []
        weights = []
        if self.legitimacy:
            scores.append(self.legitimacy.score)
            weights.append(0.4)
        if self.freshness:
            scores.append(self.freshness.score)
            weights.append(0.35)
        if self.fitness:
            scores.append(self.fitness.score)
            weights.append(0.25)
        if not scores:
            return 0
        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)

    @property
    def overall_risk_level(self) -> str:
        s = self.overall_score
        if s >= 80:
            return "安全"
        elif s >= 60:
            return "注意"
        elif s >= 40:
            return "警告"
        return "危险"

    @property
    def all_risks(self) -> list[str]:
        risks = []
        for dim in [self.legitimacy, self.freshness, self.fitness]:
            if dim:
                risks.extend(dim.risks)
        return risks
