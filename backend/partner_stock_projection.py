"""Rota aditiva da projeção de estoque no parceiro; sem tela até o grupo validar, e nunca altera nada oficial."""
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from caderno_inteligente.partner_stock_projection import build_partner_stock_projection, load_partner_projection_settings

CODE_PATTERN = r"^[A-Za-z0-9 _.\-]{1,40}$"


def create_partner_stock_projection_router(*, dataset_loader: Callable, settings_file: Path,
                                           describe_error: Callable[[str, Exception], str] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")
    describe = describe_error or (lambda message, error: f"{message}: {error}")

    @router.get("/partner-stock-projection")
    def partner_stock_projection(partner: str | None = Query(None, pattern=CODE_PATTERN),
                                 sku: str | None = Query(None, pattern=CODE_PATTERN)):
        try:
            result = build_partner_stock_projection(dataset_loader(), load_partner_projection_settings(settings_file))
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(422, describe("Projeção no parceiro bloqueada por dados/configuração inválidos", error)) from error
        items = result["items"]
        if partner is not None:
            items = [item for item in items if item["partner"] == partner]
            if not items:
                raise HTTPException(404, "Parceiro sem sell-out informado")
        if sku is not None:
            items = [item for item in items if item["sku"] == sku]
            if not items:
                raise HTTPException(404, "SKU sem sell-out informado para o filtro")
        # Os erros agregados continuam os da base inteira; os do par estão em cada item.
        return {**result, "items": items, "total": len(items)}

    return router
