import re
import json
from typing import Optional
from DrissionPage import ChromiumPage, ChromiumOptions
from boss_analyzer.scrapers.base import BaseScraper
from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job
from boss_analyzer.utils.helpers import (
    random_delay, parse_salary, parse_experience, logger,
)
from boss_analyzer.config import MAX_JOBS_TO_SCRAPE


class BossScraper(BaseScraper):

    def __init__(self, headless: bool = True):
        super().__init__()
        self.headless = headless
        self._page: Optional[ChromiumPage] = None

    def _init_browser(self):
        if self._page:
            return
        opts = ChromiumOptions()
        if self.headless:
            opts.headless()
        opts.set_argument("--disable-blink-features=AutomationControlled")
        opts.set_argument("--no-sandbox")
        opts.set_argument("--disable-gpu")
        self._page = ChromiumPage(addr_or_opts=opts)

    def _close_browser(self):
        if self._page:
            try:
                self._page.quit()
            except Exception:
                pass
            self._page = None

    def scrape(self, query: str) -> dict:
        try:
            self._init_browser()
            if query.startswith("http"):
                company = self._scrape_company_by_url(query)
            else:
                company = self._scrape_company_by_name(query)
            if not company:
                return {"company": None, "jobs": []}
            jobs = self._scrape_jobs(company)
            return {"company": company, "jobs": jobs}
        finally:
            self._close_browser()

    def _scrape_company_by_name(self, name: str) -> Optional[Company]:
        self.logger.info(f"搜索公司: {name}")
        self._page.get(f"https://www.zhipin.com/web/geek/job?query={name}&city=100010000")
        random_delay()

        company_cards = self._page.eles("css:.company-info")
        if not company_cards:
            company_cards = self._page.eles("css:.company-name")

        target_link = None
        for card in company_cards:
            text = card.text
            if name in text:
                link = card.ele("tag:a", timeout=2)
                if link:
                    href = link.attr("href")
                    if href and "/gongsi/" in href:
                        target_link = href if href.startswith("http") else f"https://www.zhipin.com{href}"
                        break

        if not target_link:
            links = self._page.eles("css:a[href*='/gongsi/']")
            if links:
                href = links[0].attr("href")
                target_link = href if href.startswith("http") else f"https://www.zhipin.com{href}"

        if not target_link:
            self.logger.warning(f"未找到公司: {name}")
            return None

        return self._scrape_company_by_url(target_link)

    def _scrape_company_by_url(self, url: str) -> Optional[Company]:
        self.logger.info(f"采集公司页面: {url}")
        self._page.get(url)
        random_delay()

        company = Company(name="", boss_url=url)

        name_el = self._page.ele("css:.company-name, .name, h1.title", timeout=5)
        if name_el:
            company.name = name_el.text.strip()

        info_items = self._page.eles("css:.res-industry, .sider-company p, .company-info-item")
        for item in info_items:
            text = item.text.strip()
            if not text:
                continue
            self._parse_info_item(company, text)

        tag_els = self._page.eles("css:.company-tag, .tag-item, .label-text")
        company.tags = [t.text.strip() for t in tag_els if t.text.strip()]

        desc_el = self._page.ele("css:.company-profile-content, .job-sec-text, .text-fold", timeout=3)
        if desc_el:
            company.description = desc_el.text.strip()

        if not company.full_name:
            company.full_name = company.name

        self.logger.info(f"采集到公司: {company.name} ({company.industry}, {company.scale})")
        return company

    def _parse_info_item(self, company: Company, text: str):
        if any(kw in text for kw in ["融资", "已上市", "不需要融资", "未融资", "天使", "A轮", "B轮", "C轮", "D轮"]):
            company.stage = text
        elif any(kw in text for kw in ["人", "员工"]):
            if re.search(r"\d+.*人", text):
                company.scale = text
        elif any(kw in text for kw in ["互联网", "科技", "金融", "教育", "医疗", "制造", "电商", "游戏", "通信"]):
            company.industry = text
        elif "成立" in text or re.match(r"\d{4}[-/年]", text):
            company.founded_date = text
        elif "注册资本" in text:
            company.registered_capital = text
        elif "法" in text and "代表" in text:
            company.legal_representative = re.sub(r"法.*代表[：:]*\s*", "", text)

    def _scrape_jobs(self, company: Company) -> list[Job]:
        self.logger.info("采集岗位列表...")

        job_url = company.boss_url
        if "/gongsi/" in job_url and not job_url.endswith(".html"):
            job_url = job_url.rstrip("/") + "/"

        job_cards = self._page.eles("css:.job-card-wrapper, .job-list li, .position-list .job-primary")
        if not job_cards:
            self._page.get(job_url)
            random_delay()
            job_cards = self._page.eles("css:.job-card-wrapper, .job-list li, .position-list .job-primary")

        jobs = []
        for i, card in enumerate(job_cards[:MAX_JOBS_TO_SCRAPE]):
            try:
                job = self._parse_job_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                self.logger.debug(f"解析岗位卡片失败: {e}")

        self.logger.info(f"采集到 {len(jobs)} 个岗位")
        return jobs

    def _parse_job_card(self, card) -> Optional[Job]:
        job = Job(title="")

        title_el = card.ele("css:.job-name, .job-title, .position-head h3", timeout=2)
        if title_el:
            job.title = title_el.text.strip()

        if not job.title:
            return None

        salary_el = card.ele("css:.salary, .job-limit .red, .position-head .salary", timeout=2)
        if salary_el:
            salary_text = salary_el.text.strip()
            job.salary_min, job.salary_max = parse_salary(salary_text)

        info_els = card.eles("css:.job-info .tag-list li, .position-head p, .job-limit span")
        for el in info_els:
            text = el.text.strip()
            if "经验" in text or "年" in text:
                job.experience_min, job.experience_max = parse_experience(text)
            elif any(edu in text for edu in ["博士", "硕士", "本科", "大专", "高中", "学历不限"]):
                job.education = text

        skill_els = card.eles("css:.tag-list .tag, .skill-labels span, .job-tags span")
        job.skills = [s.text.strip() for s in skill_els if s.text.strip()]

        hr_el = card.ele("css:.info-public em, .job-info .boss-name", timeout=2)
        if hr_el:
            job.hr_name = hr_el.text.strip()

        hr_title_el = card.ele("css:.info-public .name, .job-info .boss-title", timeout=2)
        if hr_title_el:
            job.hr_title = hr_title_el.text.strip()

        active_el = card.ele("css:.boss-active-time, .info-public .time", timeout=2)
        if active_el:
            job.hr_active_time = active_el.text.strip()

        link_el = card.ele("tag:a[href*='/job_detail/']", timeout=2)
        if link_el:
            href = link_el.attr("href")
            job.job_url = href if href.startswith("http") else f"https://www.zhipin.com{href}"

        return job

    def scrape_job_detail(self, job: Job) -> Job:
        if not job.job_url:
            return job
        self.logger.debug(f"采集岗位详情: {job.title}")
        self._page.get(job.job_url)
        random_delay()

        desc_el = self._page.ele("css:.job-detail-section .text, .job-sec-text, .text", timeout=5)
        if desc_el:
            job.description = desc_el.text.strip()

        active_el = self._page.ele("css:.boss-active-time, .boss-info-attr span", timeout=3)
        if active_el:
            job.hr_active_time = active_el.text.strip()

        return job
