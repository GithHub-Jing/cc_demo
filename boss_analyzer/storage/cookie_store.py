import json
import logging
from pathlib import Path

_COOKIE_FILE = Path.home() / ".config" / "boss_analyzer" / "cookies.json"
logger = logging.getLogger(__name__)


def cookie_file_path() -> Path:
    return _COOKIE_FILE


def has_cookies() -> bool:
    return _COOKIE_FILE.exists() and _COOKIE_FILE.stat().st_size > 10


def load_cookies() -> dict:
    if not has_cookies():
        return {}
    try:
        with open(_COOKIE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取 Cookie 文件失败: {e}")
        return {}


def save_cookies(cookies: dict) -> None:
    _COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    logger.info(f"Cookie 已保存: {_COOKIE_FILE}")


def extract_cookies_from_browser(page) -> dict:
    """Extract cookies from DrissionPage across supported API versions."""
    try:
        raw = page.cookies(as_dict=True)
    except TypeError:
        raw = page.cookies(all_domains=True, all_info=True)

    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if v}

    cookies = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if name and value:
            cookies[name] = value
    return cookies


def save_cookies_from_browser(page) -> dict:
    """Extract cookies from a DrissionPage browser session and persist them."""
    try:
        cookies = extract_cookies_from_browser(page)
        if cookies:
            save_cookies(cookies)
        return cookies
    except Exception as e:
        logger.error(f"提取浏览器 Cookie 失败: {e}")
        return {}
