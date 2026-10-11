"""Commercial evidence at real partner/SKU/month keys; never allocates global stock."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from caderno_inteligente.direct_channels import direct_channel_codes
from caderno_inteligente.partner_stock_projection import DEFAULT_PATH as PROJECTION_SETTINGS, load_partner_projection_settings, projection_by_pair

DEFAULT_THRESHOLDS = {
    "recent_months": 3, "minimum_sell_out_months": 3, "maximum_age_months": 1,
    "reposition_coverage_days": 30, "excess_coverage_days": 90,
    "minimum_excess_stock": 100,
    "divergence_ratio": .5, "minimum_divergence_quantity": 50,
    # Etapa 15: estoque acumulando no parceiro; gravados na 15.0, antes do código que os usa (15.5).
    "buildup_months": 6, "buildup_max_sell_through": .9, "buildup_min_stock_growth": .3, "stock_identity_tolerance": 1,
}
ACTION_LABELS = {
    "avaliar_reposicao": "Avaliar reposição",
    "monitorar_estoque": "Monitorar estoque do parceiro",
    "investigar_divergencia": "Investigar divergência",
    "solicitar_atualizacao": "Solicitar atualização dos dados",
    "dados_insuficientes": "Sem recomendação por dados insuficientes",
    # Etapa 15.5: estoque parado no parceiro.
    "conter_reposicao": "Não repor; acionar sell-out com o parceiro",
    "monitorar_excesso_parceiro": "Monitorar estoque alto no parceiro",
    # Etapa 16.1: canal direto vende ao consumidor; o faturamento é a venda observada.
    "canal_direto": "Venda direta ao consumidor: acompanhar pelo canal",
}
DIRECT_STOCK_REASON = "Sem estoque intermediário: o estoque que atende o canal é o do CD"
DIRECT_DATA_NATURE = "Observado (faturamento direto)"
SIGNAL_LABELS = {
    "REPOSITION_OPPORTUNITY": "Possível oportunidade de reposição",
    "PARTNER_EXCESS_RISK": "Possível excesso no parceiro",
    "SELLIN_SELLOUT_DIVERGENCE": "Divergência entre sell-in e sell-out",
    "STALE_PARTNER_DATA": "Dado antigo ou descontínuo",
    "INSUFFICIENT_PARTNER_DATA": "Dados insuficientes para recomendar",
    "PARTNER_STOCK_BUILDUP": "Estoque acumulando no parceiro",
}
LIMITATION = (
    "Recomendação comercial demonstrativa, sujeita à revisão humana. Estoque do parceiro é estimado; "
    "não é estoque do CD. Ausência de informação não é venda zero. Não altera o ranking operacional. "
    "Atualidade é relativa ao mês de referência da base, não à data atual."
)
FIELD_NATURE = {
    "sell_in_quantity": {"nature": "observado na fonte", "origin": "Sell_In.Quantidade enviada"},
    "sell_out_quantity": {"nature": "natureza declarada em cada registro", "origin": "Sell_Out.Quantidade vendida / Natureza do dado"},
    "estimated_stock": {"nature": "estimado na fonte, não auditado", "origin": "Sell_Out.Estoque estimado cliente"},
    "backlog_quantity": {"nature": "carteira registrada, sem alocação de produção", "origin": "Carteira_Pedidos.Quantidade"},
    "coverage_days": {"nature": "calculado: estoque estimado / (média mensal observada / 30)", "origin": "Sell_Out, somente meses do mesmo parceiro e SKU"},
    "comparable_difference": {"nature": "calculado apenas na interseção dos meses observados", "origin": "Sell_In e Sell_Out"},
    "region": {"nature": "cadastral", "origin": "Parceiros_Canais.Região"},
    "channel": {"nature": "cadastral", "origin": "Parceiros_Canais.Canal principal"},
}

FIELD_NATURE.update({
    "sell_in_recent": {"nature": "soma dos valores observados nos meses listados", "origin": "Sell_In, mesmo parceiro/SKU"},
    "sell_out_recent": {"nature": "soma dos valores observados nos meses listados", "origin": "Sell_Out, mesmo parceiro/SKU"},
    "average_monthly_sell_out": {"nature": "média aritmética de meses observados; zero observado entra na média", "origin": "Sell_Out no recorte recente"},
    "age_months": {"nature": "diferença de meses contra referência da base, não contra hoje", "origin": "último sell-out e maior mês de Sell_In/Sell_Out"},
    "missing_months": {"nature": "meses da janela sem quantidade observada", "origin": "Sell_Out e janela configurada"},
    "observed_skus": {"nature": "contagem distinta com quantidade não nula", "origin": "Sell_Out.SKU por parceiro"},
    "coverage": {"nature": "SKUs observados / total do catálogo; não é faturamento", "origin": "Sell_Out e Produtos"},
    "product": {"nature": "cadastral", "origin": "Produtos.Produto"},
    "backlog_order_count": {"nature": "contagem de pedidos registrados não encerrados", "origin": "Carteira_Pedidos.Pedido e Status"},
    "signals": {"nature": "calculado por regras comerciais demonstrativas", "origin": "config/commercial_thresholds.json e evidências do par"},
    "action": {"nature": "sugestão determinística para revisão humana, não autorização", "origin": "sinais comerciais e precedência documentada"},
    "sell_through_window": {"nature": "calculado: sell-out ÷ sell-in na janela de acúmulo", "origin": "Sell_In e Sell_Out, mesmo parceiro/SKU"},
    "stock_start": {"nature": "estimado na fonte", "origin": "Sell_Out.Estoque estimado cliente no mês anterior à janela de acúmulo"},
    "stock_growth": {"nature": "calculado: (estoque final − inicial) ÷ inicial", "origin": "Sell_Out.Estoque estimado cliente"},
    "stock_identity_consistent": {"nature": "calculado: estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t), dentro da tolerância", "origin": "Sell_In e Sell_Out"},
    # Etapa 16.1: canais diretos usam o faturamento como venda ao consumidor.
    "row_kind": {"nature": "cadastral", "origin": "Parceiros_Canais.Tipo: 'direct' para Canal direto, 'partner' para os demais"},
    "visibility_source": {"nature": "cadastral", "origin": "faturamento_direto (Vendas_24m) para Canal direto; sell_out_parceiro (Sell_Out) para os demais"},
    "stock_reason": {"nature": "explicação da ausência de estoque estimado", "origin": "canal direto não tem estoque intermediário; o estoque é o do CD"},
    "forward_projection": {"nature": "estimado: sell-out previsto pela média dos últimos meses; não é autorização de envio", "origin": "partner_stock_projection e config/partner_projection.json"},
})


def load_commercial_thresholds(path: str | Path | None = None) -> dict:
    values = dict(DEFAULT_THRESHOLDS)
    if path is not None:
        overrides = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(values):
            raise ValueError("Configuração comercial contém campos desconhecidos")
        values.update(overrides)
    return _validate_thresholds(values)


def _validate_thresholds(values: dict) -> dict:
    if set(values) != set(DEFAULT_THRESHOLDS):
        raise ValueError("Limiar comercial desconhecido")
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Limiar comercial inválido: {key}")
    for key in ("recent_months", "minimum_sell_out_months", "maximum_age_months", "buildup_months"):
        if int(values[key]) != values[key]:
            raise ValueError(f"Limiar precisa ser inteiro: {key}")
        values[key] = int(values[key])
    if not 1 <= values["minimum_sell_out_months"] <= values["recent_months"] <= 24:
        raise ValueError("Janela comercial deve conter de 1 a 24 meses e a amostra mínima")
    if values["excess_coverage_days"] <= values["reposition_coverage_days"]:
        raise ValueError("Limite de excesso deve superar o limite de reposição")
    if not 2 <= values["buildup_months"] <= 12:
        raise ValueError("Janela de acúmulo no parceiro deve ter de 2 a 12 meses")
    if not 0 < values["buildup_max_sell_through"] <= 1:
        raise ValueError("Sell-through máximo de acúmulo deve estar em (0, 1]")
    return values


def _number(value):
    return None if pd.isna(value) else float(value)


def _text(value):
    return None if pd.isna(value) else str(value)


def _monthly(frame: pd.DataFrame, rename: dict) -> pd.DataFrame:
    result = frame.rename(columns={"Cliente": "partner", "SKU": "sku", "Mês": "month", **rename}).copy()
    result = result[["partner", "sku", "month", *rename.values()]]
    result["month"] = pd.to_datetime(result["month"], errors="raise").dt.to_period("M")
    if result[["partner", "sku", "month"]].isna().any().any() or result.duplicated(["partner", "sku", "month"]).any():
        raise ValueError("Chave parceiro/SKU/mês ausente ou duplicada")
    for column in rename.values():
        if column == "data_nature":
            continue
        result[column] = pd.to_numeric(result[column], errors="raise")
        present = result[column].dropna()
        if (present < 0).any() or not present.map(math.isfinite).all():
            raise ValueError(f"Valor comercial inválido: {column}")
    return result


def _buildup(history: pd.DataFrame, reference, cfg: dict) -> dict:
    """Janela de acúmulo (Etapa 15.5): sell-through, estoque inicial → final e se a conta de estoque fecha."""
    months = cfg["buildup_months"]
    empty = {"buildup_window_months": months, "sell_in_window": None, "sell_out_window": None, "sell_through_window": None,
             "stock_start": None, "stock_growth": None, "stock_identity_consistent": None, "stock_identity_max_residual": None}
    if reference is None or history.empty:
        return empty
    window = history[history["month"] > reference - months]
    sell_in = window["sell_in_quantity"].dropna()
    sell_out = window["sell_out_quantity"].dropna()
    total_in = float(sell_in.sum()) if not sell_in.empty else None
    total_out = float(sell_out.sum()) if not sell_out.empty else None
    stocks = history.dropna(subset=["estimated_stock"]).set_index("month")["estimated_stock"]
    before = stocks[stocks.index <= reference - months]
    start = float(before.iloc[-1]) if not before.empty else (float(stocks[stocks.index > reference - months].iloc[0]) if not stocks.empty else None)
    end = float(stocks.iloc[-1]) if not stocks.empty else None
    residuals = []
    indexed = history.set_index("month")
    for month in indexed.index:
        previous = month - 1
        row = indexed.loc[month]
        if previous in indexed.index and all(pd.notna(value) for value in (row["estimated_stock"], row["sell_in_quantity"], row["sell_out_quantity"], indexed.loc[previous, "estimated_stock"])):
            residuals.append(abs(float(row["estimated_stock"]) - (float(indexed.loc[previous, "estimated_stock"]) + float(row["sell_in_quantity"]) - float(row["sell_out_quantity"]))))
    largest = max(residuals) if residuals else None
    return {
        "buildup_window_months": months, "sell_in_window": total_in, "sell_out_window": total_out,
        "sell_through_window": None if not total_in or total_out is None else total_out / total_in,
        "stock_start": start, "stock_growth": None if not start or end is None else (end - start) / start,
        "stock_identity_consistent": None if largest is None else largest <= cfg["stock_identity_tolerance"],
        "stock_identity_max_residual": largest,
    }


def _billing(sales: pd.DataFrame | None, direct: set[str]) -> pd.DataFrame:
    """Faturamento dos canais diretos por canal/SKU/mês (Vendas_24m); sem a aba, nada é observado."""
    columns = ["partner", "sku", "month", "billed_quantity"]
    if sales is None or not direct:
        return pd.DataFrame(columns=columns)
    frame = sales[sales["Cliente/Canal"].isin(direct)].rename(columns={"Cliente/Canal": "partner", "SKU": "sku", "Mês": "month", "Quantidade faturada": "billed_quantity"})
    frame = frame[columns].copy()
    frame["month"] = pd.to_datetime(frame["month"], errors="raise").dt.to_period("M")
    frame["billed_quantity"] = pd.to_numeric(frame["billed_quantity"], errors="raise")
    return frame.groupby(["partner", "sku", "month"], as_index=False)["billed_quantity"].sum(min_count=1)


def _backlog_fields(backlog: pd.DataFrame) -> dict:
    return {
        "backlog_quantity": float(backlog["Quantidade"].sum()), "backlog_order_count": len(backlog),
        "orders": [{"order": r["Pedido"], "quantity": float(r["Quantidade"]), "promised_date": None if pd.isna(r["Data prometida"]) else pd.Timestamp(r["Data prometida"]).date().isoformat(), "status": r["Status"]} for _, r in backlog.iterrows()],
    }


def _direct_row(partner, sku, fields: pd.Series, product, backlog: pd.DataFrame, history: pd.DataFrame, reference, window: list, cfg: dict) -> dict:
    """Etapa 16.1: no canal direto o faturamento é a venda ao consumidor; não há estoque intermediário para estimar."""
    history = history[history["billed_quantity"].notna()].sort_values("month")
    recent = history[history["month"].isin(window)]
    sold = recent[recent["billed_quantity"] > 0]
    billed_months = history.loc[history["billed_quantity"] > 0, "month"]
    latest = None if billed_months.empty else billed_months.max()
    enough = len(sold) >= cfg["minimum_sell_out_months"]
    total = None if recent.empty else float(recent["billed_quantity"].sum())
    avg = None if recent.empty else float(recent["billed_quantity"].mean())
    observed = set(sold["month"])
    if enough:
        action, signals = "canal_direto", []
        rationale = (f"Venda direta ao consumidor: {total:g} unidades faturadas em {len(sold)} meses (Vendas_24m), média de {avg:g} un./mês. "
                     "Sem estoque intermediário; cobertura, acúmulo e divergência não se aplicam. Uma falta em pedido do canal depende do estoque do CD.")
    else:
        action, signals = "dados_insuficientes", ["INSUFFICIENT_PARTNER_DATA"]
        rationale = (f"Faturamento direto em {len(sold)} dos {len(window)} meses recentes (mínimo {cfg['minimum_sell_out_months']}). "
                     "Sem venda observada suficiente no canal; nenhuma recomendação é inferida.")
    return {
        "partner": partner, "partner_name": _text(fields["Nome fictício"]), "sku": sku,
        "product": _text(product), "region": _text(fields.get("Região")), "channel": _text(fields.get("Canal principal")),
        "row_kind": "direct", "visibility_source": "faturamento_direto", "stock_reason": DIRECT_STOCK_REASON,
        "forward_projection": None, "forward_projection_reason": None,
        "reference_month": None if reference is None else str(reference), "window_months": [str(m) for m in window],
        "sell_in_recent": None, "sell_in_months": [],
        "sell_out_recent": total, "sell_out_months": [str(m) for m in sold["month"]],
        **_buildup(pd.DataFrame(), None, cfg),
        "comparable_months": [], "comparable_sell_in": None, "comparable_sell_out": None, "comparable_difference": None, "divergence_ratio": None,
        "estimated_stock": None, "stock_month": None, "data_nature": DIRECT_DATA_NATURE if enough else None,
        "average_monthly_sell_out": avg, "coverage_days": None,
        "age_months": None if reference is None or latest is None else reference.ordinal - latest.ordinal,
        "missing_months": [str(month) for month in window if month not in observed],
        "data_quality": "sufficient" if enough else "insufficient",
        **_backlog_fields(backlog),
        "signals": [{"code": code, "label": SIGNAL_LABELS[code]} for code in signals],
        "action": action, "action_label": ACTION_LABELS[action], "requires_human_review": True,
        "recommendation_reason": rationale,
        "periods": [{"month": str(r["month"]), "sell_in_quantity": None, "sell_out_quantity": _number(r["billed_quantity"]), "estimated_stock": None,
                     "data_nature": DIRECT_DATA_NATURE} for _, r in history.iterrows()],
    }


def _load_projection(data: dict[str, pd.DataFrame]) -> tuple[dict | None, str | None]:
    """Etapa 16.6: projeção estimada por par; falha não derruba a análise (campo None + motivo)."""
    try:
        return projection_by_pair(data, load_partner_projection_settings(PROJECTION_SETTINGS)), None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, f"Projeção do parceiro indisponível: {error}"


def build_partner_insights(data: dict[str, pd.DataFrame], thresholds: dict | None = None, projection: dict | str | None = "auto") -> dict:
    """Read-only, reproducible reference is the latest month of sell-in/out, not wall clock.

    `projection`: "auto" carrega config/partner_projection.json; um dict (saída de `projection_by_pair`) é usado como está; None desliga.
    Linhas de parceiro com dado suficiente ganham `forward_projection` (evidência estimada); as demais ficam None.
    """
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    cfg = _validate_thresholds(cfg)
    incoming = _monthly(data["Sell_In"], {"Quantidade enviada": "sell_in_quantity"})
    outgoing = _monthly(data["Sell_Out"], {"Quantidade vendida": "sell_out_quantity", "Estoque estimado cliente": "estimated_stock", "Natureza do dado": "data_nature"})
    monthly = incoming.merge(outgoing, on=["partner", "sku", "month"], how="outer", validate="one_to_one")
    partners = data["Parceiros_Canais"]
    products = data["Produtos"]
    if partners["Código"].duplicated().any() or products["SKU"].duplicated().any():
        raise ValueError("Cadastro comercial duplicado")
    partner_codes = set(partners["Código"])
    product_codes = set(products["SKU"])
    orders = data["Carteira_Pedidos"].copy()
    if orders["Pedido"].duplicated().any():
        raise ValueError("Pedido duplicado na carteira comercial")
    if not set(monthly["partner"]).issubset(partner_codes) or not set(monthly["sku"]).issubset(product_codes):
        raise ValueError("Vínculo comercial órfão em sell-in/out")
    if not set(orders["Cliente/Canal"]).issubset(partner_codes) or not set(orders["SKU"]).issubset(product_codes):
        raise ValueError("Vínculo comercial órfão na carteira")
    quantities = pd.to_numeric(orders["Quantidade"], errors="raise")
    if quantities.isna().any() or (quantities < 0).any() or not quantities.map(math.isfinite).all():
        raise ValueError("Quantidade inválida na carteira comercial")
    orders["Quantidade"] = quantities
    orders = orders[~orders["Status"].astype(str).str.casefold().isin(["cancelado", "concluído", "entregue", "faturado"])]
    reference = None if monthly.empty else monthly["month"].max()
    window = [] if reference is None else [reference - i for i in reversed(range(cfg["recent_months"]))]
    pairs = set(zip(monthly["partner"], monthly["sku"])) | set(zip(orders["Cliente/Canal"], orders["SKU"]))
    catalog = products.set_index("SKU")
    registry = partners.set_index("Código")
    direct = set(direct_channel_codes(partners))
    billing = _billing(data.get("Vendas_24m"), direct)
    projection_reason = None
    if isinstance(projection, str):
        projection, projection_reason = _load_projection(data)
    rows = []
    for partner, sku in sorted(pairs):
        if partner in direct:
            backlog = orders[(orders["Cliente/Canal"] == partner) & (orders["SKU"] == sku)]
            rows.append(_direct_row(partner, sku, registry.loc[partner], catalog.loc[sku, "Produto"], backlog,
                                    billing[(billing["partner"] == partner) & (billing["sku"] == sku)], reference, window, cfg))
            continue
        history =monthly[(monthly["partner"] == partner) & (monthly["sku"] == sku)].sort_values("month")
        recent = history[history["month"].isin(window)]
        sell_out = history[history["sell_out_quantity"].notna()]
        recent_out = recent[recent["sell_out_quantity"].notna()]
        recent_in = recent[recent["sell_in_quantity"].notna()]
        comparable = recent[recent["sell_in_quantity"].notna() & recent["sell_out_quantity"].notna()]
        last = None if sell_out.empty else sell_out.iloc[-1]
        latest_month = None if last is None else last["month"]
        age = None if reference is None or latest_month is None else reference.ordinal - latest_month.ordinal
        stock = None if last is None else _number(last["estimated_stock"])
        avg = None if recent_out.empty else float(recent_out["sell_out_quantity"].mean())
        coverage = stock / (avg / 30) if stock is not None and avg is not None and avg > 0 else None
        observed_months = set(recent_out["month"])
        missing_months = [str(month) for month in window if month not in observed_months]
        enough = len(recent_out) >= cfg["minimum_sell_out_months"] and stock is not None and last is not None and bool(_text(last["data_nature"]))
        stale = latest_month is not None and (age > cfg["maximum_age_months"] or bool(missing_months))
        comparable_in = None if comparable.empty else float(comparable["sell_in_quantity"].sum())
        comparable_out = None if comparable.empty else float(comparable["sell_out_quantity"].sum())
        difference = None if comparable.empty else comparable_in - comparable_out
        ratio = None if comparable_out in (None, 0) else abs(difference) / comparable_out
        buildup = _buildup(history, reference, cfg)
        consistent = buildup["stock_identity_consistent"]
        signals = []
        if not enough:
            signals.append("INSUFFICIENT_PARTNER_DATA")
        if stale:
            signals.append("STALE_PARTNER_DATA")
        # Etapa 15.5: se a conta de estoque fecha, a diferença sell-in − sell-out é estoque acumulado, não erro de dado.
        if (consistent is not True and len(comparable) >= cfg["minimum_sell_out_months"] and abs(difference) >= cfg["minimum_divergence_quantity"]
                and (comparable_out == 0 or ratio >= cfg["divergence_ratio"])):
            signals.append("SELLIN_SELLOUT_DIVERGENCE")
        if enough and not stale:
            if coverage is not None and coverage <= cfg["reposition_coverage_days"] and avg > 0:
                signals.append("REPOSITION_OPPORTUNITY")
            high_stock = stock >= cfg["minimum_excess_stock"] and (avg == 0 or (coverage is not None and coverage >= cfg["excess_coverage_days"]))
            through, growth = buildup["sell_through_window"], buildup["stock_growth"]
            if high_stock and through is not None and through <= cfg["buildup_max_sell_through"] and growth is not None and growth >= cfg["buildup_min_stock_growth"]:
                signals.append("PARTNER_STOCK_BUILDUP")
            elif high_stock:
                signals.append("PARTNER_EXCESS_RISK")
        if stale:
            action = "solicitar_atualizacao"
        elif not enough:
            action = "dados_insuficientes"
        elif "SELLIN_SELLOUT_DIVERGENCE" in signals:
            action = "investigar_divergencia"
        elif "PARTNER_STOCK_BUILDUP" in signals:
            action = "conter_reposicao"
        elif "REPOSITION_OPPORTUNITY" in signals:
            action = "avaliar_reposicao"
        elif "PARTNER_EXCESS_RISK" in signals:
            action = "monitorar_excesso_parceiro"
        else:
            action = "monitorar_estoque"
        if action == "solicitar_atualizacao":
            rationale = f"Sell-out com idade de {age} meses contra a referência da base; meses recentes ausentes: {', '.join(missing_months) or 'nenhum'}. Atualizar antes de avaliar reposição."
        elif action == "dados_insuficientes":
            rationale = f"Amostra recente de {len(recent_out)} meses (mínimo {cfg['minimum_sell_out_months']}); exige estoque estimado e natureza declarada. Dados ausentes impedem recomendação de reposição."
        elif action == "investigar_divergencia":
            rationale = f"Diferença de {difference:g} unidades nos mesmos {len(comparable)} meses supera os limites demonstrativos de quantidade e proporção. Conferir períodos e registros; não interpretar a diferença como venda futura."
        elif action == "conter_reposicao":
            rationale = (f"Nos últimos {cfg['buildup_months']} meses o parceiro vendeu {buildup['sell_through_window']:.0%} do que recebeu e o estoque estimado foi de "
                         f"{buildup['stock_start']:g} para {stock:g} unidades ({coverage:.0f} dias de giro). A conta de estoque fecha: é produto parado, "
                         "não erro de registro. Não repor e combinar ação de sell-out com o parceiro.")
        elif action == "avaliar_reposicao":
            rationale = f"Giro médio observado de {avg:g} unidades/mês e cobertura estimada de {coverage:.1f} dias, até o limite de {cfg['reposition_coverage_days']:g} dias. Avaliar comercialmente; não há quantidade autorizada."
        elif action == "monitorar_excesso_parceiro":
            rationale = (f"Estoque estimado de {stock:g} unidades para um giro de {avg:g} unidades/mês ({'sem giro' if not avg else f'{coverage:.0f} dias'}), "
                         "sem acúmulo recente. Monitorar e não ampliar a reposição.")
        else:
            rationale = "Dados suficientes no recorte, sem exceção que justifique outra sugestão. Monitoramento de rotina não afirma excesso de estoque."
        quality = "stale" if stale else "sufficient" if enough else "insufficient"
        forward, forward_reason = None, None
        if quality == "sufficient" and projection is not None:
            forward = projection.get((partner, sku)) or {"status": "insufficient_data", "nature": "estimado", "days_until_stockout_without_replenishment": None,
                                                         "replenishment_to_target": None, "sell_out_wape": None, "reason": "Par sem sell-out na base da projeção."}
        elif quality == "sufficient":
            forward_reason = projection_reason
        backlog = orders[(orders["Cliente/Canal"] == partner) & (orders["SKU"] == sku)]
        fields = registry.loc[partner]
        rows.append({
            "partner": partner, "partner_name": _text(fields["Nome fictício"]), "sku": sku,
            "product": _text(catalog.loc[sku, "Produto"]), "region": _text(fields.get("Região")), "channel": _text(fields.get("Canal principal")),
            "row_kind": "partner", "visibility_source": "sell_out_parceiro", "stock_reason": None,
            "forward_projection": forward, "forward_projection_reason": forward_reason,
            "reference_month": None if reference is None else str(reference), "window_months": [str(m) for m in window],
            "sell_in_recent": None if recent_in.empty else float(recent_in["sell_in_quantity"].sum()),
            "sell_in_months": [str(m) for m in recent_in["month"]],
            "sell_out_recent": None if recent_out.empty else float(recent_out["sell_out_quantity"].sum()),
            "sell_out_months": [str(m) for m in recent_out["month"]],
            **buildup,
            "comparable_months": [str(m) for m in comparable["month"]], "comparable_sell_in": comparable_in,
            "comparable_sell_out": comparable_out, "comparable_difference": difference, "divergence_ratio": ratio,
            "estimated_stock": stock, "stock_month": None if latest_month is None else str(latest_month),
            "data_nature": None if last is None else _text(last["data_nature"]),
            "average_monthly_sell_out": avg, "coverage_days": coverage, "age_months": age,
            "missing_months": missing_months, "data_quality": quality,
            **_backlog_fields(backlog),
            "signals": [{"code": code, "label": SIGNAL_LABELS[code]} for code in signals],
            "action": action, "action_label": ACTION_LABELS[action], "requires_human_review": True,
            "recommendation_reason": rationale,
            "periods": [{"month": str(r["month"]), **{k: _number(r[k]) for k in ("sell_in_quantity", "sell_out_quantity", "estimated_stock")}, "data_nature": _text(r["data_nature"])} for _, r in history.iterrows()],
        })
    summaries = []
    total_skus = len(product_codes)
    for _, partner in partners.iterrows():
        code = partner["Código"]
        subset = [row for row in rows if row["partner"] == code]
        if code in direct:
            # Etapa 16.1: canal direto é observado pelo faturamento nos meses recentes da janela comercial.
            billed = billing[(billing["partner"] == code) & (billing["billed_quantity"] > 0)]
            observed_skus = int(billed.loc[billed["month"].isin(window), "sku"].nunique())
            latest = billed["month"]
        else:
            observed = outgoing[outgoing["partner"] == code]
            observed_skus = int(observed[observed["sell_out_quantity"].notna()]["sku"].nunique())
            latest = observed.loc[observed["sell_out_quantity"].notna(), "month"]
        summaries.append({
            "code": code, "name": _text(partner["Nome fictício"]), "type": _text(partner["Tipo"]),
            "visibility_source": "faturamento_direto" if code in direct else "sell_out_parceiro",
            "region": _text(partner.get("Região")), "channel": _text(partner.get("Canal principal")),
            "state": _text(partner.get("UF")), "city": _text(partner.get("Cidade")),
            "observed_skus": observed_skus, "linked_skus": len(subset), "total_catalog_skus": total_skus,
            "coverage": observed_skus / total_skus if total_skus else 0,
            "latest_sell_out_month": None if latest.empty else str(latest.max()),
            "backlog_quantity": sum(row["backlog_quantity"] for row in subset),
            "action_counts": {a: sum(row["action"] == a for row in subset) for a in ACTION_LABELS},
            "quality_counts": {q: sum(row["data_quality"] == q for row in subset) for q in ("sufficient", "stale", "insufficient")},
        })
    return {"reference_month": None if reference is None else str(reference), "partners": summaries, "items": rows,
            "thresholds": cfg, "field_nature": FIELD_NATURE, "limitation": LIMITATION}
