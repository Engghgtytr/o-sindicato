"""O motor não pode mentir: cada regra com um exemplo calculado à mão."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from conftest import tabela
from sindicato.estrategia import Estrategia
from sindicato.motor import Custos, rodar

CUSTOS = Custos(dolares_por_ponto=2.0, tick=0.25, comissao_por_lado=0.62, slippage_ticks=1)
COMISSAO = 0.62 * 2  # ida e volta


@dataclass
class Roteiro(Estrategia):
    """Estratégia de teste: sinais, stop e alvo fixos, escolhidos à mão."""

    sinal_em: tuple = (0,)
    direcao: int = 1
    stop_pts: float = 10.0
    alvo_pts: float = 20.0
    max_dias: int = 99
    nome = "roteiro"

    def sinais(self, df):
        s = pd.Series(0, index=df.index)
        s.iloc[list(self.sinal_em)] = self.direcao
        return s

    def distancias(self, df):
        return pd.Series(self.stop_pts, index=df.index), pd.Series(self.alvo_pts, index=df.index)


def test_entra_na_abertura_do_dia_seguinte_com_slippage():
    df = tabela([(100, 101, 99, 100), (102, 103, 101, 102), (102, 103, 101, 102)])
    r = rodar(df, Roteiro(), CUSTOS)
    t = r.trades.iloc[0]
    assert t["entrada"] == df.index[1]  # sinal no dia 0 → entra no dia 1
    assert t["preco_entrada"] == 102.25  # abertura 102 + 1 tick contra
    assert t["motivo"] == "fim_dos_dados"


def test_alvo_paga_com_custos_exatos():
    # Abertura 100, entra a 100.25 (1 tick pior); alvo em 120 (20 pontos da abertura).
    df = tabela([(100, 100, 100, 100), (100, 101, 99, 100), (110, 125, 109, 124)])
    t = rodar(df, Roteiro(), CUSTOS).trades.iloc[0]
    assert t["motivo"] == "alvo"
    assert t["preco_saida"] == 119.75  # 120 - 1 tick
    assert t["pontos"] == pytest.approx(19.5)
    assert t["resultado_usd"] == pytest.approx(19.5 * 2 - COMISSAO)


def test_stop_e_alvo_no_mesmo_dia_conta_o_stop():
    df = tabela([(100, 100, 100, 100), (100, 100.5, 99.5, 100), (100, 130, 80, 100)])
    t = rodar(df, Roteiro(), CUSTOS).trades.iloc[0]
    assert t["motivo"] == "stop"
    assert t["resultado_usd"] < 0


def test_gap_alem_do_stop_sai_na_abertura():
    # Stop em 90; o dia 2 abre em 80 (notícia de madrugada).
    df = tabela([(100, 100, 100, 100), (100, 101, 99, 100), (80, 85, 78, 84)])
    t = rodar(df, Roteiro(), CUSTOS).trades.iloc[0]
    assert t["motivo"] == "gap_stop"
    assert t["preco_saida"] == 79.75  # pior que o stop: abertura 80 - 1 tick
    assert t["resultado_usd"] == pytest.approx((79.75 - 100.25) * 2 - COMISSAO)


def test_venda_ganha_quando_cai():
    df = tabela([(100, 100, 100, 100), (100, 101, 99, 100), (95, 96, 70, 75)])
    t = rodar(df, Roteiro(direcao=-1), CUSTOS).trades.iloc[0]
    assert t["direcao"] == "venda"
    assert t["preco_entrada"] == 99.75  # vende 1 tick abaixo
    assert t["motivo"] == "alvo"  # alvo em 80
    assert t["resultado_usd"] > 0


def test_saida_por_tempo_na_abertura_seguinte():
    linhas = [(100, 100.5, 99.5, 100)] * 6
    t = rodar(tabela(linhas), Roteiro(max_dias=2), CUSTOS).trades.iloc[0]
    assert t["motivo"] == "tempo"
    assert t["saida"] == tabela(linhas).index[3]  # entrou no dia 1, 2 dias, sai na abertura do dia 3


def test_custos_mudam_o_resultado():
    df = tabela([(100, 100, 100, 100), (100, 101, 99, 100), (110, 125, 109, 124)])
    sem = rodar(df, Roteiro(), Custos(2.0, 0.25, 0.0, 0)).trades.iloc[0]["resultado_usd"]
    com = rodar(df, Roteiro(), CUSTOS).trades.iloc[0]["resultado_usd"]
    assert sem == pytest.approx(40.0)
    assert com == pytest.approx(40.0 - 2 * 0.25 * 2 - COMISSAO)


def test_nao_opera_antes_do_inicio_permitido():
    df = tabela([(100, 101, 99, 100)] * 6)
    r = rodar(df, Roteiro(sinal_em=(0, 3)), CUSTOS, inicio_operacao=df.index[3])
    assert list(r.trades["entrada"]) == [df.index[4]]  # o sinal do dia 0 é ignorado
    assert r.patrimonio.index[0] == df.index[3]


def test_patrimonio_inclui_posicao_aberta():
    df = tabela([(100, 100, 100, 100), (100, 101, 99, 100), (100, 106, 99, 105), (105, 106, 104, 105)])
    p = rodar(df, Roteiro(), CUSTOS).patrimonio
    assert p.iloc[2] == pytest.approx((105 - 100.25) * 2)  # ainda aberta, marcada no fechamento


def test_preco_que_so_sobe_comprado_sempre_ganha():
    precos = np.arange(100, 400, 1.0)
    linhas = [(p, p + 2, p - 0.5, p + 1.5) for p in precos]
    from sindicato.estrategia import Rompimento

    r = rodar(tabela(linhas), Rompimento(dias=5), CUSTOS)
    assert len(r.trades) > 5
    assert (r.trades["resultado_usd"] > 0).all()
