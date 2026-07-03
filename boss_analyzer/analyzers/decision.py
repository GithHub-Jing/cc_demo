from typing import Optional

from boss_analyzer.analyzers.fitness import _score_salary, _score_skills
from boss_analyzer.models.decision import DecisionCriteria, JobDecision
from boss_analyzer.models.job import UserProfile
from boss_analyzer.models.ranking import JobMatch
from boss_analyzer.utils.helpers import clamp, text_similarity


UPSKILL_KEYWORDS = {
    "k8s", "kubernetes", "docker", "redis", "mysql", "kafka", "rocketmq",
    "elasticsearch", "微服务", "分布式", "高并发", "go", "golang", "java",
    "python", "php", "ci/cd", "linux", "云原生",
}


def evaluate_decisions(
    matches: list[JobMatch],
    profile: Optional[UserProfile] = None,
    criteria: Optional[DecisionCriteria] = None,
) -> list[JobDecision]:
    criteria = criteria or DecisionCriteria()
    decisions = [
        evaluate_decision(match, profile=profile, criteria=criteria)
        for match in matches
    ]
    decisions.sort(key=lambda item: item.overall_score, reverse=True)
    for index, decision in enumerate(decisions, start=1):
        decision.rank = index
    return decisions


def evaluate_decision(
    match: JobMatch,
    profile: Optional[UserProfile] = None,
    criteria: Optional[DecisionCriteria] = None,
) -> JobDecision:
    criteria = criteria or DecisionCriteria()
    profile = profile or UserProfile()
    job = match.job
    company = match.company

    matched_skills, missing_skills = _skill_sets(job.skills, profile.skills)
    skill_score = _score_skills(job, profile) if profile.skills else (match.fitness_score or 60)
    salary_score = _score_salary(job, profile) if profile.expected_salary_min else 60
    stability_score = _score_stability(match)
    growth_score = _score_growth(job, company, matched_skills, missing_skills, criteria)

    risks = _collect_risks(match, profile, criteria, missing_skills)
    strengths = _collect_strengths(match, profile, matched_skills)
    questions = _default_questions(match, profile, risks)
    hard_risk_count = sum(1 for item in risks if item.startswith("硬风险"))

    overall = (
        skill_score * 0.35
        + salary_score * 0.25
        + stability_score * 0.25
        + growth_score * 0.15
    )
    if hard_risk_count:
        overall -= hard_risk_count * 18
    elif len(risks) >= 3:
        overall -= 8
    overall = round(clamp(overall), 1)

    recommendation, label, action = _recommend(overall, hard_risk_count)
    return JobDecision(
        company=company,
        job=job,
        recommendation=recommendation,
        recommendation_label=label,
        overall_score=overall,
        skill_score=round(skill_score, 1),
        salary_score=round(salary_score, 1),
        stability_score=round(stability_score, 1),
        growth_score=round(growth_score, 1),
        risk_level=_risk_level(overall, hard_risk_count, len(risks)),
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        upskill_skills=_upskill_skills(missing_skills),
        strengths=strengths,
        risks=risks,
        questions=questions,
        action=action,
    )


def _skill_sets(job_skills: list[str], profile_skills: list[str]) -> tuple[list[str], list[str]]:
    matched, missing = [], []
    for job_skill in job_skills:
        if any(text_similarity(job_skill.lower(), skill.lower()) > 0.6 for skill in profile_skills):
            matched.append(job_skill)
        else:
            missing.append(job_skill)
    return _dedupe(matched), _dedupe(missing)


def _score_stability(match: JobMatch) -> float:
    company = match.company
    score = 60
    text = " ".join([company.scale, company.stage, company.business_status, company.description])

    scale_rules = [
        ("10000", 18), ("5000", 15), ("1000", 12), ("500", 10),
        ("100-499", 8), ("100-500", 8), ("50-150", 2), ("0-20", -12),
    ]
    for keyword, delta in scale_rules:
        if keyword in text:
            score += delta
            break

    if any(word in text for word in ["已上市", "D轮", "C轮", "不需要融资", "盈利"]):
        score += 12
    if any(word in text for word in ["未融资", "天使轮", "初创"]):
        score -= 10
    if company.tianyancha_verified or company.has_official_website:
        score += 8
    if company.multi_platform_presence:
        score += 5
    if company.business_status and "存续" not in company.business_status and "开业" not in company.business_status:
        score -= 20
    if company.risk_count:
        score -= min(20, company.risk_count * 2)
    if company.penalties:
        score -= min(15, company.penalties * 5)
    if company.lawsuits:
        score -= min(12, company.lawsuits)
    if match.legitimacy_score:
        score = score * 0.5 + match.legitimacy_score * 0.5
    return clamp(score)


def _score_growth(job, company, matched_skills, missing_skills, criteria: DecisionCriteria) -> float:
    text = " ".join([job.title, job.description, " ".join(job.skills), company.industry, company.description]).lower()
    score = 55 + min(20, len(matched_skills) * 4)
    if any(keyword.lower() in text for keyword in criteria.target_keywords):
        score += 10
    if any(keyword in text for keyword in ["高并发", "分布式", "微服务", "k8s", "kubernetes", "云原生", "支付", "游戏"]):
        score += 12
    if any(keyword in text for keyword in ["维护", "二开", "客服系统", "内部系统"]):
        score -= 10
    score += min(10, len(_upskill_skills(missing_skills)) * 3)
    return clamp(score)


def _collect_risks(match: JobMatch, profile: UserProfile, criteria: DecisionCriteria, missing_skills: list[str]) -> list[str]:
    company, job = match.company, match.job
    text = " ".join([
        company.name, company.full_name, company.industry, company.scale, company.stage,
        company.description, job.title, job.description, job.job_type, " ".join(job.skills),
    ]).lower()
    risks = []

    if profile.expected_salary_min and job.salary_max and job.salary_max < profile.expected_salary_min:
        risks.append("硬风险：薪资上限低于最低期望")
    for keyword in criteria.rejected_keywords:
        if keyword.lower() in text:
            risks.append(f"硬风险：疑似{keyword}")
            break
    if criteria.preferred_cities and job.location:
        if not any(city in job.location for city in criteria.preferred_cities):
            risks.append("城市不在优先范围")
    for keyword in criteria.cautious_keywords:
        if keyword.lower() in text:
            risks.append(f"需要确认：岗位描述出现“{keyword}”")
            break
    if len(missing_skills) >= 4:
        risks.append("技能缺口较多，需要判断是否能短期补齐")
    if company.risk_count and company.risk_count >= 10:
        risks.append("企业风险记录偏多")
    if not job.description and len(job.skills) <= 2:
        risks.append("Boss 岗位信息较少，需补充 JD 后再判断")
    return _dedupe(risks)


def _collect_strengths(match: JobMatch, profile: UserProfile, matched_skills: list[str]) -> list[str]:
    job = match.job
    strengths = []
    if matched_skills:
        strengths.append(f"技能直接匹配：{'、'.join(matched_skills[:5])}")
    if profile.experience_years and job.experience_min <= profile.experience_years:
        strengths.append("工作年限满足岗位下限")
    if profile.expected_salary_min and job.salary_max >= profile.expected_salary_min:
        strengths.append("薪资范围覆盖最低期望")
    if job.salary_min and profile.expected_salary_min and job.salary_min >= profile.expected_salary_min:
        strengths.append("薪资下限已达到期望底线")
    return strengths or ["岗位信息可继续沟通，但当前优势证据不足"]


def _default_questions(match: JobMatch, profile: UserProfile, risks: list[str]) -> list[str]:
    questions = [
        "是否外包、驻场或项目外派？",
        "薪资结构、几薪、绩效比例和试用期折扣是否写入 offer？",
        "团队作息、加班频率和线上值班机制如何？",
        "岗位是新增还是替换，当前团队规模多大？",
    ]
    if profile.expected_salary_min and match.job.salary_min < profile.expected_salary_min <= match.job.salary_max:
        questions.append("薪资能否按期望区间谈到上半段？")
    if any("技能缺口" in risk for risk in risks):
        questions.append("岗位核心技术栈中哪些是入职后必须立即上手的？")
    return questions


def _upskill_skills(skills: list[str]) -> list[str]:
    result = []
    for skill in skills:
        lower = skill.lower()
        if lower in UPSKILL_KEYWORDS or any(keyword in lower for keyword in UPSKILL_KEYWORDS):
            result.append(skill)
    return _dedupe(result[:6])


def _recommend(score: float, hard_risk_count: int) -> tuple[str, str, str]:
    if hard_risk_count:
        return "D", "不建议", "除非硬风险被确认排除，否则不建议投入面试时间"
    if score >= 82:
        return "A", "强烈推荐", "优先沟通，值得针对性准备面试"
    if score >= 68:
        return "B", "可以尝试", "可以推进，作为主力或备选机会"
    if score >= 52:
        return "C", "谨慎", "先补充公司、薪资和作息信息后再决定"
    return "D", "不建议", "投入产出比偏低，不建议优先推进"


def _risk_level(score: float, hard_risk_count: int, risk_count: int) -> str:
    if hard_risk_count or score < 50:
        return "高"
    if risk_count >= 3 or score < 70:
        return "中"
    return "低"


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        normalized = str(item or "").strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result
