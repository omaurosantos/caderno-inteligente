"""Smoke test of a published (or local) Caderno Inteligente deployment. Read-only: it never records data.

    python scripts/smoke_test.py --backend https://API.vercel.app --frontend https://APP.vercel.app
    python scripts/smoke_test.py --backend http://127.0.0.1:8000 --frontend http://127.0.0.1:4173 --expect-environment development

The only write-shaped request is a POST with a non-existent SKU, which the API must refuse (422, or 403 in read-only mode).
Uses only the Python standard library. Exit code 1 when any check fails.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

PROBE_SKU = "__SMOKE_TEST_INEXISTENTE__"
SECRET_PATTERNS = (re.compile(r"postgres(?:ql)?://", re.I), re.compile(r"DATABASE_URL"), re.compile(r"service_role", re.I))


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


# request(method, url, headers, body) -> Response
Requester = Callable[[str, str, dict[str, str], bytes | None], Response]


def http_request(method: str, url: str, headers: dict[str, str], body: bytes | None = None, timeout: float = 60) -> Response:
    request = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "caderno-smoke-test", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Response(response.status, {k.lower(): v for k, v in response.headers.items()}, response.read())
    except urllib.error.HTTPError as error:
        return Response(error.code, {k.lower(): v for k, v in error.headers.items()}, error.read())


@dataclass
class Check:
    area: str
    name: str
    ok: bool
    detail: str = ""


class Runner:
    def __init__(self, request: Requester):
        self.request = request
        self.checks: list[Check] = []

    def check(self, area: str, name: str, condition: bool, detail: str = "") -> bool:
        self.checks.append(Check(area, name, bool(condition), detail))
        return bool(condition)

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response | None:
        try:
            return self.request("GET", url, headers or {}, None)
        except Exception as error:  # network failure is reported as a failed check, not a crash
            self.check("rede", f"GET {url}", False, f"{type(error).__name__}: {error}")
            return None


def backend_checks(runner: Runner, backend: str, frontend: str | None = None, expect_environment: str | None = None,
                   expect_readonly: bool | None = None, expect_demo: bool | None = None) -> dict:
    api = backend.rstrip("/") + "/api"
    found: dict = {}

    health = runner.get(f"{api}/health")
    if health and runner.check("backend", "health responde 200", health.status == 200, f"status {health.status}"):
        body = health.json()
        runner.check("backend", "planilha empacotada disponível", body.get("source_available") is True)
        runner.check("backend", "persistência saudável", body.get("database") == "ok", f"{body.get('persistence')} / {body.get('database')}")
        runner.check("backend", "X-Request-ID presente", bool(health.headers.get("x-request-id")))
        runner.check("backend", "nosniff presente", health.headers.get("x-content-type-options") == "nosniff")

    system = runner.get(f"{api}/system")
    if system and runner.check("backend", "system responde 200", system.status == 200, f"status {system.status}"):
        info = system.json()
        runner.check("backend", "system sem dados de conexão", not any(p.search(system.text) for p in SECRET_PATTERNS))
        if expect_environment:
            runner.check("backend", f"APP_ENV = {expect_environment}", info.get("environment") == expect_environment, str(info.get("environment")))
        if expect_readonly is not None:
            runner.check("backend", f"WRITE_ENABLED = {not expect_readonly}", info.get("write_enabled") is (not expect_readonly), str(info.get("write_enabled")))
        if expect_demo is not None:
            runner.check("backend", f"DEMO_MODE = {expect_demo}", info.get("demo_mode") is expect_demo, str(info.get("demo_mode")))
        found["system"] = info

    overview = runner.get(f"{api}/overview")
    total = 0
    if overview and runner.check("dados", "overview responde 200", overview.status == 200):
        body = overview.json()
        total = body.get("total_skus", 0)
        runner.check("dados", "overview com SKUs", total > 0 and 0 <= body.get("prioritized", -1) <= total, f"{body.get('prioritized')} de {total}")

    priorities = runner.get(f"{api}/priorities")
    if priorities and runner.check("dados", "ranking responde 200", priorities.status == 200):
        rows = priorities.json()
        positions = [row["priority"] for row in rows]
        tiers = [row.get("urgency_tier") or 0 for row in rows]
        runner.check("dados", "ranking sequencial e ordenado por faixa", positions == list(range(1, len(rows) + 1)) and tiers == sorted(tiers), f"{len(rows)} SKUs")
        if rows:
            found["sku"] = rows[0]["sku"]

    if found.get("sku"):
        detail = runner.get(f"{api}/priorities/{quote(found['sku'], safe='')}")
        if detail and runner.check("dados", f"detalhe de {found['sku']} responde 200", detail.status == 200):
            runner.check("dados", "recomendação exige revisão humana", detail.json()["operational_recommendation"]["requires_human_review"] is True)
    missing = runner.get(f"{api}/priorities/{PROBE_SKU}")
    if missing:
        runner.check("dados", "SKU inexistente retorna 404", missing.status == 404, f"status {missing.status}")

    forecasts = runner.get(f"{api}/forecasts")
    if forecasts and runner.check("dados", "previsões respondem 200", forecasts.status == 200):
        items = forecasts.json()
        runner.check("dados", "uma previsão por SKU", not total or len(items) == total, f"{len(items)} de {total}")
        runner.check("dados", "toda recomendação exige revisão", all(item["operational_recommendation"]["requires_human_review"] for item in items))

    partners = runner.get(f"{api}/partners")
    if partners and runner.check("comercial", "parceiros respondem 200", partners.status == 200):
        items = partners.json().get("items", [])
        runner.check("comercial", "parceiros cadastrados", len(items) > 0, f"{len(items)} parceiros")
        if items:
            found["partner"] = items[0]["code"]
            code = quote(found["partner"], safe="")
            detail = runner.get(f"{api}/partners/{code}")
            rows = runner.get(f"{api}/partners/{code}/skus?limit=5")
            runner.check("comercial", f"detalhe do parceiro {found['partner']}", bool(detail) and detail.status == 200)
            runner.check("comercial", "matriz parceiro–SKU", bool(rows) and rows.status == 200)

    validation = runner.get(f"{api}/validation/summary")
    if validation and runner.check("validação", "central de validação responde 200", validation.status == 200, f"status {validation.status}"):
        body = validation.json()
        cases = body.get("frozen_cases", {})
        pending = cases.get("pending", 0)  # casos gravados antes do código que os atende (Etapa 15) não contam
        executed = cases.get("total", 0) - pending
        runner.check("validação", "casos congelados avaliados", executed >= 8 and cases.get("passed") == executed, f"{cases.get('passed')}/{executed} aprovados, {pending} pendentes")
        runner.check("validação", "planilha igual à congelada", cases.get("source_matches_frozen") is True)
        runner.check("validação", "nenhum comportamento seguro reprovado", not any(item["status"] == "reprovado" for item in body.get("safe_behavior", [])))

    runs = runner.get(f"{api}/runs")
    if runs:
        runner.check("persistência", "execuções respondem 200", runs.status == 200, f"status {runs.status}")

    try:
        probe = runner.request("POST", f"{api}/feedback", {"Content-Type": "application/json"},
                               json.dumps({"sku": PROBE_SKU, "action": "aceita"}).encode("utf-8"))
        allowed = {403} if expect_readonly else {403, 422}
        runner.check("segurança", "sondagem de escrita recusada (nada gravado)", probe.status in allowed, f"status {probe.status}")
    except Exception as error:
        runner.check("segurança", "sondagem de escrita", False, str(error))

    if frontend:
        origin = frontend.rstrip("/")
        preflight = {"Access-Control-Request-Method": "GET"}
        try:
            allowed = runner.request("OPTIONS", f"{api}/overview", {"Origin": origin, **preflight}, None)
            runner.check("segurança", "CORS aceita o frontend", allowed.headers.get("access-control-allow-origin") == origin,
                         allowed.headers.get("access-control-allow-origin", "sem cabeçalho"))
            evil = runner.request("OPTIONS", f"{api}/overview", {"Origin": "https://smoke-test.invalid", **preflight}, None)
            runner.check("segurança", "CORS recusa origem desconhecida", "access-control-allow-origin" not in evil.headers)
        except Exception as error:
            runner.check("segurança", "CORS", False, str(error))
    return found


def frontend_checks(runner: Runner, frontend: str, sku: str | None = None, partner: str | None = None) -> None:
    base = frontend.rstrip("/")
    paths = ["/", "/guia", "/prioridades", "/previsoes", "/validacao", "/execucoes?base=1&alvo=2", "/rota-inexistente"]
    if sku:
        paths.append(f"/skus/{quote(sku, safe='')}")
    if partner:
        paths.append(f"/parceiros/{quote(partner, safe='')}")
    index = None
    for path in paths:
        response = runner.get(base + path)
        if response is None:
            continue
        ok = response.status == 200 and 'id="root"' in response.text
        runner.check("frontend", f"{path} entrega a SPA (rewrite)", ok, f"status {response.status}")
        if path == "/" and ok:
            index = response
    if index is None:
        return
    headers = index.headers
    runner.check("frontend", "Content-Security-Policy presente", "default-src" in headers.get("content-security-policy", ""))
    runner.check("frontend", "X-Frame-Options DENY", headers.get("x-frame-options") == "DENY")
    runner.check("frontend", "nosniff presente", headers.get("x-content-type-options") == "nosniff")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', index.text)
    runner.check("frontend", "bundle referenciado", bool(scripts))
    for src in scripts:
        asset = runner.get(src if src.startswith("http") else base + src)
        if asset is None:
            continue
        runner.check("frontend", f"{src} disponível", asset.status == 200 and "javascript" in asset.headers.get("content-type", ""), asset.headers.get("content-type", ""))
        runner.check("frontend", f"{src} sem segredos", not any(p.search(asset.text) for p in SECRET_PATTERNS))


def report(checks: list[Check]) -> int:
    width = max((len(f"{c.area} · {c.name}") for c in checks), default=10)
    for item in checks:
        label = f"{item.area} · {item.name}"
        print(f"{'OK  ' if item.ok else 'FALHA'} {label.ljust(width)}  {item.detail}")
    failed = [item for item in checks if not item.ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} verificações aprovadas.")
    return 1 if failed else 0


def main(argv: list[str] | None = None, request: Requester = http_request) -> int:
    parser = argparse.ArgumentParser(description="Smoke test somente leitura do Caderno Inteligente publicado.")
    parser.add_argument("--backend", required=True, help="URL base do backend, sem /api")
    parser.add_argument("--frontend", help="URL base do frontend")
    parser.add_argument("--expect-environment", choices=("development", "production"), help="valor esperado de APP_ENV")
    parser.add_argument("--expect-readonly", action="store_true", help="exige WRITE_ENABLED=false")
    parser.add_argument("--expect-demo", action="store_true", help="exige DEMO_MODE=true")
    args = parser.parse_args(argv)
    runner = Runner(request)
    found = backend_checks(runner, args.backend, args.frontend, args.expect_environment,
                           True if args.expect_readonly else None, True if args.expect_demo else None)
    if args.frontend:
        frontend_checks(runner, args.frontend, found.get("sku"), found.get("partner"))
    return report(runner.checks)


if __name__ == "__main__":
    sys.exit(main())
