import json
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from boss_analyzer.analyzers.decision import evaluate_decisions
from boss_analyzer.main import search_positions
from boss_analyzer.models.decision import DecisionCriteria
from boss_analyzer.models.job import UserProfile


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "gui.html"


def run_gui(host: str = "127.0.0.1", port: int = 8765) -> tuple[str, int]:
    server = _build_server(host, port)
    actual_host, actual_port = server.server_address
    print(f"Boss Analyzer GUI 已启动: http://{actual_host}:{actual_port}")
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGUI 服务已停止。")
    finally:
        server.server_close()
    return actual_host, actual_port


def _build_server(host: str, port: int) -> ThreadingHTTPServer:
    last_error = None
    for candidate in range(port, port + 20):
        try:
            return ThreadingHTTPServer((host, candidate), GuiHandler)
        except OSError as exc:
            last_error = exc
    raise RuntimeError(f"无法启动 GUI 服务，端口 {port}-{port + 19} 均不可用: {last_error}")


class GuiHandler(BaseHTTPRequestHandler):
    server_version = "BossAnalyzerGUI/1.0"

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"", "/"}:
            self._send_html(TEMPLATE_PATH.read_text(encoding="utf-8"))
            return
        if path == "/health":
            self._send_json({"ok": True})
            return
        self.send_error(404, "Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/search":
            self.send_error(404, "Not found")
            return

        try:
            payload = self._read_json()
            profile = profile_from_payload(payload)
            criteria = criteria_from_payload(payload)
            matches = search_positions(
                position=str(payload.get("position") or "").strip(),
                profile=profile,
                city=str(payload.get("city") or "全国").strip() or "全国",
                limit=parse_int(payload.get("limit"), 20, minimum=1, maximum=100),
                full_analysis=parse_bool(payload.get("full_analysis")),
                headless=True,
                fast=parse_bool(payload.get("fast"), default=True),
                output_format="none",
            )
            decisions = evaluate_decisions(matches, profile=profile, criteria=criteria)
            self._send_json({
                "ok": True,
                "count": len(decisions),
                "decisions": [decision_to_dict(item) for item in decisions],
            })
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def log_message(self, fmt, *args):
        return

    def _read_json(self) -> dict[str, Any]:
        length = parse_int(self.headers.get("Content-Length"), 0, minimum=0, maximum=2_000_000)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        if not str(data.get("position") or "").strip():
            raise ValueError("请填写岗位关键词")
        return data

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict[str, Any], status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def profile_from_payload(payload: dict[str, Any]) -> UserProfile:
    return UserProfile(
        experience_years=parse_int(payload.get("experience_years"), 0, minimum=0, maximum=60),
        skills=parse_list(payload.get("skills")),
        education=str(payload.get("education") or "").strip(),
        expected_salary_min=parse_int(payload.get("salary_min"), 0, minimum=0, maximum=500),
        expected_salary_max=parse_int(payload.get("salary_max"), 0, minimum=0, maximum=500),
    )


def criteria_from_payload(payload: dict[str, Any]) -> DecisionCriteria:
    return DecisionCriteria(
        preferred_cities=parse_list(payload.get("preferred_cities")),
        rejected_keywords=parse_list(payload.get("reject_keywords")) or ["外包", "驻场", "外派"],
        cautious_keywords=parse_list(payload.get("caution_keywords")) or ["996", "大小周", "抗压", "狼性"],
        target_keywords=parse_list(payload.get("target_keywords")),
    )


def decision_to_dict(decision) -> dict[str, Any]:
    result = asdict(decision) if is_dataclass(decision) else dict(decision)
    result["company"] = asdict(decision.company)
    result["job"] = asdict(decision.job)
    return result


def parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        text = str(value or "")
        items = text.replace("，", ",").replace("、", ",").split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: Any, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number
