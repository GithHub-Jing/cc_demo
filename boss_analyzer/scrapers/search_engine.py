import re
import requests
from typing import Optional
from bs4 import BeautifulSoup
from boss_analyzer.scrapers.base import BaseScraper
from boss_analyzer.models.company import Company
from boss_analyzer.utils.helpers import random_delay, logger
from boss_analyzer.config import USER_AGENTS, REQUEST_TIMEOUT


class SearchEngineScraper(BaseScraper):

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENTS[0],
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def scrape(self, query: str) -> dict:
        try:
            data = {}
            bing_results = self._search_bing(query)
            data["search_result_count"] = bing_results.get("total", 0)
            data["has_official_website"] = self._check_official_website(query, bing_results.get("items", []))
            data["multi_platform_presence"] = self._check_multi_platform(bing_results.get("items", []))
            data["news_count"] = self._search_news_count(query)
            self.logger.info(
                f"搜索引擎结果: 结果数={data['search_result_count']}, "
                f"官网={data['has_official_website']}, "
                f"多平台={data['multi_platform_presence']}, "
                f"新闻={data['news_count']}"
            )
            return data
        except Exception as e:
            self.logger.error(f"搜索引擎采集失败: {e}")
            return {}

    def _search_bing(self, query: str) -> dict:
        self.logger.info(f"必应搜索: {query}")
        try:
            resp = self._session.get(
                "https://www.bing.com/search",
                params={"q": query, "count": "20"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            random_delay()
            soup = BeautifulSoup(resp.text, "lxml")

            items = []
            for li in soup.select(".b_algo"):
                link_el = li.select_one("h2 a")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                title = link_el.get_text(strip=True)
                snippet_el = li.select_one(".b_caption p, .b_lineclamp2")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                items.append({"url": href, "title": title, "snippet": snippet})

            total_el = soup.select_one(".sb_count")
            total = 0
            if total_el:
                m = re.search(r"([\d,]+)", total_el.text.replace(",", ""))
                if m:
                    total = int(m.group(1))
            if not total:
                total = len(items)

            return {"items": items, "total": total}
        except Exception as e:
            self.logger.warning(f"必应搜索失败: {e}")
            return {"items": [], "total": 0}

    def _check_official_website(self, company_name: str, items: list[dict]) -> bool:
        official_patterns = [
            r"官网", r"官方网站", r"official",
            r"首页.*" + re.escape(company_name),
        ]
        for item in items[:10]:
            text = f"{item.get('title', '')} {item.get('snippet', '')}"
            for pattern in official_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return True
            url = item.get("url", "")
            if self._looks_like_corporate_site(url, company_name):
                return True
        return False

    def _looks_like_corporate_site(self, url: str, company_name: str) -> bool:
        skip_domains = [
            "baidu.com", "bing.com", "zhipin.com", "tianyancha.com",
            "qichacha.com", "lagou.com", "liepin.com", "51job.com",
            "zhaopin.com", "wikipedia.org", "baike.baidu.com",
        ]
        for domain in skip_domains:
            if domain in url:
                return False
        if re.search(r"\.(com|cn|com\.cn|net|org)/?$", url):
            return True
        return False

    def _check_multi_platform(self, items: list[dict]) -> bool:
        platforms = set()
        platform_domains = {
            "zhipin.com": "boss直聘", "lagou.com": "拉勾", "liepin.com": "猎聘",
            "51job.com": "前程无忧", "zhaopin.com": "智联招聘",
            "tianyancha.com": "天眼查", "qichacha.com": "企查查",
            "aiqicha.com": "爱企查",
            "weibo.com": "微博", "zhihu.com": "知乎",
            "douyin.com": "抖音", "xiaohongshu.com": "小红书",
        }
        for item in items:
            url = item.get("url", "")
            for domain, name in platform_domains.items():
                if domain in url:
                    platforms.add(name)
        return len(platforms) >= 3

    def _search_news_count(self, query: str) -> int:
        try:
            resp = self._session.get(
                "https://www.bing.com/news/search",
                params={"q": query},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            random_delay()
            soup = BeautifulSoup(resp.text, "lxml")
            news_items = soup.select(".news-card, .newsitem, article")
            return len(news_items)
        except Exception as e:
            self.logger.debug(f"新闻搜索失败: {e}")
            return 0

    def update_company(self, company: Company) -> Company:
        data = self.scrape(company.full_name or company.name)
        if not data:
            return company
        company.has_official_website = data.get("has_official_website", False)
        company.multi_platform_presence = data.get("multi_platform_presence", False)
        company.news_count = data.get("news_count", 0)
        company.search_result_count = data.get("search_result_count", 0)
        return company
