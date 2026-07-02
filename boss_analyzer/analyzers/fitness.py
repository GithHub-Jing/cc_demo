from boss_analyzer.models.job import Job, UserProfile
from boss_analyzer.models.report import DimensionResult, SubScore
from boss_analyzer.config import FITNESS_WEIGHTS
from boss_analyzer.utils.helpers import education_level, text_similarity, clamp


def evaluate_fitness_per_job(jobs: list[Job], profile: UserProfile) -> list[tuple[Job, float]]:
    if not jobs or not profile:
        return []
    results = []
    for job in jobs:
        exp = _score_experience(job, profile) * FITNESS_WEIGHTS["experience_match"]
        skill = _score_skills(job, profile) * FITNESS_WEIGHTS["skill_match"]
        edu = _score_education(job, profile) * FITNESS_WEIGHTS["education_match"]
        sal = _score_salary(job, profile) * FITNESS_WEIGHTS["salary_match"]
        score = exp + skill + edu + sal
        results.append((job, round(score, 1)))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def evaluate_fitness(jobs: list[Job], profile: UserProfile) -> DimensionResult:
    if not jobs or not profile:
        return DimensionResult(
            name="岗位贴合度", score=0,
            sub_scores=[SubScore(name="数据不足", score=0, weight=1.0, detail="缺少岗位或用户画像信息")],
            risks=["无法评估岗位贴合度"],
            suggestions=["请提供个人技能、经验等信息以获得贴合度评估"],
        )

    best_scores = {"experience": 0, "skill": 0, "education": 0, "salary": 0}
    best_details = {"experience": "", "skill": "", "education": "", "salary": ""}

    for job in jobs:
        # 经验匹配
        exp_score = _score_experience(job, profile)
        if exp_score > best_scores["experience"]:
            best_scores["experience"] = exp_score
            best_details["experience"] = (
                f"要求 {job.experience_min}-{job.experience_max} 年, "
                f"您有 {profile.experience_years} 年 ({job.title})"
            )

        # 技能匹配
        skill_score = _score_skills(job, profile)
        if skill_score > best_scores["skill"]:
            best_scores["skill"] = skill_score
            matched = [s for s in profile.skills if any(
                text_similarity(s.lower(), js.lower()) > 0.6 for js in job.skills
            )]
            best_details["skill"] = (
                f"匹配 {len(matched)}/{len(job.skills)} 项技能 ({job.title})"
            )

        # 学历匹配
        edu_score = _score_education(job, profile)
        if edu_score > best_scores["education"]:
            best_scores["education"] = edu_score
            best_details["education"] = (
                f"要求 {job.education or '不限'}, 您 {profile.education} ({job.title})"
            )

        # 薪资匹配
        sal_score = _score_salary(job, profile)
        if sal_score > best_scores["salary"]:
            best_scores["salary"] = sal_score
            best_details["salary"] = (
                f"岗位 {job.salary_range_str}, "
                f"期望 {profile.expected_salary_min}-{profile.expected_salary_max}K ({job.title})"
            )

    sub_scores = [
        SubScore(
            name="经验匹配", score=best_scores["experience"],
            weight=FITNESS_WEIGHTS["experience_match"],
            detail=best_details["experience"] or "无匹配数据",
            risk_level=_risk_label(best_scores["experience"]),
        ),
        SubScore(
            name="技能匹配", score=best_scores["skill"],
            weight=FITNESS_WEIGHTS["skill_match"],
            detail=best_details["skill"] or "无匹配数据",
            risk_level=_risk_label(best_scores["skill"]),
        ),
        SubScore(
            name="学历匹配", score=best_scores["education"],
            weight=FITNESS_WEIGHTS["education_match"],
            detail=best_details["education"] or "无匹配数据",
            risk_level=_risk_label(best_scores["education"]),
        ),
        SubScore(
            name="薪资匹配", score=best_scores["salary"],
            weight=FITNESS_WEIGHTS["salary_match"],
            detail=best_details["salary"] or "无匹配数据",
            risk_level=_risk_label(best_scores["salary"]),
        ),
    ]

    total_score = sum(s.score * s.weight for s in sub_scores)

    risks = []
    suggestions = []
    if best_scores["experience"] < 40:
        risks.append("经验要求与您的资历差距较大")
        suggestions.append("考虑积累更多相关经验，或寻找经验要求更低的岗位")
    if best_scores["skill"] < 40:
        risks.append("技能匹配度偏低")
        suggestions.append("建议补充岗位要求的核心技能")
    if best_scores["salary"] < 40:
        risks.append("薪资期望与岗位提供的范围差距较大")
    if best_scores["education"] < 50:
        suggestions.append("学历要求可能偏高，可尝试沟通或关注经验优先的岗位")

    return DimensionResult(
        name="岗位贴合度",
        score=total_score,
        sub_scores=sub_scores,
        risks=risks,
        suggestions=suggestions,
    )


def _score_experience(job: Job, profile: UserProfile) -> float:
    if job.experience_min == 0 and job.experience_max >= 99:
        return 80
    years = profile.experience_years
    if job.experience_min <= years <= job.experience_max:
        return 100
    if years < job.experience_min:
        gap = job.experience_min - years
        return clamp(100 - gap * 20)
    gap = years - job.experience_max
    return clamp(90 - gap * 10)


def _score_skills(job: Job, profile: UserProfile) -> float:
    if not job.skills:
        return 70
    if not profile.skills:
        return 30
    matched = 0
    for js in job.skills:
        for ps in profile.skills:
            if text_similarity(js.lower(), ps.lower()) > 0.6:
                matched += 1
                break
    return clamp(matched / len(job.skills) * 100)


def _score_education(job: Job, profile: UserProfile) -> float:
    if not job.education or "不限" in job.education:
        return 85
    required = education_level(job.education)
    actual = education_level(profile.education)
    if actual >= required:
        return 100
    gap = required - actual
    return clamp(100 - gap * 25)


def _score_salary(job: Job, profile: UserProfile) -> float:
    if job.salary_min == 0 or profile.expected_salary_min == 0:
        return 60
    if job.salary_max >= profile.expected_salary_min:
        if job.salary_min >= profile.expected_salary_min:
            return 100
        return 80
    gap_ratio = (profile.expected_salary_min - job.salary_max) / profile.expected_salary_min
    return clamp(80 - gap_ratio * 200)


def _risk_label(score: float) -> str:
    if score >= 80:
        return "安全"
    if score >= 60:
        return "注意"
    if score >= 40:
        return "警告"
    return "危险"
