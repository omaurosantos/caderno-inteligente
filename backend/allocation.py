"""Rotas aditivas da alocação sugerida (Etapa 16.2): leitura do bloco calculado no pipeline, sem recalcular nada."""
from typing import Callable

from fastapi import APIRouter, HTTPException, Query


def create_allocation_router(allocation_loader: Callable[[], dict], describe_error: Callable[[str, Exception], str] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")
    describe = describe_error or (lambda message, error: f"{message}: {error}")

    def load() -> dict:
        try:
            return allocation_loader()
        except (ValueError, KeyError) as error:
            raise HTTPException(422, describe("Alocação bloqueada por dados/configuração inválidos", error)) from error

    @router.get("/allocation")
    def allocation(
        sku: str | None = Query(default=None, max_length=40),
        regiao: str | None = Query(default=None, max_length=80),
        cliente: str | None = Query(default=None, max_length=80),
    ):
        """SKUs com falta ou disputados, com a ordem de atendimento e o motivo de cada pedido. Sugestão: nada é reservado."""
        result = load()
        skus = result["skus"]
        if sku is not None and sku not in skus:
            raise HTTPException(404, "SKU sem pedido aberto na alocação")
        orders = [order for item in skus.values() for order in item["orders"]]
        if regiao is not None and regiao not in {order["region"] for order in orders}:
            raise HTTPException(422, "Região inválida")
        if cliente is not None and cliente not in {order["client"] for order in orders}:
            raise HTTPException(422, "Cliente inválido")
        items = [
            item for code, item in skus.items()
            if (item["has_shortfall"] or item["contested"]) and (sku is None or code == sku)
            and (regiao is None or any(order["region"] == regiao for order in item["orders"]))
            and (cliente is None or cliente in item["clients"])
        ]
        return {
            "reference_date": result["reference_date"], "total": len(items), "items": items, "totals": result["totals"],
            "field_nature": result["field_nature"], "limitations": result["limitations"], "requires_human_review": True,
        }

    @router.get("/allocation/regions")
    def allocation_regions():
        """Unidades e valor sem cobertura na data prometida por região; a soma das regiões é o total descoberto."""
        result = load()
        return {
            "reference_date": result["reference_date"], "regions": result["regions"], "totals": result["totals"],
            "limitations": result["limitations"], "requires_human_review": True,
        }

    return router
