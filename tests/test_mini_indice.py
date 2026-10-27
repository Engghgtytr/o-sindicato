"""Mini índice (WIN): regras, imposto e o Vendedor no horário da B3."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from sindicato.avisos import Avisos
from sindicato.config import carregar_regras, instrumentos_disponiveis
from sindicato.metricas import imposto_estimado
from sindicato.motor import Custos
from sindicato.vendedor import Vendedor
from tests.test_vendedor import SempreCompra

SP = ZoneInfo("America/Sao_Paulo")


def test_regras_dos_dois_mercados():
    assert {"mnq", "win"} <= set(instrumentos_disponiveis())
    nasdaq = carregar_regras()
    assert nasdaq["instrumento"]["id"] == "mnq" and nasdaq["instrumento"]["simbolo"] == "US$"
    assert nasdaq["imposto"] is None
    win = carregar_regras(instrumento="win")
    assert win["instrumento"]["simbolo"] == "R$"
    assert win["dados"]["serie_backtest"] == "^BVSP"
    c = Custos.das_regras(win)
    assert c.dolares_por_ponto == 0.20 and c.tick == 5
    # 1 tick de slippage no WIN = 5 pontos = R$ 1,00
    assert c.slip * c.dolares_por_ponto == pytest.approx(1.0)


def test_mercado_que_nao_existe():
    with pytest.raises(ValueError):
        carregar_regras(instrumento="bitcoin")


def _trades(linhas):
    return pd.DataFrame(
        [{"entrada": pd.Timestamp(e), "saida": pd.Timestamp(s), "resultado_usd": r} for e, s, r in linhas]
    )


ALIQ = {"day_trade": 0.20, "swing_trade": 0.15}


def test_imposto_swing_compensa_prejuizo_do_mes_anterior():
    t = _trades([
        ("2024-01-02", "2024-01-05", -100.0),  # janeiro: prejuízo
        ("2024-02-01", "2024-02-06", 300.0),   # fevereiro: lucro 300 - 100 de prejuízo = base 200
    ])
    ir = imposto_estimado(t, ALIQ)
    assert ir["imposto"] == pytest.approx(200 * 0.15)
    assert ir["lucro_depois_do_ir"] == pytest.approx(200 - 30)


def test_imposto_day_trade_tem_pote_separado():
    t = _trades([
        ("2024-01-02 10:00", "2024-01-02 15:00", 100.0),  # day trade: 20%
        ("2024-01-03", "2024-01-08", -500.0),             # prejuízo de swing não abate day trade
    ])
    ir = imposto_estimado(t, ALIQ)
    assert ir["por_tipo"]["day_trade"] == pytest.approx(20.0)
    assert ir["por_tipo"]["swing_trade"] == 0
    assert ir["imposto"] == pytest.approx(20.0)


def test_sem_trades_sem_imposto():
    assert imposto_estimado(_trades([]), ALIQ)["imposto"] == 0


class FeedB3:
    def __init__(self):
        self.barras = pd.DataFrame(columns=["abertura", "maxima", "minima", "fechamento", "volume"])

    def diario(self):
        datas = pd.bdate_range("2026-10-01", "2026-10-26")
        return pd.DataFrame({"abertura": 130000.0, "maxima": 131000.0, "minima": 129000.0, "fechamento": 130000.0, "volume": 1}, index=datas)

    def minutos(self):
        return self.barras

    def barra(self, hora, a, h, l, c, dia="2026-10-27"):
        self.barras.loc[pd.Timestamp(f"{dia} {hora}", tz=SP).tz_convert("UTC")] = [a, h, l, c, 1]
        self.barras = self.barras.sort_index()


def test_vendedor_win_usa_horario_da_b3_e_reais(tmp_path):
    regras = carregar_regras(instrumento="win")
    agora = {"t": datetime(2026, 10, 26, 16, 0, tzinfo=SP)}
    enviados = []
    avisos = Avisos("https://exemplo/webhook", pasta=tmp_path / "logs", postar=lambda url, corpo: enviados.append(corpo))
    feed = FeedB3()
    v = Vendedor([SempreCompra()], regras, feed, avisos, pasta=tmp_path, relogio=lambda: agora["t"])

    assert v.passo() == "sem_dados"  # 16h em SP: pregão aberto (em NY seria outro horário)
    agora["t"] = datetime(2026, 10, 26, 17, 10, tzinfo=SP)
    assert v.passo() == "fora_do_horario"  # fechou às 17h, processa só às 17h30
    agora["t"] = datetime(2026, 10, 26, 17, 31, tzinfo=SP)
    assert v.passo() == "processou_fechamento"

    agora["t"] = datetime(2026, 10, 27, 10, 1, tzinfo=SP)
    feed.barra("10:00", 130000, 130020, 129990, 130010)
    assert v.passo() == "operando"
    pos = v.estado.posicoes["sempre_compra"]
    assert pos["entrada"] == 130005  # abertura + 1 tick (5 pontos)

    agora["t"] = datetime(2026, 10, 27, 11, 0, tzinfo=SP)
    feed.barra("10:59", 130050, 130120, 130040, 130110)  # passa do alvo (130100)
    v.passo()
    assert v.estado.posicoes == {}
    # (130095 - 130005) pontos × R$ 0,20 - R$ 1,00 de corretagem
    assert v.estado.realizado_hoje == pytest.approx(90 * 0.20 - 1.0)
    assert (tmp_path / "estado_win.json").exists() and not (tmp_path / "estado.json").exists()
    assert (tmp_path / "logs" / "vendedor_trades_win.jsonl").exists()
    assert any("R$" in c["embeds"][0]["title"] for c in enviados)
