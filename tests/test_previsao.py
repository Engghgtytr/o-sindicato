"""O previsor aprende só com o passado e mede o acerto com honestidade."""
import numpy as np
import pandas as pd

from conftest import tabela
from sindicato.previsao import Logistica, alvo, avaliar_acerto, indicadores, prever_amanha, walk_forward


def serie_com_padrao(n=2600, inverte_em=None, semente=1):
    """Preços onde "subiu hoje → sobe amanhã" (momentum). Opcional: o padrão inverte numa data."""
    rng = np.random.default_rng(semente)
    datas = pd.bdate_range("2010-01-04", periods=n)
    ret = np.zeros(n)
    ret[0] = 0.01
    for i in range(1, n):
        sinal = 1 if ret[i - 1] > 0 else -1
        if inverte_em is not None and datas[i] >= pd.Timestamp(inverte_em):
            sinal = -sinal
        ret[i] = sinal * abs(rng.normal(0.004, 0.01)) if rng.random() < 0.8 else -sinal * abs(rng.normal(0.004, 0.01))
    fech = 100 * np.exp(np.cumsum(ret))
    abert = np.r_[fech[0], fech[:-1]]
    return tabela(list(zip(abert, np.maximum(abert, fech) * 1.002, np.minimum(abert, fech) * 0.998, fech)), inicio="2010-01-04")


def test_alvo_e_indicadores_nao_olham_amanha():
    df = serie_com_padrao(400)
    y = alvo(df)
    assert np.isnan(y.iloc[-1])  # o último dia não tem "amanhã"
    x_todo, x_cortado = indicadores(df), indicadores(df.iloc[:300])
    pd.testing.assert_frame_equal(x_todo.iloc[:300], x_cortado)


def test_aprende_um_padrao_claro():
    df = serie_com_padrao()
    prob = walk_forward(df)
    acerto = avaliar_acerto(df, prob)
    assert acerto["acerto_pct"] > 65  # o padrão existe e é forte: tem que achar
    assert acerto["ganhou_do_sempre_sobe"]


def test_nao_ve_o_ano_que_esta_prevendo():
    # O padrão inverte em 2017. Se o modelo de 2017 "visse" 2017, acertaria; como só vê até 2016, erra.
    df = serie_com_padrao(inverte_em="2017-01-01")
    prob = walk_forward(df)
    ano_2017 = df.index.year == 2017
    acerto_2017 = avaliar_acerto(df[ano_2017], prob[ano_2017])
    assert acerto_2017["acerto_pct"] < 40
    # Em 2018 ele já aprendeu um pouco com 2017, mas o histórico antigo ainda pesa.
    acerto_2016 = avaliar_acerto(df[df.index.year == 2016], prob[df.index.year == 2016])
    assert acerto_2016["acerto_pct"] > 65


def test_ruido_puro_nao_ganha_do_chute():
    rng = np.random.default_rng(9)
    n = 2600
    fech = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    abert = np.r_[fech[0], fech[:-1]]
    df = tabela(list(zip(abert, np.maximum(abert, fech) * 1.002, np.minimum(abert, fech) * 0.998, fech)), inicio="2010-01-04")
    acerto = avaliar_acerto(df, walk_forward(df))
    assert not acerto["ganhou_do_sempre_sobe"]
    assert 40 < acerto["acerto_pct"] < 60


def test_resultado_vira_json_com_tipos_certos():
    import json

    df = serie_com_padrao(900)
    texto = json.dumps(avaliar_acerto(df, walk_forward(df)), default=str)
    assert '"ganhou_do_sempre_sobe": "' not in texto  # nunca como texto "True"/"False"


def test_prever_amanha_da_uma_chance():
    r = prever_amanha(serie_com_padrao(900))
    assert 0 <= r["chance_subir_pct"] <= 100
    assert r["leitura"] in ("sobe", "cai", "incerto (perto de 50%)")


def test_logistica_separa_o_obvio():
    x = np.r_[np.full((50, 1), -1.0), np.full((50, 1), 1.0)]
    y = np.r_[np.zeros(50), np.ones(50)]
    m = Logistica().treinar(x, y)
    assert m.prob(np.array([[1.0]]))[0] > 0.9 and m.prob(np.array([[-1.0]]))[0] < 0.1
