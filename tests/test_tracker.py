import unittest
from contextlib import redirect_stdout
from io import StringIO

from boss_analyzer.analyzers.career import advise_career
from boss_analyzer.analyzers.decision import evaluate_decisions
from boss_analyzer.analyzers.tracker import detect_changes, classify_lifecycle
from boss_analyzer.main import _print_career_advice, _print_decision_summary, _print_skill_summary
from boss_analyzer.models.company import Company
from boss_analyzer.models.decision import DecisionCriteria
from boss_analyzer.models.job import Job, UserProfile
from boss_analyzer.models.ranking import JobMatch
from boss_analyzer.models.snapshot import JobSnapshot
from boss_analyzer.utils.helpers import parse_salary


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

    def test_career_advice_recommends_salary_and_keyword_gaps(self):
        matches = [
            JobMatch(
                company=Company(name="A"),
                job=Job(
                    title="Python后端",
                    salary_min=12,
                    salary_max=18,
                    experience_min=1,
                    experience_max=3,
                    skills=["Python", "Django", "MySQL"],
                ),
            ),
            JobMatch(
                company=Company(name="B"),
                job=Job(
                    title="高级Python后端",
                    salary_min=22,
                    salary_max=32,
                    experience_min=3,
                    experience_max=5,
                    skills=["Python", "Redis", "Docker"],
                ),
            ),
            JobMatch(
                company=Company(name="C"),
                job=Job(
                    title="Python架构",
                    salary_min=35,
                    salary_max=50,
                    experience_min=5,
                    experience_max=8,
                    skills=["Python", "Kubernetes", "Redis"],
                ),
            ),
        ]
        profile = UserProfile(
            experience_years=4,
            skills=["Python", "Redis"],
            expected_salary_min=25,
            expected_salary_max=35,
        )

        advice = advise_career(matches, profile)

        self.assertEqual(advice.salary_jobs, 3)
        self.assertEqual(advice.level_label, "中级/独立贡献者")
        self.assertEqual(advice.recommended_salary_min, 27)
        self.assertEqual(advice.recommended_salary_max, 35)
        self.assertEqual(advice.target_fit_count, 1)
        self.assertIn("Python", advice.matched_keywords)
        self.assertIn("Docker", advice.gap_keywords)

    def test_print_career_advice_outputs_reference_sections(self):
        matches = [
            JobMatch(
                company=Company(name="A"),
                job=Job(
                    title="Python后端",
                    salary_min=20,
                    salary_max=30,
                    experience_min=3,
                    experience_max=5,
                    skills=["Python", "Redis"],
                ),
            ),
        ]
        output = StringIO()

        with redirect_stdout(output):
            _print_career_advice(matches, UserProfile(experience_years=4, skills=["Python"]))

        text = output.getvalue()
        self.assertIn("跳槽薪资与岗位档位参考", text)
        self.assertIn("建议谈薪区间", text)
        self.assertIn("薪资档位", text)
        self.assertIn("已匹配关键词", text)

    def test_parse_salary_ignores_day_rate_and_converts_yearly_salary(self):
        self.assertEqual(parse_salary("100-350元/天"), (0, 0))
        self.assertEqual(parse_salary("100-350/天"), (0, 0))
        self.assertEqual(parse_salary("12-18K"), (12, 18))
        self.assertEqual(parse_salary("24-36万/年"), (20, 30))

    def test_career_advice_ignores_implausible_salary_outliers(self):
        matches = [
            JobMatch(company=Company(name="A"), job=Job(title="实习", salary_min=4, salary_max=8)),
            JobMatch(company=Company(name="B"), job=Job(title="初级", salary_min=8, salary_max=12)),
            JobMatch(company=Company(name="C"), job=Job(title="中级", salary_min=12, salary_max=20)),
            JobMatch(company=Company(name="D"), job=Job(title="异常日薪", salary_min=100, salary_max=350)),
        ]

        advice = advise_career(matches)

        self.assertEqual(advice.salary_jobs, 3)
        self.assertEqual(advice.ignored_salary_jobs, 1)
        self.assertEqual(advice.salary_median, 10)
        self.assertFalse(any(band.label == "高薪档" for band in advice.salary_bands))

    def test_decision_downgrades_salary_hard_risk(self):
        matches = [
            JobMatch(
                company=Company(name="低薪公司", scale="100-499人", stage="不需要融资"),
                job=Job(
                    title="Go后端",
                    salary_min=18,
                    salary_max=25,
                    skills=["Go", "Redis", "MySQL"],
                    description="负责高并发服务",
                ),
            )
        ]
        profile = UserProfile(
            experience_years=6,
            skills=["Go", "Redis", "MySQL"],
            expected_salary_min=35,
            expected_salary_max=45,
        )

        decision = evaluate_decisions(matches, profile)[0]

        self.assertEqual(decision.recommendation, "D")
        self.assertIn("硬风险：薪资上限低于最低期望", decision.risks)

    def test_decision_reports_upskill_gap(self):
        matches = [
            JobMatch(
                company=Company(name="游戏公司", scale="500-999人", stage="C轮"),
                job=Job(
                    title="高级后端",
                    salary_min=35,
                    salary_max=50,
                    experience_min=5,
                    experience_max=10,
                    skills=["Go", "Redis", "Kubernetes", "Kafka"],
                    description="游戏后台，高并发，微服务",
                ),
            )
        ]
        profile = UserProfile(
            experience_years=8,
            skills=["Go", "Redis"],
            expected_salary_min=35,
            expected_salary_max=45,
        )
        criteria = DecisionCriteria(target_keywords=["游戏", "高并发"])

        decision = evaluate_decisions(matches, profile, criteria)[0]

        self.assertIn(decision.recommendation, ["A", "B"])
        self.assertIn("Kubernetes", decision.upskill_skills)
        self.assertIn("Kafka", decision.upskill_skills)
        self.assertTrue(any("技能直接匹配" in item for item in decision.strengths))

    def test_print_decision_summary_outputs_recommendation(self):
        matches = [
            JobMatch(
                company=Company(name="A"),
                job=Job(
                    title="Python后端",
                    salary_min=20,
                    salary_max=30,
                    skills=["Python", "Redis", "Docker"],
                    description="负责后端服务",
                ),
            ),
        ]
        profile = UserProfile(
            experience_years=4,
            skills=["Python", "Redis"],
            expected_salary_min=20,
            expected_salary_max=30,
        )
        output = StringIO()

        with redirect_stdout(output):
            _print_decision_summary(matches, profile)

        text = output.getvalue()
        self.assertIn("求职决策筛选", text)
        self.assertIn("Top 建议", text)
        self.assertIn("建议追问", text)


if __name__ == "__main__":
    unittest.main()
