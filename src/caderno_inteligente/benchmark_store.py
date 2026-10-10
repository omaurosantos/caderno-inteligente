"""Histórico das rodadas do benchmark de modelos de previsão, em SQLite local.

Cada rodada guarda o protocolo usado, o hash da planilha e um resultado por modelo. Nada aqui é lido pelo pipeline
oficial: o benchmark é evidência para comparar modelos, não muda previsão, ranking nem recomendação.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULT_FIELDS = (
    "model", "label", "library", "library_version", "params", "status", "error_message",
    "wape", "peak_wape", "normal_wape", "bias", "evaluated_points", "fallback_points", "duration_seconds",
)
JSON_RESULT_FIELDS = {"params"}
RESULT_STATUSES = ("ok", "unavailable", "failed")


def init_benchmark_db(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS benchmark_runs ("
            "id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, source_hash TEXT NOT NULL, "
            "protocol TEXT NOT NULL, official_model TEXT, environment TEXT NOT NULL, note TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS benchmark_results ("
            "id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES benchmark_runs(id), "
            "model TEXT NOT NULL, label TEXT NOT NULL, library TEXT NOT NULL, library_version TEXT, params TEXT NOT NULL, "
            "status TEXT NOT NULL, error_message TEXT, wape REAL, peak_wape REAL, normal_wape REAL, bias REAL, "
            "evaluated_points INTEGER NOT NULL, fallback_points INTEGER NOT NULL, duration_seconds REAL NOT NULL)"
        )


def save_benchmark_run(path: str | Path, *, source_hash: str, protocol: dict[str, Any], official_model: str | None,
                       environment: dict[str, Any], results: list[dict[str, Any]], note: str | None = None) -> int:
    """Grava a rodada e seus resultados numa única transação; devolve o id da rodada."""
    for result in results:
        if result["status"] not in RESULT_STATUSES:
            raise ValueError(f"Status de resultado inválido: {result['status']}")
    init_benchmark_db(path)
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        cursor = connection.execute(
            "INSERT INTO benchmark_runs(created_at, source_hash, protocol, official_model, environment, note) VALUES (?, ?, ?, ?, ?, ?)",
            (created_at, source_hash, json.dumps(protocol), official_model, json.dumps(environment), note),
        )
        run_id = int(cursor.lastrowid)
        connection.executemany(
            f"INSERT INTO benchmark_results(run_id, {', '.join(RESULT_FIELDS)}) VALUES (?{', ?' * len(RESULT_FIELDS)})",
            [
                (run_id, *(json.dumps(result.get(field) or {}) if field in JSON_RESULT_FIELDS else result.get(field) for field in RESULT_FIELDS))
                for result in results
            ],
        )
    return run_id


def _run(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0], "created_at": row[1], "source_hash": row[2], "protocol": json.loads(row[3]),
        "official_model": row[4], "environment": json.loads(row[5]), "note": row[6],
    }


def _results(connection: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT {', '.join(RESULT_FIELDS)} FROM benchmark_results WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
    return [
        {field: json.loads(value) if field in JSON_RESULT_FIELDS else value for field, value in zip(RESULT_FIELDS, row)}
        for row in rows
    ]


def get_benchmark_run(path: str | Path, run_id: int) -> dict[str, Any] | None:
    if not Path(path).exists():
        return None
    init_benchmark_db(path)
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT id, created_at, source_hash, protocol, official_model, environment, note FROM benchmark_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return None if row is None else {**_run(row), "results": _results(connection, row[0])}


def latest_benchmark_run(path: str | Path) -> dict[str, Any] | None:
    """Rodada mais recente com seus resultados, ou `None` se o banco não existe ou está vazio."""
    if not Path(path).exists():
        return None
    init_benchmark_db(path)
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT MAX(id) FROM benchmark_runs").fetchone()
    return None if row[0] is None else get_benchmark_run(path, int(row[0]))


def list_benchmark_runs(path: str | Path) -> list[dict[str, Any]]:
    """Resumo de cada rodada (mais recente primeiro): quantos modelos e o de menor WAPE."""
    if not Path(path).exists():
        return []
    init_benchmark_db(path)
    with sqlite3.connect(path) as connection:
        runs = connection.execute(
            "SELECT id, created_at, source_hash, official_model, note FROM benchmark_runs ORDER BY id DESC"
        ).fetchall()
        summaries = []
        for run_id, created_at, source_hash, official_model, note in runs:
            best = connection.execute(
                "SELECT model, wape FROM benchmark_results WHERE run_id = ? AND status = 'ok' AND wape IS NOT NULL ORDER BY wape, id LIMIT 1",
                (run_id,),
            ).fetchone()
            count = connection.execute("SELECT COUNT(*) FROM benchmark_results WHERE run_id = ?", (run_id,)).fetchone()[0]
            summaries.append({
                "id": run_id, "created_at": created_at, "source_hash": source_hash, "official_model": official_model, "note": note,
                "models": count, "best_model": None if best is None else best[0], "best_wape": None if best is None else best[1],
            })
    return summaries
