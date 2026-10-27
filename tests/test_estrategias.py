"""Nenhuma estratégia pode ver o futuro.

Teste: calcula os sinais com a série inteira e com a série cortada em vários pontos.
Os sinais até o corte precisam ser idênticos. Se mudarem, a estratégia usou dado do futuro.
"""
import numpy as np
import pandas as pd
import pytest

from conftest import tabela
from sindicato.estrategia import ESTRATEGIAS, atr, ifr


def passeio_aleatorio(n=600, semente=7):
    rng = np.random.default_rng(semente)
    fech = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    abert = np.r_[fech[0], fech[:-1]] * (1 + rng.normal(0, 0.002, n))
    maxi = np.maximum(abert, fech) * (1 + rng.uniform(0, 0.01, n))
    mini = np.minimum(abert, fech) * (1 - rng.uniform(0, 0.01, n))
    return tabela(list(zip(abert, maxi, mini, fech)))


@pytest.mark.parametrize("nome", list(ESTRATEGIAS))
def test_sinais_nao_usam_o_futuro(nome):
    df = passeio_aleatorio()
    est = ESTRATEGIAS[nome]()
    inteiro = est.sinais(df)
    saida_inteira = est.saida(df)
    stop_inteiro, _ = est.distancias(df)
    for corte in (250, 333, 480, 599):
        parte = df.iloc[:corte]
        pd.testing.assert_series_equal(est.sinais(parte), inteiro.iloc[:corte], check_names=False)
        pd.testing.assert_series_equal(est.saida(parte), saida_inteira.iloc[:corte], check_names=False)
        pd.testing.assert_series_equal(est.distancias(parte)[0], stop_inteiro.iloc[:corte], check_names=False)


def test_atr_conta_o_gap():
    df = tabela([(100, 101, 99, 100), (110, 111, 109, 110)])
    assert atr(df, 1).iloc[1] == 11  # da mínima de hoje? não: do fechamento de ontem (100) até a máxima (111)


def test_ifr_extremos():
    sobe = pd.Series(np.arange(1, 30, dtype=float))
    desce = pd.Series(np.arange(30, 1, -1, dtype=float))
    assert ifr(sobe).iloc[-1] > 95
    assert ifr(desce).iloc[-1] < 5
