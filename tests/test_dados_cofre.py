import numpy as np
import pandas as pd
import pytest

from conftest import tabela
from sindicato.dados import limpar, salvar_historico
from sindicato.diario import Diario
from sindicato.metricas import calcular
from sindicato.periodos import CofreFechado, fatiar


def bruto_yfinance(linhas, datas):
    """Imita o formato do yfinance: colunas em dois níveis (campo, ticker)."""
    cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["NQ=F"]])
    return pd.DataFrame([list(l) for l in linhas], index=pd.DatetimeIndex(datas), columns=cols)


def test_limpar_remove_lixo_e_padroniza():
    datas = ["2020-01-03", "2020-01-02", "2020-01-02", "2020-01-06", "2020-01-07", "2020-01-08"]
    linhas = [
        (10, 11, 9, 10.5, 100),
        (10, 11, 9, 10, 100),
        (10, 11, 9, 10.2, 100),  # data repetida: fica a última
        (np.nan, np.nan, np.nan, np.nan, np.nan),  # feriado vazio
        (0, 0, 0, 0, 0),  # zerada
        (10, 9, 8, 10, 50),  # máxima menor que a abertura: incoerente
    ]
    df, removidas = limpar(bruto_yfinance(linhas, datas))
    assert list(df.columns) == ["abertura", "maxima", "minima", "fechamento", "volume"]
    assert list(df.index.strftime("%Y-%m-%d")) == ["2020-01-02", "2020-01-03"]
    assert df.loc["2020-01-02", "fechamento"] == 10.2
    assert removidas == {"vazias": 1, "zeradas": 1, "repetidas": 1, "incoerentes": 1}


def test_atualiza_so_o_que_falta(tmp_path):
    pedidos = []

    def falso(ticker, inicio, intervalo):
        pedidos.append(inicio)
        datas = pd.bdate_range(inicio, periods=5)
        return bruto_yfinance([(10, 11, 9, 10, 1)] * 5, datas)

    df1, _ = salvar_historico("NQ=F", inicio="2020-01-01", baixar=falso, pasta=tmp_path)
    df2, info = salvar_historico("NQ=F", baixar=falso, pasta=tmp_path)
    assert pedidos[0] == "2020-01-01"
    assert pedidos[1] > "2020-01-01"  # a 2ª vez pede só a partir dos últimos dias
    assert df2.index.is_unique and df2.index.is_monotonic_increasing
    assert len(df2) >= len(df1)


def test_cofre_treino_nao_tem_2021(regras, tmp_path):
    df = tabela([(1, 2, 0.5, 1.5)] * 3000, inicio="2010-01-04")
    treino, inicio = fatiar(df, "treino", regras, Diario(tmp_path / "d.jsonl"))
    assert treino.index.max() <= pd.Timestamp("2020-12-31")
    assert inicio == treino.index[0]


def test_cofre_cego_exige_motivo_e_registra(regras, tmp_path):
    diario = Diario(tmp_path / "d.jsonl")
    df = tabela([(1, 2, 0.5, 1.5)] * 3000, inicio="2010-01-04")
    with pytest.raises(CofreFechado):
        fatiar(df, "cego", regras, diario)
    assert diario.contar("abriu_cego") == 0

    cego, inicio = fatiar(df, "cego", regras, diario, motivo="versão final do rompimento")
    assert inicio == pd.Timestamp("2021-01-01")
    assert cego.index.min() < inicio  # dias de aquecimento só para os indicadores
    assert diario.contar("abriu_cego") == 1


def test_diario_so_cresce(tmp_path):
    d = Diario(tmp_path / "d.jsonl")
    d.registrar("teste", estrategia="a")
    d.registrar("teste", estrategia="b")
    assert [r["n"] for r in d.ler()] == [1, 2]
    assert d.contar("teste") == 2


def test_metricas_calculadas_a_mao():
    trades = pd.DataFrame({"resultado_usd": [100.0, -50.0, 200.0, -50.0], "custos_usd": [3.0] * 4})
    patrimonio = pd.Series([100.0, 50.0, 250.0, 200.0], index=pd.bdate_range("2020-01-01", periods=4))
    m = calcular(trades, patrimonio)
    assert m["taxa_acerto_pct"] == 50.0
    assert m["profit_factor"] == 3.0  # 300 / 100
    assert m["payoff"] == 3.0  # média 150 / média 50
    assert m["drawdown_max_usd"] == 50.0
    assert m["lucro_liquido"] == 200.0
