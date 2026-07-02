import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class JobSnapshot:
    job_url: str
    company_name: str
    job_title: str
    salary_min: int = 0
    salary_max: int = 0
    experience_req: str = ""
    education_req: str = ""
    skills_json: str = "[]"
    description_hash: str = ""
    hr_active_time: str = ""
    hr_active_days: int = 999
    captured_at: str = ""
    run_id: str = ""

    @staticmethod
    def from_job(job, company_name: str, run_id: str, captured_at: str) -> "JobSnapshot":
        from boss_analyzer.utils.helpers import parse_active_time
        skills = job.skills or []
        desc_hash = hashlib.md5((job.description or "").encode()).hexdigest()
        return JobSnapshot(
            job_url=job.job_url or f"{company_name}::{job.title}",
            company_name=company_name,
            job_title=job.title,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            experience_req=f"{job.experience_min}-{job.experience_max}年",
            education_req=job.education or "",
            skills_json=json.dumps(sorted(skills), ensure_ascii=False),
            description_hash=desc_hash,
            hr_active_time=job.hr_active_time or "",
            hr_active_days=parse_active_time(job.hr_active_time or ""),
            captured_at=captured_at,
            run_id=run_id,
        )


@dataclass
class JobChange:
    job_url: str
    company_name: str
    job_title: str
    change_type: str
    change_label: str
    old_value: str = ""
    new_value: str = ""
    severity: str = "info"
    detected_at: str = ""

    @property
    def severity_order(self) -> int:
        return {"important": 0, "warning": 1, "info": 2}.get(self.severity, 3)

    @property
    def icon(self) -> str:
        icons = {
            "new_job": "🟢",
            "job_offline": "⚪",
            "description_changed": "🔵",
            "salary_changed": "💰",
            "hr_active": "✅",
            "stale": "🟡",
            "frequent_update": "🟠",
        }
        return icons.get(self.change_type, "➖")


@dataclass
class JobLifecycleStatus:
    job_url: str
    company_name: str
    job_title: str
    status_code: str
    status_label: str
    confidence: str
    observed_days: int = 0
    days_since_update: int = 0
    seen_count: int = 0
    update_count: int = 0
    evidence: str = ""

    @property
    def icon(self) -> str:
        icons = {
            "new": "🆕",
            "urgent": "🔥",
            "active": "✅",
            "evergreen": "♻️",
            "stale": "🧊",
            "uncertain": "❔",
            "offline": "⚪",
        }
        return icons.get(self.status_code, "➖")
