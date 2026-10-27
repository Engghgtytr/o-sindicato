"""Métricas do relatório. Lucro sozinho não diz nada; estas dizem."""
from __future__ import annotations

import math

import pandas as pd


def calcular(trades: pd.DataFrame, patrimonio: pd.Series) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "lucro_liquido": 0.0, "aviso": "Nenhum trade: a estratégia não deu sinal neste período."}

    r = trades["resultado_usd"]
    ganhos, perdas = r[r > 0], r[r <= 0]
    lucro_bruto, prejuizo_bruto = ganhos.sum(), -perdas.sum()

    # Drawdown: a maior queda do patrimônio a partir de um topo anterior.
    topo = patrimonio.cummax().clip(lower=0)
    queda = topo - patrimonio
    anos = max((patrimonio.index[-1] - patrimonio.index[0]).days / 365.25, 1e-9)

    sequencia = maior = 0
    for x in r:
        sequencia = sequencia + 1 if x <= 0 else 0
        maior = max(maior, sequencia)

    return {
        "trades": n,
        "trades_por_ano": round(n / anos, 1),
        "lucro_liquido": round(r.sum(), 2),
        "taxa_acerto_pct": round(100 * len(ganhos) / n, 1),
        # Profit factor < 1 = estratégia perdedora. O vídeo/plano mira acima de 1,3.
        "profit_factor": round(lucro_bruto / prejuizo_bruto, 2) if prejuizo_bruto > 0 else math.inf,
        "payoff": round(ganhos.mean() / -perdas.mean(), 2) if len(ganhos) and len(perdas) and perdas.mean() < 0 else None,
        "media_por_trade": round(r.mean(), 2),
        "drawdown_max_usd": round(queda.max(), 2),
        "maior_sequencia_perdas": maior,
        "custos_totais_usd": round(trades["custos_usd"].sum(), 2),
    }


def imposto_estimado(trades: pd.DataFrame, aliquotas: dict) -> dict:
    """Estimativa do IR brasileiro sobre o lucro de contratos futuros.

    - Day trade (entra e sai no mesmo dia): 20%. Swing trade (fica de um dia para o outro): 15%.
    - Apurado por mês. Prejuízo de um mês abate lucro dos meses seguintes, cada tipo no seu
      "pote" (prejuízo de day trade só compensa lucro de day trade).
    É uma estimativa para comparar estratégias, não substitui o cálculo do DARF.
    """
    if trades.empty:
        return {"imposto": 0.0, "lucro_depois_do_ir": 0.0}
    t = trades.assign(
        mes=pd.to_datetime(trades["saida"]).dt.to_period("M"),
        tipo=(pd.to_datetime(trades["entrada"]).dt.date == pd.to_datetime(trades["saida"]).dt.date).map(
            {True: "day_trade", False: "swing_trade"}
        ),
    )
    total = 0.0
    por_tipo = {}
    for tipo, grupo in t.groupby("tipo"):
        prejuizo_acumulado = 0.0
        imposto_tipo = 0.0
        for _, resultado in grupo.groupby("mes")["resultado_usd"].sum().sort_index().items():
            base = resultado - prejuizo_acumulado
            if base > 0:
                imposto_tipo += base * aliquotas[tipo]
                prejuizo_acumulado = 0.0
            else:
                prejuizo_acumulado = -base
        por_tipo[tipo] = round(imposto_tipo, 2)
        total += imposto_tipo
    return {
        "imposto": round(total, 2),
        "por_tipo": por_tipo,
        "lucro_depois_do_ir": round(trades["resultado_usd"].sum() - total, 2),
    }


def resumo_texto(nome: str, periodo: str, m: dict, simbolo: str = "US$") -> str:
    if m["trades"] == 0:
        return f"{nome} [{periodo}]: {m['aviso']}"
    pf = "∞" if m["profit_factor"] == math.inf else m["profit_factor"]
    return (
        f"{nome} [{periodo}]  trades {m['trades']} ({m['trades_por_ano']}/ano)  "
        f"lucro {simbolo} {m['lucro_liquido']:,.0f}  acerto {m['taxa_acerto_pct']}%  PF {pf}  "
        f"payoff {m['payoff']}  drawdown {simbolo} {m['drawdown_max_usd']:,.0f}  custos {simbolo} {m['custos_totais_usd']:,.0f}"
    )
