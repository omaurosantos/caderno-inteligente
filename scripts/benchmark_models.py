"""Roda o benchmark de modelos de previsão e grava a rodada no SQLite local.

Somente leitura sobre o XLSM. Os modelos externos precisam de `requirements-ml.txt`; sem a biblioteca, o modelo é
registrado como indisponível e a rodada continua.

    python scripts/benchmark_models.py                          # modelos rápidos
    python scripts/benchmark_models.py --include-slow           # inclui Prophet (dezenas de minutos)
    python scripts/benchmark_models.py --models official,auto_ets --note "teste"
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from caderno_inteligente.benchmark_store import save_benchmark_run  # noqa: E402
from caderno_inteligente.forecast_engine_config import load_engine_config  # noqa: E402
from caderno_inteligente.ingestion import load_workbook  # noqa: E402
from caderno_inteligente.model_benchmark import MODELS, environment, run_benchmark  # noqa: E402
from caderno_inteligente.rolling_backtest import series_by_sku  # noqa: E402
from caderno_inteligente.transformations import normalise_dataset  # noqa: E402

SOURCE = ROOT / "data" / "source" / "Base de Dados - Caderno Inteligente.xlsm"
ENGINE_CONFIG_FILE = ROOT / "config" / "forecast_engine.json"
DEFAULT_DB = ROOT / "runtime" / "benchmarks.db"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _print_result(result: dict) -> None:
    detail = result["error_message"] or ""
    if result["fallback_points"]:
        detail = f"{result['fallback_points']} pontos com recuo para o oficial"
    print(
        f"{result['label'][:42]:42s} {result['status']:11s} WAPE {_percent(result['wape']):>6s} | pico {_percent(result['peak_wape']):>6s}"
        f" | viés {_percent(result['bias']):>6s} | {result['duration_seconds']:7.1f}s {detail}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", help=f"códigos separados por vírgula; disponíveis: {', '.join(MODELS)}")
    parser.add_argument("--include-slow", action="store_true", help="inclui modelos lentos (Prophet) quando --models não é usado")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="banco SQLite da rodada (padrão: runtime/benchmarks.db)")
    parser.add_argument("--note", help="observação gravada com a rodada")
    args = parser.parse_args(argv)

    if args.models:
        codes = [code.strip() for code in args.models.split(",") if code.strip()]
        unknown = [code for code in codes if code not in MODELS]
        if unknown:
            parser.error(f"modelo desconhecido: {', '.join(unknown)}")
    else:
        codes = [code for code, model in MODELS.items() if args.include_slow or not model.slow]

    config = load_engine_config(ENGINE_CONFIG_FILE)
    dataset = normalise_dataset(load_workbook(SOURCE))
    series_map = series_by_sku(dataset["Vendas_24m"])
    print(f"{len(series_map)} SKUs | modelos: {', '.join(codes)}", flush=True)
    protocol, results = run_benchmark(series_map, config, [MODELS[code] for code in codes], on_result=_print_result)
    run_id = save_benchmark_run(
        args.db, source_hash=file_sha256(SOURCE), protocol=protocol, official_model=config["official"]["model_chain"][0],
        environment=environment(), results=results, note=args.note,
    )
    print(f"Rodada {run_id} gravada em {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
