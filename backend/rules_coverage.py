"""Rota aditiva de cobertura de regras (somente leitura sobre o pipeline em cache)."""
from typing import Callable

from fastapi import APIRouter, HTTPException

from caderno_inteligente.rules_coverage import build_rules_coverage


def create_rules_coverage_router(*, pipeline: Callable, forecast_items: Callable, commercial: Callable, direct_channels: Callable,
                                 describe_error: Callable[[str, Exception], str] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")
    describe = describe_error or (lambda message, error: f"{message}: {error}")

    @router.get("/rules/coverage")
    def rules_coverage():
        """Quanto cada regra dispara nas saídas atuais e, quando zero, por quê."""
        try:
            dataset, _, _, issues, _, _ = pipeline()
            return build_rules_coverage(issues, forecast_items(), commercial(), direct_channels(), dataset)
        except (ValueError, KeyError) as error:
            raise HTTPException(422, describe("Cobertura de regras bloqueada por dados/configuração inválidos", error)) from error

    return router
