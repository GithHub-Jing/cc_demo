from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    title: str
    salary_min: int = 0
    salary_max: int = 0
    salary_unit: str = "月"
    experience_min: int = 0
    experience_max: int = 0
    education: str = ""
    skills: list[str] = field(default_factory=list)
    description: str = ""
    publish_time: str = ""
    hr_name: str = ""
    hr_title: str = ""
    hr_active_time: str = ""
    job_url: str = ""
    location: str = ""
    job_type: str = ""

    @property
    def salary_range_str(self) -> str:
        if self.salary_min and self.salary_max:
            return f"{self.salary_min}-{self.salary_max}K/{self.salary_unit}"
        return "薪资面议"


@dataclass
class UserProfile:
    experience_years: int = 0
    skills: list[str] = field(default_factory=list)
    education: str = ""
    expected_salary_min: int = 0
    expected_salary_max: int = 0
