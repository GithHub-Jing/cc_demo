"""
Boss直聘 HTTP API client.

Uses the internal JSON API (inspired by jackwener/boss-cli):
  GET /wapi/zpgeek/search/joblist.json

Requires a valid cookie session. Call `boss_login` (the CLI `login` subcommand)
once to harvest cookies via a real browser session; subsequent runs reuse them.
"""
import time
import random
from typing import Optional
import requests

from boss_analyzer.models.company import Company
from boss_analyzer.models.job import Job
from boss_analyzer.storage.cookie_store import has_cookies, load_cookies, cookie_file_path
from boss_analyzer.utils.helpers import parse_salary, parse_experience, logger

_BASE = "https://www.zhipin.com"
_SEARCH_API = f"{_BASE}/wapi/zpgeek/search/joblist.json"

# API response codes
_CODE_OK = 0
_CODE_RATE_LIMITED = 9
_CODE_SESSION_EXPIRED = 37


class BossApiClient:
    """Thin wrapper around Boss直聘's internal search JSON API."""

    def __init__(self):
        self._session = requests.Session()
        self._ready = False

    def setup(self) -> bool:
        """Load persisted cookies. Returns True if cookies are available."""
        if not has_cookies():
            logger.info(
                f"未找到 Cookie 文件 ({cookie_file_path()})。\n"
                "请先运行: python -m boss_analyzer login\n"
                "在弹出的浏览器中登录 Boss直聘，Cookie 将自动保存供后续使用。"
            )
            return False
        cookies = load_cookies()
        for name, value in cookies.items():
            self._session.cookies.set(name, value, domain=".zhipin.com")
        self._ready = True
        logger.debug(f"已加载 {len(cookies)} 个 Cookie")
        return True

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    #  public
    # ------------------------------------------------------------------

    def search_jobs(
        self,
        query: str,
        city_code: str = "100010000",
        limit: int = 20,
    ) -> list:
        """
        Returns list of (Company, Job) tuples.
        Fetches multiple pages until `limit` is reached.
        """
        if not self._ready:
            return []

        results = []
        page = 1
        page_size = min(15, limit)

        while len(results) < limit:
            data = self._fetch_page(query, city_code, page, page_size)
            error = data.get("error")

            if error == "session_expired":
                logger.warning("Cookie 已过期，请重新运行 `python -m boss_analyzer login` 刷新登录状态")
                break
            if error == "rate_limited":
                logger.warning("API 请求频率过高，等待后重试...")
                time.sleep(random.uniform(5, 10))
                continue
            if error:
                logger.warning(f"API 返回错误: {error}")
                break

            job_list = data.get("jobList", [])
            if not job_list:
                break

            parsed = self._parse_job_list(job_list)
            results.extend(parsed)

            if not data.get("hasMore") or len(parsed) < page_size:
                break

            page += 1
            time.sleep(random.uniform(0.5, 1.5))

        return results[:limit]

    # ------------------------------------------------------------------
    #  internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        bst = self._session.cookies.get("bst", "")
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "zp_token": bst,
            "sec-ch-ua": '"Chromium";v="145", "Not(A:Brand";v="99", "Google Chrome";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://www.zhipin.com/web/geek/job",
        }

    def _fetch_page(
        self,
        query: str,
        city_code: str,
        page: int,
        page_size: int,
    ) -> dict:
        params = {
            "query": query,
            "city": city_code,
            "page": page,
            "pageSize": page_size,
            "ka": f"page-{page}",
        }
        try:
            resp = self._session.get(
                _SEARCH_API,
                params=params,
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            return {"jobList": [], "hasMore": False, "error": str(e)}

        code = body.get("code", -1)
        if code == _CODE_SESSION_EXPIRED:
            return {"jobList": [], "hasMore": False, "error": "session_expired"}
        if code == _CODE_RATE_LIMITED:
            return {"jobList": [], "hasMore": False, "error": "rate_limited"}
        if code != _CODE_OK:
            return {"jobList": [], "hasMore": False, "error": f"api_{code}"}

        zp = body.get("zpData", {})
        return {
            "jobList": zp.get("jobList", []),
            "hasMore": zp.get("hasMore", False),
            "error": None,
        }

    def _parse_job_list(self, items: list) -> list:
        results = []
        for item in items:
            try:
                pair = self._parse_item(item)
                if pair:
                    results.append(pair)
            except Exception as e:
                logger.debug(f"解析 API 岗位条目失败: {e}")
        return results

    def _parse_item(self, item: dict) -> Optional[tuple]:
        job_name = item.get("jobName", "").strip()
        if not job_name:
            return None

        job = Job(title=job_name)
        job.salary_min, job.salary_max = parse_salary(
            item.get("salaryDesc") or item.get("salary", "")
        )
        job.experience_min, job.experience_max = parse_experience(
            item.get("jobExperience", "")
        )
        job.education = item.get("jobDegree", "")
        job.location = item.get("cityName", "")
        job.skills = item.get("skills", [])
        job.hr_name = item.get("bossName", "")
        job.hr_title = item.get("bossTitle", "")
        job.hr_active_time = (
            item.get("bossActiveTime")
            or item.get("activeTimeDesc")
            or item.get("bossOnline")
            or ""
        )
        description = (
            item.get("postDescription")
            or item.get("jobDesc")
            or item.get("jobLabels")
            or ""
        )
        if isinstance(description, list):
            description = " ".join(str(v) for v in description)
        job.description = str(description)

        # Boss 直聘 job URL
        enc_jid = item.get("encryptJobId", "")
        if enc_jid:
            lid = item.get("lid", "")
            sec_id = item.get("securityId", "")
            job.job_url = (
                f"{_BASE}/job_detail/{enc_jid}.html"
                f"?lid={lid}&securityId={sec_id}"
            )

        company_name = item.get("brandName", "").strip()
        if not company_name:
            return None

        company = Company(name=company_name)
        company.full_name = company_name
        company.scale = item.get("brandScaleName", "")
        company.industry = item.get("brandIndustry", "")
        company.stage = item.get("brandStageName", "")

        enc_bid = item.get("encryptBossId", "")
        if enc_bid:
            company.boss_url = f"{_BASE}/gongsi/{enc_bid}.html"

        return company, job
