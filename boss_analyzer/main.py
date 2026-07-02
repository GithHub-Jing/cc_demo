from typing import Optional
import argparse
import logging
import time
import uuid
from datetime import datetime
from boss_analyzer.scrapers.boss import BossScraper
from boss_analyzer.scrapers.boss_api import BossApiClient
from boss_analyzer.scrapers.tianyancha import TianyanchaScraper
from boss_analyzer.scrapers.search_engine import SearchEngineScraper
from boss_analyzer.storage.cookie_store import (
    has_cookies, save_cookies_from_browser, cookie_file_path, extract_cookies_from_browser,
)
from boss_analyzer.analyzers.legitimacy import evaluate_legitimacy
from boss_analyzer.analyzers.freshness import evaluate_freshness
from boss_analyzer.analyzers.fitness import evaluate_fitness, evaluate_fitness_per_job
from boss_analyzer.analyzers.ranking import rank_matches
from boss_analyzer.analyzers.tracker import detect_changes
from boss_analyzer.models.job import UserProfile
from boss_analyzer.models.ranking import JobMatch
from boss_analyzer.models.report import AnalysisReport
from boss_analyzer.models.snapshot import JobSnapshot
from boss_analyzer.storage.sqlite_store import JobStore
from boss_analyzer.report.html_report import (
    generate_report, generate_ranking_report, generate_tracking_report,
)
from boss_analyzer.utils.helpers import setup_logging, logger
from boss_analyzer.config import CITY_CODES, SEARCH_LIMIT


# ------------------------------------------------------------------ #
#  analyze
# ------------------------------------------------------------------ #

def analyze(
    query: str,
    profile: UserProfile = None,
    headless: bool = True,
    fast: bool = False,
    skip_tianyancha: bool = False,
    skip_search: bool = False,
    output_path: str = "",
) -> AnalysisReport:
    logger.info(f"开始分析: {query}")

    boss = BossScraper(headless=headless, fast=fast)
    result = boss.scrape(query)
    company = result.get("company")
    jobs = result.get("jobs", [])

    if not company:
        logger.error("未找到目标公司信息，分析终止")
        return AnalysisReport(company_name=query, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    logger.info(f"Boss直聘采集完成: {company.name}, {len(jobs)} 个岗位")

    if not skip_tianyancha and not fast:
        try:
            tianyancha = TianyanchaScraper(headless=headless)
            tianyancha.update_company(company)
            logger.info("天眼查验证完成")
        except Exception as e:
            logger.warning(f"天眼查采集失败，跳过: {e}")

    if not skip_search and not fast:
        try:
            search = SearchEngineScraper()
            search.update_company(company)
            logger.info("搜索引擎验证完成")
        except Exception as e:
            logger.warning(f"搜索引擎采集失败，跳过: {e}")

    report = AnalysisReport(
        company_name=company.name,
        legitimacy=evaluate_legitimacy(company),
        freshness=evaluate_freshness(company, jobs),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    if profile and profile.experience_years > 0:
        report.fitness = evaluate_fitness(jobs, profile)
        report.job_fitness_list = evaluate_fitness_per_job(jobs, profile)

    fitness_str = f"{report.fitness.score:.0f}" if report.fitness else "未评估"
    logger.info(
        f"评分完成: 企业真实性={report.legitimacy.score:.0f}, "
        f"招聘真实性={report.freshness.score:.0f}, "
        f"岗位贴合度={fitness_str}"
    )
    logger.info(f"总评分: {report.overall_score:.0f} ({report.overall_risk_level})")

    path = generate_report(report, output_path)
    logger.info(f"报告已生成: {path}")

    return report


# ------------------------------------------------------------------ #
#  track
# ------------------------------------------------------------------ #

def track(
    query: str,
    headless: bool = True,
    fast: bool = True,
    output_path: str = "",
    db_path: str = "",
    position: str = "",
    city: str = "全国",
    limit: int = SEARCH_LIMIT,
) -> None:
    now = datetime.now()
    run_id = str(uuid.uuid4())[:8]
    captured_at = now.strftime("%Y-%m-%d %H:%M:%S")

    logger.info(f"开始追踪: {query} (run={run_id})")

    if position:
        company_name, jobs = _search_company_jobs(
            company_query=query,
            position=position,
            city=city,
            limit=limit,
            headless=headless,
            fast=fast,
        )
        company = None
    else:
        boss = BossScraper(headless=headless, fast=fast)
        result = boss.scrape(query)
        company = result.get("company")
        jobs = result.get("jobs", [])
        company_name = company.name if company else ""

    if not company_name:
        logger.error("未找到公司信息，追踪终止")
        return

    logger.info(f"采集到 {len(jobs)} 个岗位")

    store = JobStore(db_path) if db_path else JobStore()

    # 当前快照
    current_snapshots = [
        JobSnapshot.from_job(j, company_name, run_id, captured_at)
        for j in jobs
    ]

    # 上次快照
    prev_snapshots = store.get_last_snapshots(company_name)
    is_first_run = len(prev_snapshots) == 0

    # 先保存当前快照
    store.save_snapshots(company_name, current_snapshots, run_id, captured_at)

    # 变更检测
    changes = []
    prev_run_at = ""
    if not is_first_run:
        recent_history = {
            s.job_url: store.get_snapshot_history(company_name, s.job_url, limit=8)
            for s in current_snapshots
        }
        changes = detect_changes(prev_snapshots, current_snapshots, captured_at, recent_history)
        history = store.get_run_history(company_name, limit=2)
        if len(history) >= 2:
            prev_run_at = history[1].get("ran_at", "")

    # 终端摘要
    _print_tracking_summary(company_name, current_snapshots, changes, is_first_run)

    # HTML 报告
    path = generate_tracking_report(
        company_name=company_name,
        current_snapshots=current_snapshots,
        changes=changes,
        is_first_run=is_first_run,
        prev_run_at=prev_run_at,
        output_path=output_path,
    )
    logger.info(f"追踪报告已生成: {path}")


def _search_company_jobs(
    company_query: str,
    position: str,
    city: str,
    limit: int,
    headless: bool,
    fast: bool,
) -> tuple[str, list]:
    city_code = CITY_CODES.get(city, CITY_CODES["全国"])
    if city != "全国" and city not in CITY_CODES:
        logger.warning(f"城市 '{city}' 不在城市列表，已回退到全国搜索")

    logger.info(
        f"使用岗位搜索追踪: 公司={company_query}, 岗位={position}, 城市={city}({city_code}), 限制={limit}"
    )

    pairs = None
    api = BossApiClient()
    if api.setup():
        logger.info("使用 API 模式追踪（已检测到 Cookie）")
        pairs = api.search_jobs(position, city_code, limit)
        if not pairs:
            logger.warning("API 返回 0 条结果，回退到浏览器模式")
            pairs = None
    else:
        logger.info("未找到 Cookie，使用浏览器模式追踪（速度较慢）")

    if pairs is None:
        boss = BossScraper(headless=headless, fast=fast)
        pairs = boss.search_jobs_by_position(position, city_code, limit)

    matched = [
        (company, job)
        for company, job in pairs
        if _company_matches(company.name, company_query)
        or _company_matches(company.full_name, company_query)
        or _company_matches(company.boss_url, company_query)
    ]

    if not matched:
        logger.warning(f"岗位搜索结果中未找到匹配企业: {company_query}")
        return "", []

    company_name = matched[0][0].name or company_query
    return company_name, [job for _, job in matched]


def _company_matches(candidate: str, query: str) -> bool:
    if not candidate or not query:
        return False
    return query in candidate or candidate in query


def _print_tracking_summary(company_name, snapshots, changes, is_first_run):
    sep = "=" * 50
    print(f"\n{sep}")
    print(f"  岗位追踪摘要 · {company_name}")
    print(sep)
    if is_first_run:
        print(f"  📌 首次追踪，已建立基准快照（{len(snapshots)} 个岗位）")
    else:
        counts = {}
        for c in changes:
            counts[c.change_type] = counts.get(c.change_type, 0) + 1
        print(f"  📊 当前岗位: {len(snapshots)} 个")
        if counts:
            print(f"  🟢 新增: {counts.get('new_job', 0)}  "
                  f"⚪ 下线: {counts.get('job_offline', 0)}  "
                  f"🔵 更新: {counts.get('description_changed', 0) + counts.get('salary_changed', 0)}  "
                  f"🟠 频繁更新: {counts.get('frequent_update', 0)}  "
                  f"🟡 不活跃: {counts.get('stale', 0)}")
        else:
            print("  ✓ 与上次相比无变更")
        if changes:
            print()
            for c in changes[:10]:
                print(f"  {c.icon} [{c.change_label}] {c.job_title}"
                      + (f"  {c.old_value} → {c.new_value}" if c.old_value or c.new_value else ""))
            if len(changes) > 10:
                print(f"  ... 共 {len(changes)} 条变更，详见 HTML 报告")
    print(sep + "\n")


# ------------------------------------------------------------------ #
#  login
# ------------------------------------------------------------------ #

def boss_login(headless: bool = False) -> bool:
    """Open a browser, let the user log in to Boss直聘, then save cookies."""
    from boss_analyzer.scrapers.boss import _CHROME_PATH
    from DrissionPage import ChromiumPage, ChromiumOptions

    logger.info("打开浏览器，请在浏览器中完成登录...")
    print("\n正在打开 Boss直聘 登录页面，请在浏览器中扫码或输入账号密码完成登录。")
    print("登录成功后，本程序将自动检测并保存 Cookie。\n")

    opts = ChromiumOptions()
    opts.auto_port()
    opts.set_browser_path(_CHROME_PATH)
    opts.set_argument("--no-sandbox")
    opts.set_argument("--disable-dev-shm-usage")
    if headless:
        opts.headless()

    try:
        page = ChromiumPage(addr_or_opts=opts)
    except Exception as e:
        logger.error(f"无法启动浏览器: {e}")
        return False

    page.get("https://www.zhipin.com/web/user/?ka=header-login")

    # Poll until user is logged in (max 3 minutes)
    deadline = time.time() + 180
    logged_in = False
    while time.time() < deadline:
        url = page.url or ""
        cookies = extract_cookies_from_browser(page) if hasattr(page, "cookies") else {}
        # Logged-in users have a session token. Redirects can happen for visitor pages,
        # so do not treat URL changes alone as a successful login.
        if cookies.get("__zp_stoken__"):
            logged_in = True
            break
        time.sleep(2)

    if not logged_in:
        logger.warning("登录超时 (3分钟)，Cookie 未保存")
        try:
            page.quit()
        except Exception:
            pass
        return False

    saved = save_cookies_from_browser(page)
    try:
        page.quit()
    except Exception:
        pass

    if saved:
        print(f"\nCookie 已保存至 {cookie_file_path()}")
        print("后续运行 `search` 命令将自动使用此 Cookie，速度大幅提升。\n")
        return True
    else:
        logger.error("Cookie 保存失败")
        return False


# ------------------------------------------------------------------ #
#  search_positions
# ------------------------------------------------------------------ #

def search_positions(
    position: str,
    profile: UserProfile = None,
    city: str = "全国",
    limit: int = SEARCH_LIMIT,
    full_analysis: bool = False,
    headless: bool = True,
    fast: bool = False,
    skip_tianyancha: bool = False,
    output_path: str = "",
) -> list:
    city_code = CITY_CODES.get(city, CITY_CODES["全国"])
    if city != "全国" and city not in CITY_CODES:
        logger.warning(f"城市 '{city}' 不在城市列表，已回退到全国搜索。支持的城市: {', '.join(sorted(CITY_CODES.keys()))}")
    logger.info(f"搜索岗位: {position}, 城市: {city}({city_code}), 限制: {limit} 条")

    # ── 优先走 API（cookie 方式，无需浏览器，速度快）──────────────────
    api = BossApiClient()
    if api.setup():
        logger.info("使用 API 模式搜索（已检测到 Cookie）")
        pairs = api.search_jobs(position, city_code, limit)
        if pairs:
            logger.info(f"API 返回 {len(pairs)} 条结果")
        else:
            logger.warning("API 返回 0 条结果，回退到浏览器模式")
            pairs = None
    else:
        logger.info("未找到 Cookie，使用浏览器模式搜索（速度较慢）")
        pairs = None

    if pairs is None:
        boss = BossScraper(headless=headless, fast=fast)
        pairs = boss.search_jobs_by_position(position, city_code, limit)
        logger.info(f"浏览器模式搜索到 {len(pairs)} 条结果")

    matches = []
    for company, job in pairs:
        match = JobMatch(company=company, job=job)
        if profile:
            from boss_analyzer.analyzers.fitness import (
                _score_experience, _score_skills, _score_education, _score_salary,
            )
            from boss_analyzer.config import FITNESS_WEIGHTS
            score = (
                _score_experience(job, profile) * FITNESS_WEIGHTS["experience_match"]
                + _score_skills(job, profile) * FITNESS_WEIGHTS["skill_match"]
                + _score_education(job, profile) * FITNESS_WEIGHTS["education_match"]
                + _score_salary(job, profile) * FITNESS_WEIGHTS["salary_match"]
            )
            match.fitness_score = round(score, 1)
        matches.append(match)

    if full_analysis and matches:
        logger.info("完整模式：对 Top 结果补充企业真实性分析...")
        top_matches = sorted(matches, key=lambda m: m.fitness_score, reverse=True)[:10]
        for match in top_matches:
            if not match.company.boss_url:
                continue
            try:
                extra_boss = BossScraper(headless=headless, fast=fast)
                r = extra_boss.scrape(match.company.boss_url)
                full_company = r.get("company")
                full_jobs = r.get("jobs", [])
                if not full_company:
                    continue
                if not skip_tianyancha:
                    try:
                        TianyanchaScraper(headless=headless).update_company(full_company)
                    except Exception as e:
                        logger.debug(f"天眼查失败: {e}")
                try:
                    SearchEngineScraper().update_company(full_company)
                except Exception as e:
                    logger.debug(f"搜索引擎失败: {e}")
                match.legitimacy_score = evaluate_legitimacy(full_company).score
                match.freshness_score = evaluate_freshness(full_company, full_jobs).score
                match.company = full_company
            except Exception as e:
                logger.warning(f"完整分析失败 ({match.company.name}): {e}")

    ranked = rank_matches(matches)
    path = generate_ranking_report(ranked, position, city, profile, output_path)
    logger.info(f"排名报告已生成: {path}")
    return ranked


# ------------------------------------------------------------------ #
#  CLI
# ------------------------------------------------------------------ #

def _build_profile(args) -> Optional[UserProfile]:
    if args.experience > 0 or args.skills or args.education:
        return UserProfile(
            experience_years=args.experience,
            skills=args.skills,
            education=args.education,
            expected_salary_min=args.salary_min,
            expected_salary_max=args.salary_max,
        )
    return None


def _add_profile_args(parser):
    parser.add_argument("--experience", type=int, default=0, help="工作经验年数")
    parser.add_argument("--skills", nargs="*", default=[], help="技能列表")
    parser.add_argument("--education", default="", help="学历（如: 本科、硕士）")
    parser.add_argument("--salary-min", type=int, default=0, help="期望最低薪资(K)")
    parser.add_argument("--salary-max", type=int, default=0, help="期望最高薪资(K)")


def _run_track_command(args, headless: bool):
    runs = max(args.runs, 0)
    completed = 0

    while runs == 0 or completed < runs:
        track(
            query=args.query,
            headless=headless,
            fast=args.fast,
            output_path=args.output,
            db_path=args.db,
            position=args.position,
            city=args.city,
            limit=args.limit,
        )
        completed += 1

        if args.interval_minutes <= 0 or (runs and completed >= runs):
            break

        sleep_seconds = args.interval_minutes * 60
        logger.info(f"等待 {args.interval_minutes:g} 分钟后执行下一次追踪...")
        time.sleep(sleep_seconds)


def main():
    parser = argparse.ArgumentParser(description="Boss直聘企业招聘分析工具")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    sub = parser.add_subparsers(dest="cmd")

    # --- analyze（默认）---
    p_analyze = sub.add_parser("analyze", help="分析指定公司的招聘信息")
    p_analyze.add_argument("query", help="公司名称或 Boss直聘公司页面 URL")
    p_analyze.add_argument("-o", "--output", default="")
    p_analyze.add_argument("--no-headless", action="store_true")
    p_analyze.add_argument("--fast", action="store_true", help="快速模式：仅 Boss直聘，短延迟")
    p_analyze.add_argument("--skip-tianyancha", action="store_true")
    p_analyze.add_argument("--skip-search", action="store_true")
    _add_profile_args(p_analyze)

    # --- login ---
    p_login = sub.add_parser("login", help="打开浏览器完成 Boss直聘 登录并保存 Cookie（search 命令前置步骤）")
    p_login.add_argument("--headless", action="store_true", help="无头模式（默认关闭，登录需要可视浏览器）")

    # --- track ---
    p_track = sub.add_parser("track", help="定期追踪岗位变化")
    p_track.add_argument("query", help="公司名称或 Boss直聘 URL")
    p_track.add_argument("-o", "--output", default="")
    p_track.add_argument("--no-headless", action="store_true")
    p_track.add_argument("--fast", action="store_true", default=True,
                         help="快速模式（默认开启）")
    p_track.add_argument("--db", default="", help="自定义数据库路径")
    p_track.add_argument("--position", default="", help="按岗位关键词追踪目标企业，如: Python工程师")
    p_track.add_argument("--city", default="全国")
    p_track.add_argument("--limit", type=int, default=SEARCH_LIMIT)
    p_track.add_argument("--interval-minutes", type=float, default=0,
                         help="定时追踪间隔。默认只执行一次")
    p_track.add_argument("--runs", type=int, default=1,
                         help="执行次数；配合 --interval-minutes 使用，0 表示持续执行")

    # --- search ---
    p_search = sub.add_parser("search", help="按岗位关键词搜索并排序")
    p_search.add_argument("position", help="岗位名称，如: Python后端工程师")
    p_search.add_argument("--city", default="全国")
    p_search.add_argument("--limit", type=int, default=SEARCH_LIMIT)
    p_search.add_argument("--full", action="store_true")
    p_search.add_argument("--fast", action="store_true")
    p_search.add_argument("-o", "--output", default="")
    p_search.add_argument("--no-headless", action="store_true")
    _add_profile_args(p_search)

    # 向后兼容：直接 python -m boss_analyzer "公司名" --fast ...
    parser.add_argument("query", nargs="?", default="", help=argparse.SUPPRESS)
    parser.add_argument("-o", "--output", default="", help=argparse.SUPPRESS)
    parser.add_argument("--no-headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fast", action="store_true", help="快速模式：仅 Boss直聘，短延迟")
    parser.add_argument("--skip-tianyancha", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-search", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--search", metavar="POSITION", help=argparse.SUPPRESS)
    parser.add_argument("--city", default="全国", help=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=SEARCH_LIMIT, help=argparse.SUPPRESS)
    parser.add_argument("--full", action="store_true", help=argparse.SUPPRESS)
    _add_profile_args(parser)

    args = parser.parse_args()
    setup_logging(args.verbose)

    headless = not args.no_headless
    profile = _build_profile(args)

    if args.cmd == "login":
        boss_login(headless=getattr(args, "headless", False))
    elif args.cmd == "track":
        _run_track_command(
            args=args,
            headless=headless,
        )
    elif args.cmd == "search":
        search_positions(
            position=args.position,
            profile=profile,
            city=args.city,
            limit=args.limit,
            full_analysis=args.full,
            headless=headless,
            fast=args.fast,
            output_path=args.output,
        )
    elif args.cmd == "analyze":
        analyze(
            query=args.query,
            profile=profile,
            headless=headless,
            fast=args.fast,
            skip_tianyancha=args.skip_tianyancha,
            skip_search=args.skip_search,
            output_path=args.output,
        )
    elif args.search:
        # 向后兼容 --search
        search_positions(
            position=args.search,
            profile=profile,
            city=args.city,
            limit=args.limit,
            full_analysis=args.full,
            headless=headless,
            fast=args.fast,
            output_path=args.output,
        )
    elif args.query:
        # 向后兼容：裸 query
        analyze(
            query=args.query,
            profile=profile,
            headless=headless,
            fast=args.fast,
            skip_tianyancha=args.skip_tianyancha,
            skip_search=args.skip_search,
            output_path=args.output,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
