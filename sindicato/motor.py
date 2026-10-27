"""Motor de backtest: o "testador que não pode mentir".

Regras (todas com teste automático em tests/test_motor.py):
1. Sinal no fechamento do dia i → entrada na ABERTURA do dia i+1. Nunca no mesmo candle.
2. Stop e alvo ficam "na corretora" desde a entrada.
3. Se o dia toca o stop E o alvo, conta o STOP (não dá para saber a ordem dentro do dia diário).
4. Se o dia abre além do stop (gap), a saída é na abertura, pior que o stop.
5. Toda ordem paga comissão e slippage (ticks contra você), inclusive no alvo.
6. Uma posição por vez. O que estiver aberto no fim dos dados sai no último fechamento.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .estrategia import Estrategia


@dataclass
class Custos:
    dolares_por_ponto: float = 2.0
    tick: float = 0.25
    comissao_por_lado: float = 0.62
    slippage_ticks: int = 1

    @classmethod
    def das_regras(cls, regras: dict) -> "Custos":
        c = regras["contrato"]
        # "dolares_por_ponto" é o nome antigo; no mini índice o valor é em reais.
        valor = c.get("valor_por_ponto", c.get("dolares_por_ponto"))
        return cls(valor, c["tick"], c["comissao_por_lado"], c["slippage_ticks_por_lado"])

    @property
    def slip(self) -> float:
        return self.tick * self.slippage_ticks


@dataclass
class Resultado:
    trades: pd.DataFrame
    patrimonio: pd.Series  # resultado acumulado em US$ a cada fechamento (inclui posição aberta)


def preparar(df: pd.DataFrame, estrategia: Estrategia) -> dict:
    """Calcula uma vez o que não muda entre rodadas: regra de saída, stop e alvo."""
    dist_stop, dist_alvo = (s.reindex(df.index).to_numpy(float) for s in estrategia.distancias(df))
    return {
        "sair": estrategia.saida(df).reindex(df.index).fillna(False).to_numpy(bool),
        "dist_stop": dist_stop,
        "dist_alvo": dist_alvo,
    }


COLUNAS_TRADES = [
    "entrada", "saida", "direcao", "preco_entrada", "preco_saida", "motivo", "pontos", "resultado_usd", "custos_usd",
]


def rodar(
    df: pd.DataFrame,
    estrategia: Estrategia,
    custos: Custos,
    contratos: int = 1,
    inicio_operacao: pd.Timestamp | None = None,
    sinais: pd.Series | np.ndarray | None = None,
    preparo: dict | None = None,
) -> Resultado:
    """Roda a estratégia nos dados.

    `sinais` substitui as entradas da estratégia (o coin flip usa isso, mantendo stop, alvo e saídas).
    `preparo` reaproveita saídas e distâncias já calculadas (para rodar 500 vezes sem recalcular).
    """
    o, h, l, c = (df[k].to_numpy(float) for k in ("abertura", "maxima", "minima", "fechamento"))
    datas = df.index
    preparo = preparo or preparar(df, estrategia)
    if sinais is None:
        sinal = estrategia.sinais(df).reindex(datas).fillna(0).to_numpy(int)
    else:
        sinal = np.asarray(sinais.reindex(datas).fillna(0) if isinstance(sinais, pd.Series) else sinais, dtype=int)
    sair, dist_stop, dist_alvo = preparo["sair"], preparo["dist_stop"], preparo["dist_alvo"]
    pode_operar = np.ones(len(df), bool) if inicio_operacao is None else (datas >= inicio_operacao)

    mult = custos.dolares_por_ponto * contratos
    comissao = custos.comissao_por_lado * contratos * 2
    slip = custos.slip

    trades = []
    realizado = 0.0
    patrimonio = np.zeros(len(df))
    pos = None  # dict com direcao, entrada, stop, alvo, data, dias
    sair_na_abertura = False

    def fechar(i, preco, motivo):
        nonlocal pos, realizado
        d = pos["direcao"]
        preco_saida = preco - slip * d  # slippage contra você
        pontos = (preco_saida - pos["entrada"]) * d
        resultado = pontos * mult - comissao
        realizado += resultado
        trades.append(
            {
                "entrada": pos["data"], "saida": datas[i], "direcao": "compra" if d == 1 else "venda",
                "preco_entrada": pos["entrada"], "preco_saida": preco_saida, "motivo": motivo,
                "pontos": pontos, "resultado_usd": resultado, "custos_usd": comissao + 2 * slip * mult,
            }
        )
        pos = None

    for i in range(len(df)):
        # 1) Ordens decididas no fechamento de ontem executam na abertura de hoje.
        if pos is not None and sair_na_abertura:
            fechar(i, o[i], "sinal_saida" if pos["dias"] < estrategia.max_dias else "tempo")
        sair_na_abertura = False

        if pos is None and i > 0 and sinal[i - 1] != 0 and pode_operar[i] and np.isfinite(dist_stop[i - 1]):
            d = sinal[i - 1]
            entrada = o[i] + slip * d
            # Stop e alvo medidos da abertura (o preço de referência), não do preço já com
            # slippage: assim o custo do slippage aparece inteiro na entrada E na saída.
            pos = {
                "direcao": d, "entrada": entrada, "data": datas[i], "dias": 0,
                "stop": o[i] - d * dist_stop[i - 1], "alvo": o[i] + d * dist_alvo[i - 1],
            }

        # 2) Durante o dia: stop e alvo.
        if pos is not None:
            d, stop, alvo = pos["direcao"], pos["stop"], pos["alvo"]
            abriu_alem_stop = (o[i] <= stop) if d == 1 else (o[i] >= stop)
            abriu_alem_alvo = (o[i] >= alvo) if d == 1 else (o[i] <= alvo)
            tocou_stop = (l[i] <= stop) if d == 1 else (h[i] >= stop)
            tocou_alvo = (h[i] >= alvo) if d == 1 else (l[i] <= alvo)
            if abriu_alem_stop and datas[i] != pos["data"]:
                fechar(i, o[i], "gap_stop")
            elif abriu_alem_alvo and datas[i] != pos["data"]:
                fechar(i, o[i], "gap_alvo")
            elif tocou_stop:
                fechar(i, stop, "stop")  # se tocou os dois, o stop vence (pior caso)
            elif tocou_alvo:
                fechar(i, alvo, "alvo")

        # 3) No fechamento: decide se sai amanhã.
        if pos is not None:
            pos["dias"] += 1
            if sair[i] or pos["dias"] >= estrategia.max_dias:
                sair_na_abertura = True

        aberto = 0.0 if pos is None else (c[i] - pos["entrada"]) * pos["direcao"] * mult
        patrimonio[i] = realizado + aberto

    if pos is not None:
        fechar(len(df) - 1, c[-1], "fim_dos_dados")
        patrimonio[-1] = realizado

    serie = pd.Series(patrimonio, index=datas, name="patrimonio")
    if inicio_operacao is not None:
        serie = serie[serie.index >= inicio_operacao]
    return Resultado(pd.DataFrame(trades, columns=COLUNAS_TRADES), serie)
