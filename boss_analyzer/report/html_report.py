import os
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from boss_analyzer.models.report import AnalysisReport
from boss_analyzer.config import REPORT_OUTPUT_DIR

TEMPLATE_DIR = Path(__file__).parent / "templates"
RISK_COLOR_MAP = {
    "安全": "#22c55e",
    "注意": "#f59e0b",
    "警告": "#f97316",
    "危险": "#ef4444",
}


def generate_report(report: AnalysisReport, output_path: str = "") -> str:
    if not report.generated_at:
        report.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    dimensions = [d for d in [report.legitimacy, report.freshness, report.fitness] if d]
    all_risks = report.all_risks
    all_suggestions = []
    for dim in dimensions:
        all_suggestions.extend(dim.suggestions)

    overall_score = report.overall_score
    overall_level = report.overall_risk_level
    overall_color = RISK_COLOR_MAP.get(overall_level, "#6b7280")

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("report.html")
    html = template.render(
        report=report,
        dimensions=dimensions,
        all_risks=all_risks,
        all_suggestions=all_suggestions,
        overall_score=overall_score,
        overall_level=overall_level,
        overall_color=overall_color,
        risk_color_map=RISK_COLOR_MAP,
    )

    if not output_path:
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in report.company_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(REPORT_OUTPUT_DIR, f"{safe_name}_{timestamp}.html")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def generate_ranking_report(
    matches: list,
    position: str,
    city: str,
    profile=None,
    output_path: str = "",
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("ranking.html")
    html = template.render(
        matches=matches,
        position=position,
        city=city,
        profile=profile,
        generated_at=generated_at,
    )

    if not output_path:
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
        safe_pos = "".join(c if c.isalnum() or c in "-_" else "_" for c in position)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(REPORT_OUTPUT_DIR, f"search_{safe_pos}_{timestamp}.html")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def generate_tracking_report(
    company_name: str,
    current_snapshots: list,
    changes: list,
    is_first_run: bool,
    prev_run_at: str = "",
    output_path: str = "",
) -> str:
    from boss_analyzer.config import STALE_DAYS
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_urls = {c.job_url for c in changes if c.change_type == "new_job"}
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("tracking.html")
    html = template.render(
        company_name=company_name,
        current_jobs=current_snapshots,
        changes=changes,
        is_first_run=is_first_run,
        new_urls=new_urls,
        prev_run_at=prev_run_at,
        stale_days=STALE_DAYS,
        generated_at=generated_at,
    )

    if not output_path:
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in company_name)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(REPORT_OUTPUT_DIR, f"track_{safe}_{ts}.html")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
