"""Rota aditiva do cartão do modelo oficial e do histórico do benchmark de modelos; nunca altera a previsão oficial."""
import hashlib
from pathlib import Path
from threading import Lock
from typing import Callable

from fastapi import APIRouter, HTTPException

from caderno_inteligente.benchmark_store import latest_benchmark_run, list_benchmark_runs
from caderno_inteligente.forecast_engine_config import load_engine_config
from caderno_inteligente.model_card import build_model_card
from caderno_inteligente.rolling_backtest import series_by_sku

NO_RUN_NOTE = "Nenhuma rodada de benchmark neste ambiente. Rode scripts/benchmark_models.py com requirements-ml.txt instalado."
STALE_NOTE = "A planilha mudou depois desta rodada: os erros abaixo não medem a base atual. Rode o benchmark de novo."


def _signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _ordered(results: list[dict]) -> list[dict]:
    """Resultados medidos do menor para o maior WAPE; indisponíveis e falhas no fim, na ordem da rodada."""
    official = next((result["wape"] for result in results if result["model"] == "official" and result["wape"] is not None), None)
    enriched = [
        {**result, "is_official": result["model"] == "official",
         "beats_official": None if official is None or result["wape"] is None or result["model"] == "official" else result["wape"] < official}
        for result in results
    ]
    measured = sorted((result for result in enriched if result["wape"] is not None), key=lambda result: result["wape"])
    return measured + [result for result in enriched if result["wape"] is None]


def create_model_benchmark_router(*, pipeline: Callable, source: Path, engine_config_file: Path, benchmark_db: Path,
                                  describe_error: Callable[[str, Exception], str] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")
    describe = describe_error or (lambda message, error: f"{message}: {error}")
    lock = Lock()
    cache: dict[str, object] = {}

    def source_hash() -> str:
        key = _signature(source)
        if cache.get("hash_key") != key:
            cache.update(hash_key=key, hash=hashlib.sha256(source.read_bytes()).hexdigest())
        return cache["hash"]

    @router.get("/model-benchmark")
    def model_benchmark():
        try:
            config = load_engine_config(engine_config_file)
        except (OSError, ValueError) as error:
            raise HTTPException(422, describe("Configuração do motor de previsão inválida", error)) from error
        built = pipeline()
        key = (id(built), _signature(engine_config_file))
        with lock:  # a avaliação rolante do cartão leva alguns décimos: não repete em chamadas simultâneas
            if cache.get("card_key") != key:
                cache.update(card_key=key, card=build_model_card(series_by_sku(built[0]["Vendas_24m"]), built[5], config))
            card = cache["card"]
            current_hash = source_hash()
        run = latest_benchmark_run(benchmark_db)
        if run is None:
            benchmark = {"status": "no_run", "stale": None, "note": NO_RUN_NOTE, "run": None, "history": []}
        else:
            stale = run["source_hash"] != current_hash
            benchmark = {
                "status": "ok", "stale": stale, "note": STALE_NOTE if stale else None,
                "run": {**run, "results": _ordered(run["results"])},
                "history": list_benchmark_runs(benchmark_db),
            }
        return {"official": card, "benchmark": benchmark}

    return router
