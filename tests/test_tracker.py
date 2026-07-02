import unittest
from contextlib import redirect_stdout
from io import StringIO

from boss_analyzer.analyzers.tracker import detect_changes, classify_lifecycle
from boss_analyzer.main import _print_skill_summary
from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job
from boss_analyzer.models.ranking import JobMatch
from boss_analyzer.models.snapshot import JobSnapshot


def snapshot(url, salary_min=10, salary_max=20, desc="a", hr_days=0):
    return JobSnapshot(
        job_url=url,
        company_name="测试公司",
        job_title="Python工程师",
        salary_min=salary_min,
        salary_max=salary_max,
        description_hash=desc,
        hr_active_days=hr_days,
        captured_at="2026-07-02 10:00:00",
        run_id="run",
    )


class TrackerTest(unittest.TestCase):
    def test_detects_frequent_update_from_recent_history(self):
        old = [snapshot("job-1", 10, 20, "a", 0)]
        new = [snapshot("job-1", 13, 23, "d", 0)]
        history = {
            "job-1": [
                snapshot("job-1", 10, 20, "a", 0),
                snapshot("job-1", 11, 21, "b", 0),
                snapshot("job-1", 12, 22, "c", 1),
                snapshot("job-1", 13, 23, "d", 0),
            ]
        }

        changes = detect_changes(old, new, recent_history=history)

        self.assertIn("frequent_update", [c.change_type for c in changes])

    def test_ignores_frequent_update_when_history_is_short(self):
        old = [snapshot("job-1", 10, 20, "a", 0)]
        new = [snapshot("job-1", 11, 21, "b", 0)]
        history = {
            "job-1": [
                snapshot("job-1", 10, 20, "a", 0),
                snapshot("job-1", 11, 21, "b", 0),
            ]
        }

        changes = detect_changes(old, new, recent_history=history)

        self.assertNotIn("frequent_update", [c.change_type for c in changes])

    def test_classifies_short_term_urgent_job(self):
        history = [
            snapshot("job-1", 10, 20, "a", 0),
            snapshot("job-1", 12, 24, "b", 0),
        ]
        history[0].captured_at = "2026-07-01 10:00:00"
        history[1].captured_at = "2026-07-05 10:00:00"

        status = classify_lifecycle(history, "2026-07-05 10:00:00")

        self.assertEqual(status.status_code, "urgent")
        self.assertEqual(status.status_label, "短期急招")

    def test_classifies_stale_long_running_job(self):
        history = [
            snapshot("job-1", 10, 20, "a", 30),
            snapshot("job-1", 10, 20, "a", 30),
        ]
        history[0].captured_at = "2026-05-01 10:00:00"
        history[1].captured_at = "2026-07-01 10:00:00"

        status = classify_lifecycle(history, "2026-07-02 10:00:00")

        self.assertEqual(status.status_code, "stale")
        self.assertEqual(status.status_label, "长期低热/疑似占位")

    def test_print_skill_summary_counts_each_skill_once_per_job(self):
        matches = [
            JobMatch(
                company=Company(name="A"),
                job=Job(title="Python", skills=["Python", "Django", "Python"]),
            ),
            JobMatch(
                company=Company(name="B"),
                job=Job(title="Backend", skills=["Python", "Docker"]),
            ),
        ]
        output = StringIO()

        with redirect_stdout(output):
            _print_skill_summary(matches, position="Python工程师", top_n=3)

        text = output.getvalue()
        self.assertIn("技能汇总", text)
        self.assertIn("已排除搜索词本身: python", text)
        self.assertIn("后端框架", text)
        self.assertIn("工程化/部署", text)
        self.assertIn("Django", text)
        self.assertIn("Docker", text)
        self.assertNotIn("| Python", text)


if __name__ == "__main__":
    unittest.main()
