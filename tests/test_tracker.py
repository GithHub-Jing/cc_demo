import unittest

from boss_analyzer.analyzers.tracker import detect_changes
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


if __name__ == "__main__":
    unittest.main()
