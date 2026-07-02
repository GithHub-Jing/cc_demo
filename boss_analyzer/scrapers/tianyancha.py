import re
from typing import Optional
from DrissionPage import ChromiumPage, ChromiumOptions
from boss_analyzer.scrapers.base import BaseScraper
from boss_analyzer.models.company import Company
from boss_analyzer.utils.helpers import random_delay, parse_capital, logger


class TianyanchaScraper(BaseScraper):

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
            return self._scrape_company(query)
        except Exception as e:
            self.logger.error(f"天眼查采集失败: {e}")
            return {}
        finally:
            self._close_browser()

    def _scrape_company(self, company_name: str) -> dict:
        self.logger.info(f"天眼查搜索: {company_name}")
        self._page.get(f"https://www.tianyancha.com/search?key={company_name}")
        random_delay()

        result_link = self._page.ele("css:.search-result-single a[href*='/company/']", timeout=8)
        if not result_link:
            result_link = self._page.ele("css:a[href*='/company/']", timeout=5)
        if not result_link:
            self.logger.warning(f"天眼查未找到公司: {company_name}")
            return {}

        href = result_link.attr("href")
        if not href.startswith("http"):
            href = f"https://www.tianyancha.com{href}"

        self._page.get(href)
        random_delay()

        data = {}
        data["tianyancha_verified"] = True

        data["business_status"] = self._extract_text(
            "css:.info-value, .status, .tag-common",
            keywords=["存续", "在业", "开业", "迁出", "注销", "吊销"]
        )

        data["legal_representative"] = self._extract_text(
            "css:.humancompany .name, .legal-person .name, a[href*='/human/']"
        )

        capital_text = self._extract_field("注册资本")
        data["registered_capital"] = capital_text

        actual_text = self._extract_field("实缴资本")
        data["actual_capital"] = actual_text

        data["penalties"] = self._count_items("行政处罚")
        data["lawsuits"] = self._count_items("法律诉讼") + self._count_items("开庭公告")
        data["risk_count"] = self._count_risk_items()

        self.logger.info(
            f"天眼查结果: 状态={data.get('business_status', '未知')}, "
            f"处罚={data['penalties']}, 诉讼={data['lawsuits']}, 风险={data['risk_count']}"
        )
        return data

    def _extract_text(self, selector: str, keywords: list[str] = None) -> str:
        els = self._page.eles(selector, timeout=3)
        for el in els:
            text = el.text.strip()
            if not text:
                continue
            if keywords:
                for kw in keywords:
                    if kw in text:
                        return text
            else:
                return text
        return ""

    def _extract_field(self, field_name: str) -> str:
        els = self._page.eles("css:td, .detail-list span, .info-col", timeout=3)
        for i, el in enumerate(els):
            if field_name in el.text:
                next_el = els[i + 1] if i + 1 < len(els) else None
                if next_el:
                    return next_el.text.strip()
                val = el.text.replace(field_name, "").strip(":： \t")
                if val:
                    return val
        return ""

    def _count_items(self, section_name: str) -> int:
        els = self._page.eles("css:.count, .total, .tab-count, .badge", timeout=3)
        for el in els:
            parent = el.parent()
            if parent and section_name in parent.text:
                m = re.search(r"(\d+)", el.text)
                if m:
                    return int(m.group(1))
        return 0

    def _count_risk_items(self) -> int:
        risk_el = self._page.ele("css:.risk-detail .total, .risk-count, [class*='risk'] .count", timeout=3)
        if risk_el:
            m = re.search(r"(\d+)", risk_el.text)
            if m:
                return int(m.group(1))
        risk_tabs = self._page.eles("css:.risk-tab .count, .risk-label .num", timeout=3)
        total = 0
        for el in risk_tabs:
            m = re.search(r"(\d+)", el.text)
            if m:
                total += int(m.group(1))
        return total

    def update_company(self, company: Company) -> Company:
        data = self.scrape(company.full_name or company.name)
        if not data:
            return company
        company.tianyancha_verified = data.get("tianyancha_verified", False)
        if data.get("business_status"):
            company.business_status = data["business_status"]
        if data.get("legal_representative"):
            company.legal_representative = data["legal_representative"]
        if data.get("registered_capital"):
            company.registered_capital = data["registered_capital"]
        if data.get("actual_capital"):
            company.actual_capital = data["actual_capital"]
        company.penalties = data.get("penalties", 0)
        company.lawsuits = data.get("lawsuits", 0)
        company.risk_count = data.get("risk_count", 0)
        return company
