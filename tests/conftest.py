import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def tabela(linhas, inicio="2015-01-05"):
    """Cria preços de mentira: lista de (abertura, maxima, minima, fechamento)."""
    datas = pd.bdate_range(inicio, periods=len(linhas))
    df = pd.DataFrame(linhas, index=datas, columns=["abertura", "maxima", "minima", "fechamento"])
    df["volume"] = 1000
    df.index.name = "data"
    return df


@pytest.fixture
def regras():
    return {
        "periodos": {"treino_inicio": "2010-01-01", "treino_fim": "2020-12-31", "cego_inicio": "2021-01-01"},
        "contrato": {"dolares_por_ponto": 2.0, "tick": 0.25, "comissao_por_lado": 0.62, "slippage_ticks_por_lado": 1},
    }
