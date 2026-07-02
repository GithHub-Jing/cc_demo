import re
import time
from typing import Optional
from urllib.parse import quote
from DrissionPage import ChromiumPage, ChromiumOptions
from boss_analyzer.scrapers.base import BaseScraper
from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job
from boss_analyzer.utils.helpers import (
    random_delay, fast_random_delay, parse_salary, parse_experience, logger,
)
from boss_analyzer.config import MAX_JOBS_TO_SCRAPE

_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_BASE = "https://www.zhipin.com"


class BossScraper(BaseScraper):

    def __init__(self, headless: bool = True, fast: bool = False):
        super().__init__()
        self.headless = headless
        self.fast = fast
        self._page: Optional[ChromiumPage] = None

    def _delay(self):
        fast_random_delay() if self.fast else random_delay()

    def _init_browser(self):
        if self._page:
            return
        opts = ChromiumOptions()
        opts.auto_port()  # Avoid port conflicts with existing Chrome instances
        opts.set_browser_path(_CHROME_PATH)
        if self.headless:
            opts.headless()
        opts.set_argument("--disable-blink-features=AutomationControlled")
        opts.set_argument("--no-sandbox")
        opts.set_argument("--disable-gpu")
        opts.set_argument("--disable-dev-shm-usage")

        last_err = None
        for attempt in range(3):
            try:
                self._page = ChromiumPage(addr_or_opts=opts)
                return
            except Exception as e:
                last_err = e
                logger.warning(f"浏览器启动失败 (尝试 {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(2)
        raise RuntimeError(f"无法启动 Chrome，请确认已安装 Google Chrome: {last_err}")

    def _close_browser(self):
        if self._page:
            try:
                self._page.quit()
            except Exception:
                pass
            self._page = None

    # ------------------------------------------------------------------ #
    #  public
    # ------------------------------------------------------------------ #

    def scrape(self, query: str) -> dict:
        try:
            self._init_browser()
            company = (
                self._scrape_company_by_url(query)
                if query.startswith("http")
                else self._scrape_company_by_name(query)
            )
            if not company:
                return {"company": None, "jobs": []}
            jobs = self._scrape_jobs(company)
            return {"company": company, "jobs": jobs}
        finally:
            self._close_browser()

    def search_jobs_by_position(
        self,
        position: str,
        city_code: str = "100010000",
        limit: int = 20,
    ) -> list:
        self._init_browser()
        url = f"{_BASE}/web/geek/job?query={quote(position)}&city={city_code}"
        self.logger.info(f"搜索岗位: {position} (city={city_code})")
        self._page.get(url)
        self._delay()
        self._log_page_state("搜索岗位页面")

        if self._is_blocked():
            self.logger.warning("页面被拦截（登录墙/验证码），建议使用 --no-headless 手动完成验证后重试")
            return []

        # 多选择器候选，依次尝试
        cards = []
        for sel in [
            "css:.job-card-wrapper",
            "css:.job-list-box li",
            "css:[class*='job-card']",
            "css:.search-job-result li",
        ]:
            cards = self._page.eles(sel)
            if cards:
                self.logger.debug(f"使用选择器 {sel!r} 找到 {len(cards)} 张卡片")
                break

        if not cards:
            # 诊断：输出页面关键信息帮助排查
            try:
                body_text = (self._page.ele("css:body", timeout=2) or type("", (), {"text": ""})()).text or ""
                snippet = body_text[:300].replace("\n", " ")
                self.logger.warning(f"未找到岗位卡片，页面内容片段: {snippet}")
            except Exception:
                pass
            self.logger.warning(
                "未找到岗位卡片。可能原因：\n"
                "  1. 该城市暂无该岗位结果\n"
                "  2. 触发了安全验证 → 使用 --no-headless 手动完成验证\n"
                "  3. 页面结构变化 → 开启 -v 查看详细日志"
            )
            return []

        self.logger.info(f"找到 {len(cards)} 张岗位卡片")
        results = []
        for card in cards[:limit]:
            try:
                pair = self._parse_search_card(card)
                if pair:
                    results.append(pair)
            except Exception as e:
                self.logger.debug(f"解析搜索卡片失败: {e}")
        return results

    # ------------------------------------------------------------------ #
    #  company lookup
    # ------------------------------------------------------------------ #

    def _scrape_company_by_name(self, name: str) -> Optional[Company]:
        self.logger.info(f"搜索公司: {name}")
        encoded = quote(name)

        # 策略1: 公司名录页
        company = self._search_company_directory(encoded, name)
        if company:
            return company

        # 策略2: 岗位搜索页提取公司链接
        self._page.get(f"{_BASE}/web/geek/job?query={encoded}&city=100010000")
        self._delay()
        self._log_page_state("岗位搜索页")

        if self._is_blocked():
            self.logger.warning("检测到登录墙/验证码，建议使用 --no-headless 手动登录后重试")
            return None

        link = self._find_company_link(name)
        if not link:
            self.logger.warning(f"未找到公司: {name}，建议直接传入 Boss直聘公司页面 URL")
            return None

        return self._scrape_company_by_url(link)

    def _search_company_directory(self, encoded: str, raw_name: str) -> Optional[Company]:
        url = f"{_BASE}/gongsimingdan/?query={encoded}"
        self.logger.debug(f"尝试公司名录: {url}")
        self._page.get(url)
        self._delay()
        self._log_page_state("公司名录页")

        if self._is_blocked():
            return None

        link = self._find_company_link(raw_name)
        if link:
            self.logger.info(f"名录页找到公司链接: {link}")
            return self._scrape_company_by_url(link)
        return None

    def _find_company_link(self, name: str) -> Optional[str]:
        """按优先级查找 /gongsi/ 链接：精确匹配 > 模糊匹配 > 第一个"""
        all_links = self._page.eles("css:a[href*='/gongsi/']")
        if not all_links:
            self.logger.debug("页面上没有 /gongsi/ 链接")
            return None

        best = None
        for el in all_links:
            try:
                href = el.attr("href") or ""
                text = el.text.strip()
                if not href:
                    continue
                full = href if href.startswith("http") else f"{_BASE}{href}"
                if name in text:          # 精确匹配
                    self.logger.debug(f"精确匹配: {text} -> {full}")
                    return full
                if best is None and any(c in text for c in name):  # 模糊匹配
                    best = full
            except Exception:
                pass

        if best:
            self.logger.debug(f"模糊匹配公司链接: {best}")
            return best

        # 最后兜底：第一个 /gongsi/ 链接
        try:
            href = all_links[0].attr("href") or ""
            full = href if href.startswith("http") else f"{_BASE}{href}"
            self.logger.debug(f"兜底取第一个公司链接: {full}")
            return full
        except Exception:
            return None

    def _scrape_company_by_url(self, url: str) -> Optional[Company]:
        self.logger.info(f"采集公司页面: {url}")
        self._page.get(url)
        self._delay()
        self._log_page_state("公司详情页")

        if self._is_blocked():
            self.logger.warning("公司页面被拦截")
            return None

        company = Company(name="", boss_url=url)

        # 公司名 - 多选择器回退
        for sel in ["css:.company-name", "css:h1.title", "css:.name", "css:h1"]:
            el = self._page.ele(sel, timeout=3)
            if el and el.text.strip():
                company.name = el.text.strip()
                break

        # 基本信息项
        for sel in ["css:.res-industry", "css:.sider-company p",
                    "css:.company-info-item", "css:.company-info li",
                    "css:[class*='info-item']"]:
            for item in self._page.eles(sel):
                text = item.text.strip()
                if text:
                    self._parse_info_item(company, text)

        # 标签
        company.tags = [
            t.text.strip()
            for t in self._page.eles("css:.company-tag, .tag-item, .label-text")
            if t.text.strip()
        ]

        # 简介
        for sel in ["css:.company-profile-content", "css:.job-sec-text", "css:.text-fold"]:
            el = self._page.ele(sel, timeout=3)
            if el and el.text.strip():
                company.description = el.text.strip()
                break

        if not company.full_name:
            company.full_name = company.name

        # 公司名是验证码页面的标志性文本，视为被拦截
        _CAPTCHA_NAMES = {"安全验证", "验证", "请完成验证", "人机验证"}
        if not company.name or company.name in _CAPTCHA_NAMES:
            self.logger.warning(
                "公司页面触发安全验证（CAPTCHA），无法继续采集。\n"
                "解决方法：使用 --no-headless 参数，在弹出的浏览器中手动完成验证后重试。"
            )
            return None

        self.logger.info(f"采集到公司: {company.name} ({company.industry}, {company.scale})")
        return company

    # ------------------------------------------------------------------ #
    #  job scraping
    # ------------------------------------------------------------------ #

    def _scrape_jobs(self, company: Company) -> list:
        self.logger.info("采集岗位列表...")
        job_url = company.boss_url

        job_cards = self._page.eles("css:.job-card-wrapper, .job-list li")
        if not job_cards:
            self._page.get(job_url)
            self._delay()
            job_cards = self._page.eles("css:.job-card-wrapper, .job-list li")

        jobs = []
        for card in job_cards[:MAX_JOBS_TO_SCRAPE]:
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

        for sel in ["css:.job-name", "css:.job-title", "css:.position-head h3"]:
            el = card.ele(sel, timeout=2)
            if el and el.text.strip():
                job.title = el.text.strip()
                break
        if not job.title:
            return None

        for sel in ["css:.salary", "css:.job-limit .red"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.salary_min, job.salary_max = parse_salary(el.text.strip())
                break

        for el in card.eles("css:.job-info .tag-list li, .job-limit span, .tag-list li"):
            text = el.text.strip()
            if "经验" in text or re.search(r"\d+年", text):
                job.experience_min, job.experience_max = parse_experience(text)
            elif any(e in text for e in ["博士", "硕士", "本科", "大专", "高中", "学历不限"]):
                job.education = text

        job.skills = [
            s.text.strip()
            for s in card.eles("css:.tag-list .tag, .skill-labels span, .job-tags span")
            if s.text.strip()
        ]

        for sel in ["css:.info-public em", "css:.boss-name"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.hr_name = el.text.strip()
                break

        for sel in ["css:.info-public .name", "css:.boss-title"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.hr_title = el.text.strip()
                break

        for sel in ["css:.boss-active-time", "css:.info-public .time"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.hr_active_time = el.text.strip()
                break

        link_el = card.ele("tag:a[href*='/job_detail/']", timeout=2)
        if link_el:
            href = link_el.attr("href")
            job.job_url = href if href.startswith("http") else f"{_BASE}{href}"

        return job

    def _parse_search_card(self, card) -> Optional[tuple]:
        job = Job(title="")

        for sel in ["css:.job-name", "css:.job-title"]:
            el = card.ele(sel, timeout=2)
            if el and el.text.strip():
                job.title = el.text.strip()
                break
        if not job.title:
            return None

        for sel in ["css:.salary", "css:.job-salary"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.salary_min, job.salary_max = parse_salary(el.text.strip())
                break

        for el in card.eles("css:.job-info .tag-list li, .job-limit span, .tag-list li"):
            text = el.text.strip()
            if "经验" in text or re.search(r"\d+年", text):
                job.experience_min, job.experience_max = parse_experience(text)
            elif any(e in text for e in ["博士", "硕士", "本科", "大专", "高中", "学历不限"]):
                job.education = text

        job.skills = [
            s.text.strip()
            for s in card.eles("css:.tag-list .tag, .skill-labels span")
            if s.text.strip()
        ]

        for sel in ["css:.job-area", "css:.city-name"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.location = el.text.strip()
                break

        link_el = card.ele("tag:a[href*='/job_detail/']", timeout=2)
        if link_el:
            href = link_el.attr("href")
            job.job_url = href if href.startswith("http") else f"{_BASE}{href}"

        for sel in ["css:.info-public em", "css:.boss-name"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.hr_name = el.text.strip()
                break

        for sel in ["css:.boss-active-time", "css:.active-time"]:
            el = card.ele(sel, timeout=2)
            if el:
                job.hr_active_time = el.text.strip()
                break

        company = Company(name="")
        for sel in ["css:.company-name", "css:.job-card-right .name"]:
            el = card.ele(sel, timeout=2)
            if el and el.text.strip():
                company.name = el.text.strip()
                break
        if not company.name:
            return None
        company.full_name = company.name

        for el in card.eles("css:.company-tag-box li, .res-industry, .company-tag li"):
            text = el.text.strip()
            if re.search(r"\d+.*人", text) or "人以上" in text:
                company.scale = text
            elif text and not company.industry:
                company.industry = text

        company_link = card.ele("tag:a[href*='/gongsi/']", timeout=2)
        if company_link:
            href = company_link.attr("href")
            company.boss_url = href if href.startswith("http") else f"{_BASE}{href}"

        return company, job

    def scrape_job_detail(self, job: Job) -> Job:
        if not job.job_url:
            return job
        self.logger.debug(f"采集岗位详情: {job.title}")
        self._page.get(job.job_url)
        self._delay()

        for sel in ["css:.job-detail-section .text", "css:.job-sec-text", "css:.text"]:
            el = self._page.ele(sel, timeout=5)
            if el and el.text.strip():
                job.description = el.text.strip()
                break

        for sel in ["css:.boss-active-time", "css:.boss-info-attr span"]:
            el = self._page.ele(sel, timeout=3)
            if el:
                job.hr_active_time = el.text.strip()
                break

        return job

    # ------------------------------------------------------------------ #
    #  helpers
    # ------------------------------------------------------------------ #

    def _is_blocked(self) -> bool:
        url = self._page.url or ""
        title = self._page.title or ""

        if any(kw in url for kw in ["/web/user/", "login", "verify", "captcha"]):
            return True
        if any(kw in title for kw in ["登录", "验证", "Login", "安全验证"]):
            return True
        if self._page.ele("css:.login-form, .verify-container, #captcha", timeout=1):
            return True

        # Boss直聘安全验证页面 URL 不变，只有 body 内容变化
        try:
            body = self._page.ele("css:body", timeout=1)
            if body:
                text = body.text or ""
                if any(kw in text for kw in ["安全验证", "请完成验证", "滑动验证", "人机验证", "拖动滑块"]):
                    return True
        except Exception:
            pass

        return False

    def _log_page_state(self, label: str):
        try:
            self.logger.debug(f"[{label}] URL={self._page.url} | 标题={self._page.title}")
        except Exception:
            pass

    def _parse_info_item(self, company: Company, text: str):
        if any(kw in text for kw in [
            "融资", "已上市", "不需要融资", "未融资",
            "天使", "A轮", "B轮", "C轮", "D轮", "E轮", "上市"
        ]):
            company.stage = text
        elif re.search(r"\d+\s*[-~]\s*\d+\s*人", text) or re.search(r"\d+\s*人以上", text):
            company.scale = text
        elif "成立" in text or re.match(r"\d{4}[-/年]", text):
            company.founded_date = text
        elif "注册资本" in text or "注册资金" in text:
            company.registered_capital = text
        elif ("法" in text and "代表" in text) or "法人" in text:
            company.legal_representative = re.sub(r"(法.*代表|法人)[：:]*\s*", "", text).strip()
        elif not company.industry and len(text) < 30 and not re.search(r"\d{4}", text):
            # 兜底：短文本作为行业信息
            company.industry = text
