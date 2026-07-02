from datetime import datetime
from typing import Optional
from boss_analyzer.models.snapshot import JobSnapshot, JobChange, JobLifecycleStatus
from boss_analyzer.config import STALE_DAYS


def detect_changes(
    old: list,  # list[JobSnapshot]
    new: list,  # list[JobSnapshot]
    detected_at: str = "",
    recent_history: Optional[dict] = None,
) -> list:
    if not detected_at:
        detected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    old_by_url = {s.job_url: s for s in old}
    new_by_url = {s.job_url: s for s in new}

    changes = []

    # 下线/可能已招到人
    for url, snap in old_by_url.items():
        if url not in new_by_url:
            changes.append(JobChange(
                job_url=url,
                company_name=snap.company_name,
                job_title=snap.job_title,
                change_type="job_offline",
                change_label="可能已招到人",
                old_value=f"上次在线 ({snap.captured_at})",
                new_value="岗位已下线",
                severity="important",
                detected_at=detected_at,
            ))

    for url, snap in new_by_url.items():
        old_snap = old_by_url.get(url)

        # 新增岗位
        if old_snap is None:
            changes.append(JobChange(
                job_url=url,
                company_name=snap.company_name,
                job_title=snap.job_title,
                change_type="new_job",
                change_label="新增岗位",
                new_value=snap.job_title,
                severity="info",
                detected_at=detected_at,
            ))
            continue

        # 描述变化
        if snap.description_hash and old_snap.description_hash and snap.description_hash != old_snap.description_hash:
            changes.append(JobChange(
                job_url=url,
                company_name=snap.company_name,
                job_title=snap.job_title,
                change_type="description_changed",
                change_label="岗位描述已更新",
                old_value="旧描述",
                new_value="新描述",
                severity="info",
                detected_at=detected_at,
            ))

        # 薪资变化
        if (snap.salary_min, snap.salary_max) != (old_snap.salary_min, old_snap.salary_max):
            old_sal = f"{old_snap.salary_min}-{old_snap.salary_max}K" if old_snap.salary_min else "面议"
            new_sal = f"{snap.salary_min}-{snap.salary_max}K" if snap.salary_min else "面议"
            if old_sal != new_sal:
                changes.append(JobChange(
                    job_url=url,
                    company_name=snap.company_name,
                    job_title=snap.job_title,
                    change_type="salary_changed",
                    change_label="薪资调整",
                    old_value=old_sal,
                    new_value=new_sal,
                    severity="info",
                    detected_at=detected_at,
                ))

        # HR 由不活跃变活跃
        if snap.hr_active_days <= 1 and old_snap.hr_active_days > 7:
            changes.append(JobChange(
                job_url=url,
                company_name=snap.company_name,
                job_title=snap.job_title,
                change_type="hr_active",
                change_label="HR 近期活跃",
                old_value=f"上次活跃 {old_snap.hr_active_days} 天前",
                new_value=snap.hr_active_time or "今日在线",
                severity="info",
                detected_at=detected_at,
            ))

        # 长期不更新
        if snap.hr_active_days > STALE_DAYS:
            changes.append(JobChange(
                job_url=url,
                company_name=snap.company_name,
                job_title=snap.job_title,
                change_type="stale",
                change_label="招聘长期不更新",
                old_value="",
                new_value=f"HR 已 {snap.hr_active_days} 天未活跃",
                severity="warning",
                detected_at=detected_at,
            ))

        history = recent_history.get(url, []) if recent_history else []
        if _is_frequently_updated(history):
            changes.append(JobChange(
                job_url=url,
                company_name=snap.company_name,
                job_title=snap.job_title,
                change_type="frequent_update",
                change_label="招聘频繁更新",
                old_value=f"近 {len(history)} 次快照",
                new_value="薪资/描述/HR 活跃状态多次变化",
                severity="warning",
                detected_at=detected_at,
            ))

    changes.sort(key=lambda c: (c.severity_order, c.change_type))
    return changes


def _is_frequently_updated(history: list) -> bool:
    if len(history) < 4:
        return False

    signatures = []
    for snap in history:
        signatures.append((
            snap.salary_min,
            snap.salary_max,
            snap.description_hash,
            snap.hr_active_days,
        ))

    transitions = sum(
        1 for before, after in zip(signatures, signatures[1:])
        if before != after
    )
    return transitions >= 3


def classify_lifecycle(history: list, detected_at: str = "") -> JobLifecycleStatus:
    if not history:
        return JobLifecycleStatus(
            job_url="",
            company_name="",
            job_title="",
            status_code="uncertain",
            status_label="样本不足",
            confidence="低",
            evidence="尚未建立历史快照",
        )

    current = history[-1]
    detected = _parse_dt(detected_at) or _parse_dt(current.captured_at) or datetime.now()
    first_seen = _parse_dt(history[0].captured_at) or detected
    last_content_update = _last_content_update_at(history) or first_seen
    observed_days = max(0, (detected - first_seen).days)
    days_since_update = max(0, (detected - last_content_update).days)
    update_count = _content_update_count(history)
    seen_count = len(history)
    active_days = current.hr_active_days

    status_code = "uncertain"
    status_label = "样本不足"
    confidence = "低"
    evidence = f"仅有 {seen_count} 次快照，需要继续观察"

    if seen_count == 1 or observed_days <= 1:
        status_code = "new"
        status_label = "新发现岗位"
        confidence = "中"
        evidence = "首次或近 1 天内发现，先作为基准观察"
    elif observed_days <= 14 and (active_days <= 1 or update_count >= 2):
        status_code = "urgent"
        status_label = "短期急招"
        confidence = "中"
        evidence = f"{observed_days} 天内出现，HR 近 {active_days} 天活跃，内容更新 {update_count} 次"
    elif observed_days >= 30 and days_since_update >= 21 and active_days > 14:
        status_code = "stale"
        status_label = "长期低热/疑似占位"
        confidence = "中"
        evidence = f"已观察 {observed_days} 天，{days_since_update} 天未见内容更新，HR 活跃弱"
    elif observed_days >= 45 and active_days <= 14:
        status_code = "evergreen"
        status_label = "长期常招/人才池"
        confidence = "中" if update_count else "低"
        evidence = f"已连续观察 {observed_days} 天，仍保持在线，内容更新 {update_count} 次"
    elif active_days <= 7 and days_since_update <= 21:
        status_code = "active"
        status_label = "正常在招"
        confidence = "中"
        evidence = f"HR 近 {active_days} 天活跃，{days_since_update} 天内有内容变化或基准更新"
    elif active_days >= 999:
        status_label = "状态不明"
        evidence = f"已观察 {observed_days} 天，但未采集到可靠 HR 活跃时间"
    else:
        status_label = "持续观察"
        evidence = f"已观察 {observed_days} 天，距内容更新 {days_since_update} 天，信号不足"

    return JobLifecycleStatus(
        job_url=current.job_url,
        company_name=current.company_name,
        job_title=current.job_title,
        status_code=status_code,
        status_label=status_label,
        confidence=confidence,
        observed_days=observed_days,
        days_since_update=days_since_update,
        seen_count=seen_count,
        update_count=update_count,
        evidence=evidence,
    )


def classify_lifecycles(histories: dict, detected_at: str = "") -> list:
    statuses = [
        classify_lifecycle(history, detected_at)
        for history in histories.values()
        if history
    ]
    statuses.sort(key=lambda s: (_status_order(s.status_code), -s.observed_days, s.job_title))
    return statuses


def _status_order(status_code: str) -> int:
    return {
        "urgent": 0,
        "stale": 1,
        "evergreen": 2,
        "active": 3,
        "new": 4,
        "uncertain": 5,
        "offline": 6,
    }.get(status_code, 9)


def _content_update_count(history: list) -> int:
    signatures = [_content_signature(s) for s in history]
    return sum(
        1 for before, after in zip(signatures, signatures[1:])
        if before != after
    )


def _last_content_update_at(history: list):
    if not history:
        return None
    last_seen = _parse_dt(history[0].captured_at)
    prev = _content_signature(history[0])
    for snap in history[1:]:
        current = _content_signature(snap)
        if current != prev:
            last_seen = _parse_dt(snap.captured_at) or last_seen
            prev = current
    return last_seen


def _content_signature(snap: JobSnapshot) -> tuple:
    return (
        snap.job_title,
        snap.salary_min,
        snap.salary_max,
        snap.experience_req,
        snap.education_req,
        snap.skills_json,
        snap.description_hash,
    )


def _parse_dt(value: str):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None
