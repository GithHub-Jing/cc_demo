from dataclasses import dataclass, field
from statistics import median
from typing import Optional

from boss_analyzer.models.job import UserProfile
from boss_analyzer.models.ranking import JobMatch
from boss_analyzer.utils.helpers import text_similarity


@dataclass
class SalaryBand:
    label: str
    count: int
    salary_min: int
    salary_max: int
    avg_midpoint: float


@dataclass
class CareerAdvice:
    total_jobs: int
    salary_jobs: int
    ignored_salary_jobs: int = 0
    salary_p25: int = 0
    salary_median: int = 0
    salary_p75: int = 0
    recommended_salary_min: int = 0
    recommended_salary_max: int = 0
    level_label: str = "数据不足"
    target_fit_count: int = 0
    salary_bands: list[SalaryBand] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    gap_keywords: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def advise_career(matches: list[JobMatch], profile: Optional[UserProfile] = None) -> CareerAdvice:
    advice = CareerAdvice(total_jobs=len(matches), salary_jobs=0)
    raw_salary_matches = [m for m in matches if m.job.salary_min > 0 and m.job.salary_max > 0]
    salary_matches = _filter_salary_outliers(raw_salary_matches)
    advice.salary_jobs = len(salary_matches)
    advice.ignored_salary_jobs = len(raw_salary_matches) - len(salary_matches)
    if not matches:
        advice.suggestions.append("先扩大岗位关键词或城市范围，拿到足够样本后再判断薪资。")
        return advice

    if salary_matches:
        midpoints = sorted(_salary_midpoint(m) for m in salary_matches)
        advice.salary_p25 = _percentile(midpoints, 25)
        advice.salary_median = int(round(median(midpoints)))
        advice.salary_p75 = _percentile(midpoints, 75)
        advice.salary_bands = _build_salary_bands(salary_matches)

    advice.level_label = _infer_level(matches, profile)
    advice.matched_keywords, advice.gap_keywords = _keyword_fit(matches, profile)
    advice.recommended_salary_min, advice.recommended_salary_max = _recommended_salary(
        advice=advice,
        profile=profile,
    )
    advice.target_fit_count = _count_target_fits(matches, advice, profile)
    advice.suggestions = _build_suggestions(advice, profile)
    return advice


def _salary_midpoint(match: JobMatch) -> float:
    return (match.job.salary_min + match.job.salary_max) / 2


def _filter_salary_outliers(matches: list[JobMatch]) -> list[JobMatch]:
    plausible = [
        m for m in matches
        if m.job.salary_min > 0
        and m.job.salary_max > 0
        and m.job.salary_min <= m.job.salary_max
        and m.job.salary_max <= 100
    ]
    if len(plausible) < 4:
        return plausible

    midpoints = sorted(_salary_midpoint(m) for m in plausible)
    middle = median(midpoints)
    threshold = max(80, middle * 3)
    return [m for m in plausible if _salary_midpoint(m) <= threshold]


def _percentile(values: list[float], percent: int) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return int(round(values[0]))
    index = (len(values) - 1) * percent / 100
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    ratio = index - lower
    value = values[lower] * (1 - ratio) + values[upper] * ratio
    return int(round(value))


def _build_salary_bands(matches: list[JobMatch]) -> list[SalaryBand]:
    buckets = [
        ("入门档", 0, 15),
        ("主流档", 15, 25),
        ("进阶档", 25, 40),
        ("高薪档", 40, 10_000),
    ]
    result = []
    for label, low, high in buckets:
        bucket = [m for m in matches if low <= _salary_midpoint(m) < high]
        if not bucket:
            continue
        result.append(SalaryBand(
            label=label,
            count=len(bucket),
            salary_min=min(m.job.salary_min for m in bucket),
            salary_max=max(m.job.salary_max for m in bucket),
            avg_midpoint=round(sum(_salary_midpoint(m) for m in bucket) / len(bucket), 1),
        ))
    return result


def _infer_level(matches: list[JobMatch], profile: Optional[UserProfile]) -> str:
    if profile and profile.experience_years:
        years = profile.experience_years
    else:
        experience_values = [
            m.job.experience_min
            for m in matches
            if m.job.experience_min > 0 and m.job.experience_min < 99
        ]
        if not experience_values:
            return "数据不足"
        years = int(round(median(experience_values)))

    if years < 2:
        return "初级/助理"
    if years < 5:
        return "中级/独立贡献者"
    if years < 8:
        return "高级/核心骨干"
    return "专家/负责人"


def _keyword_fit(matches: list[JobMatch], profile: Optional[UserProfile]) -> tuple[list[str], list[str]]:
    required = []
    for match in matches:
        required.extend(match.job.skills)
    required_counts = {}
    for skill in required:
        normalized = " ".join(str(skill or "").strip().split())
        if normalized:
            required_counts[normalized] = required_counts.get(normalized, 0) + 1

    top_required = [
        skill for skill, _ in sorted(required_counts.items(), key=lambda item: item[1], reverse=True)[:12]
    ]
    if not profile or not profile.skills:
        return [], top_required[:8]

    matched = []
    gaps = []
    for skill in top_required:
        if any(text_similarity(skill.lower(), owned.lower()) > 0.6 for owned in profile.skills):
            matched.append(skill)
        else:
            gaps.append(skill)
    return matched[:8], gaps[:8]


def _recommended_salary(advice: CareerAdvice, profile: Optional[UserProfile]) -> tuple[int, int]:
    if not advice.salary_jobs:
        return 0, 0

    low = advice.salary_median
    high = advice.salary_p75
    if profile and profile.expected_salary_min:
        low = max(low, profile.expected_salary_min)
    if profile and profile.expected_salary_max:
        high = max(low, min(max(advice.salary_p75, profile.expected_salary_min), profile.expected_salary_max))
    elif high < low:
        high = low
    return int(low), int(high)


def _count_target_fits(matches: list[JobMatch], advice: CareerAdvice, profile: Optional[UserProfile]) -> int:
    if not advice.recommended_salary_min:
        return 0
    count = 0
    for match in matches:
        job = match.job
        salary_ok = job.salary_max >= advice.recommended_salary_min if job.salary_max else False
        exp_ok = True
        if profile and profile.experience_years:
            exp_ok = job.experience_min <= profile.experience_years <= job.experience_max
        if salary_ok and exp_ok:
            count += 1
    return count


def _build_suggestions(advice: CareerAdvice, profile: Optional[UserProfile]) -> list[str]:
    suggestions = []
    if advice.salary_jobs < max(3, advice.total_jobs // 3):
        suggestions.append("可增加样本量或换相邻关键词，当前公开薪资样本偏少。")
    if advice.recommended_salary_min:
        suggestions.append(
            f"优先投递薪资上限不低于 {advice.recommended_salary_min}K 的岗位，谈薪锚点放在 "
            f"{advice.recommended_salary_min}-{advice.recommended_salary_max}K。"
        )
    if profile and profile.expected_salary_min and advice.salary_p75 and profile.expected_salary_min > advice.salary_p75:
        suggestions.append("当前期望薪资高于市场 P75，建议补充更高阶关键词或放宽城市/行业范围验证。")
    if advice.gap_keywords:
        suggestions.append(f"简历和搜索词可重点补强: {'、'.join(advice.gap_keywords[:5])}。")
    if advice.target_fit_count:
        suggestions.append(f"本次有 {advice.target_fit_count} 个岗位同时满足薪资下限和经验匹配，可优先查看排名靠前项。")
    if not suggestions:
        suggestions.append("当前结果可作为跳槽参考，建议结合岗位描述和公司活跃度继续筛选。")
    return suggestions
