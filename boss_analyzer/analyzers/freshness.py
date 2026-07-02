from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job
from boss_analyzer.models.report import DimensionResult, SubScore
from boss_analyzer.config import FRESHNESS_WEIGHTS
from boss_analyzer.utils.helpers import (
    parse_active_time, check_risk_keywords, text_similarity, clamp,
)


def evaluate_freshness(company: Company, jobs: list[Job]) -> DimensionResult:
    sub_scores = []

    if not jobs:
        return DimensionResult(
            name="招聘真实性", score=30,
            sub_scores=[SubScore(name="数据不足", score=30, weight=1.0, detail="未采集到岗位信息")],
            risks=["未发现任何在招岗位，可能已停止招聘"],
            suggestions=["确认该公司是否仍在招聘"],
        )

    # HR 活跃度
    active_days = [parse_active_time(j.hr_active_time) for j in jobs if j.hr_active_time]
    if active_days:
        min_days = min(active_days)
        if min_days == 0:
            hr_score = 100
        elif min_days <= 1:
            hr_score = 90
        elif min_days <= 3:
            hr_score = 75
        elif min_days <= 7:
            hr_score = 55
        elif min_days <= 30:
            hr_score = 35
        else:
            hr_score = 15
    else:
        hr_score = 40
    sub_scores.append(SubScore(
        name="HR活跃度", score=hr_score,
        weight=FRESHNESS_WEIGHTS["hr_activity"],
        detail=f"最近活跃: {min(active_days) if active_days else '未知'}天前",
        risk_level="安全" if hr_score >= 70 else ("警告" if hr_score < 40 else "注意"),
    ))

    # 岗位更新频率
    publish_count = sum(1 for j in jobs if j.publish_time)
    freq_score = clamp(publish_count / len(jobs) * 100) if jobs else 50
    sub_scores.append(SubScore(
        name="更新频率", score=freq_score,
        weight=FRESHNESS_WEIGHTS["update_frequency"],
        detail=f"{publish_count}/{len(jobs)} 个岗位有发布时间信息",
        risk_level="安全" if freq_score >= 60 else "注意",
    ))

    # JD 描述质量
    desc_scores = []
    for j in jobs:
        desc = j.description
        if not desc:
            desc_scores.append(20)
            continue
        length = len(desc)
        if length >= 300:
            s = 90
        elif length >= 150:
            s = 70
        elif length >= 50:
            s = 50
        else:
            s = 25
        if j.skills:
            s = min(100, s + len(j.skills) * 3)
        risk_words = check_risk_keywords(desc)
        if risk_words:
            s = max(0, s - 30)
        desc_scores.append(s)
    desc_avg = sum(desc_scores) / len(desc_scores) if desc_scores else 40
    sub_scores.append(SubScore(
        name="描述质量", score=desc_avg,
        weight=FRESHNESS_WEIGHTS["description_quality"],
        detail=f"平均 JD 长度 {sum(len(j.description) for j in jobs) // max(len(jobs), 1)} 字",
        risk_level="安全" if desc_avg >= 70 else ("注意" if desc_avg >= 40 else "警告"),
    ))

    # 薪资合理性
    salary_jobs = [j for j in jobs if j.salary_min > 0 and j.salary_max > 0]
    if salary_jobs:
        reasonable = 0
        for j in salary_jobs:
            ratio = j.salary_max / j.salary_min if j.salary_min > 0 else 999
            if 1.0 <= ratio <= 3.0:
                reasonable += 1
        salary_score = clamp(reasonable / len(salary_jobs) * 100)
    else:
        salary_score = 40
    sub_scores.append(SubScore(
        name="薪资合理性", score=salary_score,
        weight=FRESHNESS_WEIGHTS["salary_rationality"],
        detail=f"{len(salary_jobs)} 个岗位有薪资信息",
        risk_level="安全" if salary_score >= 70 else "注意",
    ))

    # 岗位数量合理性
    count = len(jobs)
    if 2 <= count <= 30:
        count_score = 90
    elif count == 1:
        count_score = 60
    elif count <= 50:
        count_score = 70
    else:
        count_score = 40
    sub_scores.append(SubScore(
        name="岗位数量", score=count_score,
        weight=FRESHNESS_WEIGHTS["job_count_rationality"],
        detail=f"共 {count} 个在招岗位",
        risk_level="安全" if count_score >= 70 else "注意",
    ))

    # 重复岗位检测
    titles = [j.title for j in jobs]
    dup_count = 0
    for i in range(len(titles)):
        for k in range(i + 1, len(titles)):
            if text_similarity(titles[i], titles[k]) > 0.85:
                dup_count += 1
    dup_ratio = dup_count / max(len(jobs), 1)
    dup_score = clamp(100 - dup_ratio * 200)
    sub_scores.append(SubScore(
        name="重复检测", score=dup_score,
        weight=FRESHNESS_WEIGHTS["duplicate_detection"],
        detail=f"发现 {dup_count} 对高度相似岗位",
        risk_level="安全" if dup_score >= 70 else ("警告" if dup_score < 40 else "注意"),
    ))

    total_score = sum(s.score * s.weight for s in sub_scores)

    risks = []
    suggestions = []
    if hr_score < 40:
        risks.append("HR 长期不活跃，岗位可能已过期")
    if dup_count > len(jobs) * 0.3:
        risks.append("大量重复/高度相似岗位，可能为虚假招聘")
    all_descs = " ".join(j.description for j in jobs)
    found_risk_words = check_risk_keywords(all_descs)
    if found_risk_words:
        risks.append(f"发现风险关键词: {', '.join(found_risk_words)}")
    if salary_score < 40:
        risks.append("薪资范围不合理（上下限差距过大或缺失）")
    if hr_score < 60:
        suggestions.append("建议直接联系 HR 确认岗位是否仍在招聘")
    if desc_avg < 50:
        suggestions.append("岗位描述过于简略，建议面试时详细了解工作内容")

    return DimensionResult(
        name="招聘真实性",
        score=total_score,
        sub_scores=sub_scores,
        risks=risks,
        suggestions=suggestions,
    )
