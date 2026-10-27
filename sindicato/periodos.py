"""O cofre do teste cego.

Treino (2010–2020): pode testar e mexer à vontade.
Cego (2021→hoje): só abre com um motivo escrito, e cada abertura fica no diário.
Cada vez que você olha o cego e volta a mexer, ele deixa de ser cego. O diário mostra isso.
"""
from __future__ import annotations

import pandas as pd

from .diario import Diario


class CofreFechado(Exception):
    pass


def fatiar(
    df: pd.DataFrame,
    periodo: str,
    regras: dict,
    diario: Diario | None = None,
    motivo: str = "",
    aquecimento: int = 250,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Devolve (dados, data em que as operações podem começar).

    No cego, os dados vêm com `aquecimento` dias antes de 2021 só para os indicadores
    (uma média de 200 dias precisa de 200 dias para existir). Operar, só a partir de 2021.
    """
    p = regras["periodos"]
    if periodo == "treino":
        dados = df.loc[p["treino_inicio"] : p["treino_fim"]]
        return dados, dados.index[0]

    if periodo == "cego":
        if not motivo.strip():
            raise CofreFechado(
                "O teste cego só abre com um motivo escrito (ex.: 'versão final da estratégia X'). "
                "Cada abertura fica registrada no diário."
            )
        inicio = pd.Timestamp(p["cego_inicio"])
        posicao = df.index.searchsorted(inicio)
        dados = df.iloc[max(0, posicao - aquecimento) :]
        (diario or Diario()).registrar("abriu_cego", motivo=motivo.strip())
        return dados, inicio

    raise ValueError("Período deve ser 'treino' ou 'cego'.")
