from datetime import datetime
from boss_analyzer.models.snapshot import JobSnapshot, JobChange
from boss_analyzer.config import STALE_DAYS


def detect_changes(
    old: list,  # list[JobSnapshot]
    new: list,  # list[JobSnapshot]
    detected_at: str = "",
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

    changes.sort(key=lambda c: (c.severity_order, c.change_type))
    return changes
