from boss_analyzer.models.company import Company
from boss_analyzer.models.report import DimensionResult, SubScore
from boss_analyzer.config import LEGITIMACY_WEIGHTS
from boss_analyzer.utils.helpers import parse_capital, calculate_company_age, clamp


def evaluate_legitimacy(company: Company) -> DimensionResult:
    sub_scores = []

    # 注册信息完整度
    filled = sum(1 for v in [
        company.full_name, company.legal_representative,
        company.registered_capital, company.registered_address,
        company.industry, company.scale,
    ] if v)
    reg_score = clamp(filled / 6 * 100)
    sub_scores.append(SubScore(
        name="注册信息", score=reg_score,
        weight=LEGITIMACY_WEIGHTS["registration"],
        detail=f"已填充 {filled}/6 项工商信息",
        risk_level="安全" if reg_score >= 60 else "警告",
    ))

    # 经营状态
    status = company.business_status
    if any(kw in status for kw in ["存续", "在业", "开业"]):
        status_score = 100
    elif "迁出" in status:
        status_score = 60
    elif any(kw in status for kw in ["注销", "吊销"]):
        status_score = 0
    elif status:
        status_score = 50
    else:
        status_score = 30
    sub_scores.append(SubScore(
        name="经营状态", score=status_score,
        weight=LEGITIMACY_WEIGHTS["business_status"],
        detail=f"状态: {status or '未知'}",
        risk_level="安全" if status_score >= 80 else ("危险" if status_score <= 20 else "注意"),
    ))

    # 成立年限
    age = calculate_company_age(company.founded_date)
    if age >= 5:
        age_score = 100
    elif age >= 3:
        age_score = 80
    elif age >= 1:
        age_score = 60
    elif age > 0:
        age_score = 40
    else:
        age_score = 20
    sub_scores.append(SubScore(
        name="成立年限", score=age_score,
        weight=LEGITIMACY_WEIGHTS["company_age"],
        detail=f"成立 {age:.1f} 年" if age > 0 else "成立时间未知",
        risk_level="安全" if age_score >= 80 else ("注意" if age_score >= 60 else "警告"),
    ))

    # 注册资本
    capital = parse_capital(company.registered_capital)
    if capital >= 1000:
        cap_score = 100
    elif capital >= 500:
        cap_score = 85
    elif capital >= 100:
        cap_score = 70
    elif capital >= 10:
        cap_score = 50
    elif capital > 0:
        cap_score = 30
    else:
        cap_score = 10
    sub_scores.append(SubScore(
        name="注册资本", score=cap_score,
        weight=LEGITIMACY_WEIGHTS["registered_capital"],
        detail=f"注册资本: {company.registered_capital or '未知'}",
        risk_level="安全" if cap_score >= 70 else "注意",
    ))

    # 社保人数匹配
    ins_score = 50
    if company.social_insurance_count is not None and company.scale:
        from boss_analyzer.config import COMPANY_SCALE_MAP
        for label, (lo, hi) in COMPANY_SCALE_MAP.items():
            if label in company.scale:
                ratio = company.social_insurance_count / max(lo, 1)
                if ratio >= 0.5:
                    ins_score = 100
                elif ratio >= 0.2:
                    ins_score = 70
                else:
                    ins_score = 30
                break
    elif company.social_insurance_count is not None:
        ins_score = 60 if company.social_insurance_count > 10 else 40
    sub_scores.append(SubScore(
        name="社保匹配", score=ins_score,
        weight=LEGITIMACY_WEIGHTS["insurance_match"],
        detail=f"社保人数: {company.social_insurance_count or '未知'}, 规模: {company.scale or '未知'}",
        risk_level="安全" if ins_score >= 70 else ("警告" if ins_score < 40 else "注意"),
    ))

    # 网络存在感
    presence_count = sum([
        company.has_official_website,
        company.multi_platform_presence,
        company.news_count > 0,
        company.search_result_count > 50,
    ])
    presence_score = clamp(presence_count / 4 * 100)
    if company.tianyancha_verified:
        presence_score = clamp(presence_score + 15)
    sub_scores.append(SubScore(
        name="网络存在", score=presence_score,
        weight=LEGITIMACY_WEIGHTS["online_presence"],
        detail=f"官网={'有' if company.has_official_website else '无'}, "
               f"多平台={'是' if company.multi_platform_presence else '否'}, "
               f"新闻={company.news_count}条",
        risk_level="安全" if presence_score >= 60 else "警告",
    ))

    total_score = sum(s.score * s.weight for s in sub_scores)

    risks = []
    suggestions = []
    if status_score <= 20:
        risks.append("企业经营状态异常（注销/吊销），极高风险")
    if age_score <= 40:
        risks.append("企业成立时间过短，稳定性存疑")
    if cap_score <= 30:
        risks.append("注册资本过低")
    if company.penalties > 0:
        risks.append(f"存在 {company.penalties} 条行政处罚记录")
    if company.lawsuits > 3:
        risks.append(f"存在 {company.lawsuits} 条法律诉讼记录")
    if company.risk_count > 5:
        risks.append(f"天眼查风险提示 {company.risk_count} 条")
    if not company.tianyancha_verified:
        suggestions.append("建议在天眼查/企查查核实企业工商信息")
    if not company.has_official_website:
        suggestions.append("未发现企业官方网站，建议进一步核实")
    if presence_score < 40:
        suggestions.append("企业网络信息匮乏，建议谨慎对待")

    return DimensionResult(
        name="企业真实性",
        score=total_score,
        sub_scores=sub_scores,
        risks=risks,
        suggestions=suggestions,
    )
