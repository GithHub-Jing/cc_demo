import argparse
import logging
from datetime import datetime
from boss_analyzer.scrapers.boss import BossScraper
from boss_analyzer.scrapers.tianyancha import TianyanchaScraper
from boss_analyzer.scrapers.search_engine import SearchEngineScraper
from boss_analyzer.analyzers.legitimacy import evaluate_legitimacy
from boss_analyzer.analyzers.freshness import evaluate_freshness
from boss_analyzer.analyzers.fitness import evaluate_fitness
from boss_analyzer.models.job import UserProfile
from boss_analyzer.models.report import AnalysisReport
from boss_analyzer.report.html_report import generate_report
from boss_analyzer.utils.helpers import setup_logging, logger


def analyze(
    query: str,
    profile: UserProfile = None,
    headless: bool = True,
    skip_tianyancha: bool = False,
    skip_search: bool = False,
    output_path: str = "",
) -> AnalysisReport:
    logger.info(f"开始分析: {query}")

    # 1. Boss直聘采集
    boss = BossScraper(headless=headless)
    result = boss.scrape(query)
    company = result.get("company")
    jobs = result.get("jobs", [])

    if not company:
        logger.error("未找到目标公司信息，分析终止")
        return AnalysisReport(company_name=query, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    logger.info(f"Boss直聘采集完成: {company.name}, {len(jobs)} 个岗位")

    # 2. 天眼查交叉验证
    if not skip_tianyancha:
        try:
            tianyancha = TianyanchaScraper(headless=headless)
            tianyancha.update_company(company)
            logger.info("天眼查验证完成")
        except Exception as e:
            logger.warning(f"天眼查采集失败，跳过: {e}")

    # 3. 搜索引擎验证
    if not skip_search:
        try:
            search = SearchEngineScraper()
            search.update_company(company)
            logger.info("搜索引擎验证完成")
        except Exception as e:
            logger.warning(f"搜索引擎采集失败，跳过: {e}")

    # 4. 三维评分
    report = AnalysisReport(
        company_name=company.name,
        legitimacy=evaluate_legitimacy(company),
        freshness=evaluate_freshness(company, jobs),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    if profile and profile.experience_years > 0:
        report.fitness = evaluate_fitness(jobs, profile)

    logger.info(
        f"评分完成: 企业真实性={report.legitimacy.score:.0f}, "
        f"招聘真实性={report.freshness.score:.0f}, "
        f"岗位贴合度={report.fitness.score:.0f if report.fitness else '未评估'}"
    )
    logger.info(f"总评分: {report.overall_score:.0f} ({report.overall_risk_level})")

    # 5. 生成报告
    path = generate_report(report, output_path)
    logger.info(f"报告已生成: {path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Boss直聘企业招聘风险分析工具")
    parser.add_argument("query", help="公司名称或 Boss直聘公司页面 URL")
    parser.add_argument("-o", "--output", default="", help="报告输出路径")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--skip-tianyancha", action="store_true", help="跳过天眼查验证")
    parser.add_argument("--skip-search", action="store_true", help="跳过搜索引擎验证")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志输出")

    parser.add_argument("--experience", type=int, default=0, help="工作经验年数")
    parser.add_argument("--skills", nargs="*", default=[], help="技能列表")
    parser.add_argument("--education", default="", help="学历（如: 本科、硕士）")
    parser.add_argument("--salary-min", type=int, default=0, help="期望最低薪资(K)")
    parser.add_argument("--salary-max", type=int, default=0, help="期望最高薪资(K)")

    args = parser.parse_args()
    setup_logging(args.verbose)

    profile = None
    if args.experience > 0 or args.skills or args.education:
        profile = UserProfile(
            experience_years=args.experience,
            skills=args.skills,
            education=args.education,
            expected_salary_min=args.salary_min,
            expected_salary_max=args.salary_max,
        )

    analyze(
        query=args.query,
        profile=profile,
        headless=not args.no_headless,
        skip_tianyancha=args.skip_tianyancha,
        skip_search=args.skip_search,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
