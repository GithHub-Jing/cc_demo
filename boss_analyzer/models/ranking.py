from dataclasses import dataclass
from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job


@dataclass
class JobMatch:
    company: Company
    job: Job
    fitness_score: float = 0.0
    legitimacy_score: float = 0.0
    freshness_score: float = 0.0
    rank: int = 0

    @property
    def overall_score(self) -> float:
        scores, weights = [], []
        if self.fitness_score:
            scores.append(self.fitness_score)
            weights.append(0.6)
        if self.legitimacy_score:
            scores.append(self.legitimacy_score)
            weights.append(0.25)
        if self.freshness_score:
            scores.append(self.freshness_score)
            weights.append(0.15)
        if not scores:
            return 0.0
        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)

    @property
    def match_level(self) -> str:
        s = self.overall_score
        if s >= 80:
            return "强烈推荐"
        if s >= 65:
            return "推荐"
        if s >= 50:
            return "一般"
        return "不推荐"

    @property
    def match_color(self) -> str:
        return {
            "强烈推荐": "#22c55e",
            "推荐": "#3b82f6",
            "一般": "#f59e0b",
            "不推荐": "#ef4444",
        }.get(self.match_level, "#6b7280")
