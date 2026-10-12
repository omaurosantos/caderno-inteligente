"""Rota aditiva do Programa de Colaboração (somente leitura, isolada do ranking operacional)."""
from pathlib import Path
from threading import Lock
from typing import Callable

from fastapi import APIRouter, HTTPException

from caderno_inteligente.collaboration import build_collaboration, load_collaboration_settings
from caderno_inteligente.partner_insights import build_partner_insights, load_commercial_thresholds


def create_collaboration_router(dataset_loader: Callable, settings_file: Path, thresholds_file: Path, unit_share: Callable[[dict], float | None],
                                describe_error: Callable[[str, Exception], str] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")
    describe = describe_error or (lambda message, error: f"{message}: {error}")
    lock = Lock()
    cache: dict = {}

    @router.get("/collaboration")
    def collaboration():
        dataset = dataset_loader()
        signature = (settings_file.stat().st_mtime_ns, thresholds_file.stat().st_mtime_ns)
        with lock:
            if cache.get("dataset") is dataset and cache.get("signature") == signature:
                return cache["result"]
            try:
                insights = build_partner_insights(dataset, load_commercial_thresholds(thresholds_file))
                result = build_collaboration(dataset, insights, load_collaboration_settings(settings_file), unit_share(dataset))
            except (ValueError, KeyError) as error:
                raise HTTPException(422, describe("Programa de colaboração bloqueado por dados/configuração inválidos", error)) from error
            cache.update(dataset=dataset, signature=signature, result=result)
            return result

    return router
