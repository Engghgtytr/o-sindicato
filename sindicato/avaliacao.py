"""O teste da honestidade: a estratégia contra a sorte, contra "comprar e segurar"
e contra a ordem azarada dos próprios trades.

1. Coin flip: 500 versões com entradas sorteadas, mas o MESMO stop, alvo, regra de saída,
   direção, custos e (em média) o mesmo número de trades. Se a sorte faz igual, a
   estratégia não é a razão do lucro.
2. Comprar e segurar: num mercado que subiu 7 vezes, qualquer compra "ganha".
3. Monte Carlo (bootstrap): sorteia os trades com reposição milhares de vezes para ver
   o pior caminho provável e a chance de estourar o limite de perda.
4. Muitas tentativas: o diário conta quantas versões já foram testadas; o p-valor é
   multiplicado por esse número (correção de Bonferroni). Testar 26 mil coisas e achar
   5 que "passam" não prova nada sem essa conta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .estrategia import Estrategia
from .metricas import calcular
from .motor import Custos, preparar, rodar


def comprar_e_segurar(df: pd.DataFrame, custos: Custos, contratos: int, inicio: pd.Timestamp) -> dict:
    d = df[df.index >= inicio]
    entrada = d["abertura"].iloc[0] + custos.slip
    saida = d["fechamento"].iloc[-1] - custos.slip
    mult = custos.dolares_por_ponto * contratos
    curva = (d["fechamento"] - entrada) * mult
    topo = curva.cummax().clip(lower=0)
    return {
        "lucro_liquido": round((saida - entrada) * mult - custos.comissao_por_lado * contratos * 2, 2),
        "drawdown_max_usd": round((topo - curva).max(), 2),
        "curva": curva,
    }


def _direcao(estrategia: Estrategia, df: pd.DataFrame) -> np.ndarray:
    """Direções que a estratégia usa (só compra, só venda ou as duas)."""
    s = estrategia.sinais(df)
    lados = sorted(set(int(x) for x in s.unique() if x != 0))
    return np.array(lados or [1])


def coin_flip(
    df: pd.DataFrame,
    estrategia: Estrategia,
    custos: Custos,
    contratos: int,
    inicio: pd.Timestamp,
    alvo_trades: int,
    rodadas: int = 500,
    semente: int = 42,
) -> dict:
    """Roda `rodadas` versões aleatórias e devolve os lucros e as estatísticas de cada uma."""
    rng = np.random.default_rng(semente)
    prep = preparar(df, estrategia)
    lados = _direcao(estrategia, df)
    pode = (df.index >= inicio) & np.isfinite(prep["dist_stop"])
    n = len(df)

    def uma(prob: float) -> tuple[float, int, float]:
        entra = (rng.random(n) < prob) & pode
        sinais = np.where(entra, rng.choice(lados, size=n), 0)
        r = rodar(df, estrategia, custos, contratos, inicio, sinais=sinais, preparo=prep)
        m = calcular(r.trades, r.patrimonio)
        return m.get("lucro_liquido", 0.0), m["trades"], m.get("drawdown_max_usd", 0.0)

    # Calibra a chance diária de entrar para dar, em média, o mesmo número de trades.
    baixo, alto = 1e-4, 1.0
    for _ in range(14):
        meio = (baixo * alto) ** 0.5
        media = np.mean([uma(meio)[1] for _ in range(6)])
        baixo, alto = (meio, alto) if media < alvo_trades else (baixo, meio)
    prob = (baixo * alto) ** 0.5

    lucros, trades, quedas = map(np.array, zip(*(uma(prob) for _ in range(rodadas))))
    return {"rodadas": rodadas, "prob_entrada_dia": prob, "lucros": lucros, "trades": trades, "drawdowns": quedas}


def p_valor(lucro_estrategia: float, lucros_sorte: np.ndarray) -> float:
    """Chance de a sorte fazer igual ou melhor (com a correção +1 para não dar zero)."""
    return (np.sum(lucros_sorte >= lucro_estrategia) + 1) / (len(lucros_sorte) + 1)


def monte_carlo(resultados: np.ndarray, limite_perda: float, rodadas: int = 5000, semente: int = 7) -> dict:
    """Sorteia a sequência de trades com reposição e mede o pior caminho."""
    if len(resultados) == 0:
        return {"rodadas": 0}
    rng = np.random.default_rng(semente)
    amostras = rng.choice(resultados, size=(rodadas, len(resultados)), replace=True)
    curvas = amostras.cumsum(axis=1)
    topo = np.maximum.accumulate(np.maximum(curvas, 0), axis=1)
    quedas = (topo - curvas).max(axis=1)
    finais = curvas[:, -1]
    return {
        "rodadas": rodadas,
        "lucro_p5": round(float(np.percentile(finais, 5)), 2),
        "lucro_mediana": round(float(np.median(finais)), 2),
        "lucro_p95": round(float(np.percentile(finais, 95)), 2),
        "drawdown_mediana": round(float(np.median(quedas)), 2),
        "drawdown_p95": round(float(np.percentile(quedas, 95)), 2),
        "chance_estourar_limite_pct": round(100 * float(np.mean(quedas >= limite_perda)), 1),
        "chance_terminar_no_prejuizo_pct": round(100 * float(np.mean(finais <= 0)), 1),
    }


def veredito(lucro: float, p: float, versoes: int, comprar_segurar: float, mc: dict, alfa: float = 0.05) -> dict:
    p_ajustado = min(1.0, p * max(versoes, 1))
    motivos = []
    if lucro <= 0:
        motivos.append("deu prejuízo depois dos custos")
    if p >= alfa:
        motivos.append(f"a sorte fez igual ou melhor em {p:.0%} das vezes")
    elif p_ajustado >= alfa:
        motivos.append(f"passou da sorte (p={p:.3f}), mas com {versoes} versões testadas pode ser acaso (p ajustado={p_ajustado:.2f})")
    if mc.get("chance_estourar_limite_pct", 0) > 5:
        motivos.append(f"{mc['chance_estourar_limite_pct']}% de chance de estourar o limite de perda")
    return {
        "aprovada": not motivos,
        "motivos": motivos or ["venceu a sorte mesmo contando todas as versões testadas"],
        "p_valor": round(p, 4),
        "p_ajustado": round(p_ajustado, 4),
        "versoes_testadas": versoes,
        "ganhou_de_comprar_e_segurar": lucro > comprar_segurar,
    }
