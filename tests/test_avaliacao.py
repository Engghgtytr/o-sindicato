"""O teste da honestidade tem que separar vantagem de sorte."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sindicato.avaliacao import coin_flip, comprar_e_segurar, monte_carlo, p_valor, veredito
from sindicato.estrategia import Estrategia
from sindicato.metricas import calcular
from sindicato.motor import Custos, rodar
from test_estrategias import passeio_aleatorio

CUSTOS = Custos(2.0, 0.25, 0.62, 1)


@dataclass
class Trapaceira(Estrategia):
    """Olha o fechamento de AMANHÃ (proibido!). Serve só para provar que o coin flip detecta vantagem."""

    stop_atr: float = 3.0
    alvo_atr: float = 3.0
    max_dias: int = 1
    nome = "trapaceira"

    def sinais(self, df):
        amanha_sobe = df["fechamento"].shift(-2) > df["abertura"].shift(-1)
        return amanha_sobe.astype(int)


@dataclass
class Aleatoria(Estrategia):
    max_dias: int = 5
    nome = "aleatoria"

    def sinais(self, df):
        rng = np.random.default_rng(123)
        return pd.Series((rng.random(len(df)) < 0.05).astype(int), index=df.index)


def avaliar(est, df):
    inicio = df.index[60]
    r = rodar(df, est, CUSTOS, 1, inicio)
    m = calcular(r.trades, r.patrimonio)
    cf = coin_flip(df, est, CUSTOS, 1, inicio, alvo_trades=m["trades"], rodadas=200)
    return m, cf


def test_coin_flip_detecta_vantagem_de_verdade():
    df = passeio_aleatorio(800, semente=3)
    m, cf = avaliar(Trapaceira(), df)
    assert p_valor(m["lucro_liquido"], cf["lucros"]) < 0.01


def test_estrategia_aleatoria_nao_passa():
    df = passeio_aleatorio(800, semente=4)
    m, cf = avaliar(Aleatoria(), df)
    p = p_valor(m["lucro_liquido"], cf["lucros"])
    assert p > 0.05
    assert not veredito(m["lucro_liquido"], p, 1, 0, {})["aprovada"]


def test_coin_flip_faz_mais_ou_menos_o_mesmo_numero_de_trades():
    df = passeio_aleatorio(800, semente=5)
    m, cf = avaliar(Aleatoria(), df)
    assert abs(cf["trades"].mean() - m["trades"]) / m["trades"] < 0.25


def test_p_valor_nunca_e_zero():
    assert p_valor(1e9, np.zeros(499)) == 1 / 500
    assert p_valor(-1e9, np.zeros(499)) == 1.0


def test_muitas_versoes_derrubam_a_aprovacao():
    mc = {"chance_estourar_limite_pct": 0}
    assert veredito(1000, 0.002, 1, 0, mc)["aprovada"]
    v = veredito(1000, 0.002, 100, 0, mc)  # mesma estratégia, mas é a 100ª tentativa
    assert not v["aprovada"]
    assert v["p_ajustado"] == 0.2


def test_monte_carlo_so_ganhos_nunca_perde():
    mc = monte_carlo(np.array([10.0, 20.0, 5.0]), limite_perda=100, rodadas=500)
    assert mc["chance_terminar_no_prejuizo_pct"] == 0
    assert mc["drawdown_p95"] == 0


def test_monte_carlo_mede_o_risco_de_quebrar():
    mc = monte_carlo(np.array([100.0, -100.0] * 20), limite_perda=300, rodadas=2000)
    assert 0 < mc["chance_estourar_limite_pct"] < 100


def test_comprar_e_segurar():
    df = passeio_aleatorio(300, semente=6)
    bh = comprar_e_segurar(df, CUSTOS, 1, df.index[0])
    esperado = ((df["fechamento"].iloc[-1] - 0.25) - (df["abertura"].iloc[0] + 0.25)) * 2 - 1.24
    assert abs(bh["lucro_liquido"] - round(esperado, 2)) < 0.01
