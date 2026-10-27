"""O Vendedor (simulado ao vivo) com relógio e preços de mentira."""
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import pytest

from sindicato.avisos import Avisos
from sindicato.estrategia import Estrategia
from sindicato.vendedor import NY, Vendedor

REGRAS = {
    "contrato": {"dolares_por_ponto": 2.0, "tick": 0.25, "comissao_por_lado": 0.62, "slippage_ticks_por_lado": 1},
    "risco": {"contratos": 1, "perda_maxima_diaria": 300.0},
}


@dataclass
class SempreCompra(Estrategia):
    stop_atr: float = 1.0
    alvo_atr: float = 1.0
    max_dias: int = 5
    nome = "sempre_compra"

    def sinais(self, df):
        return pd.Series(1, index=df.index)

    def distancias(self, df):
        return pd.Series(50.0, index=df.index), pd.Series(100.0, index=df.index)


class FeedFalso:
    def __init__(self):
        self.barras = pd.DataFrame(columns=["abertura", "maxima", "minima", "fechamento", "volume"])

    def diario(self):
        datas = pd.bdate_range("2026-10-01", "2026-10-26")
        return pd.DataFrame({"abertura": 20000.0, "maxima": 20100.0, "minima": 19900.0, "fechamento": 20000.0, "volume": 1}, index=datas)

    def minutos(self):
        return self.barras

    def barra(self, hora, a, h, l, c, dia="2026-10-27"):
        quando = pd.Timestamp(f"{dia} {hora}", tz=NY).tz_convert("UTC")
        self.barras.loc[quando] = [a, h, l, c, 1]
        self.barras = self.barras.sort_index()


class Relogio:
    def __init__(self, texto):
        self.agora = datetime.fromisoformat(texto).replace(tzinfo=NY)

    def __call__(self):
        return self.agora

    def ir(self, texto):
        self.agora = datetime.fromisoformat(texto).replace(tzinfo=NY)


def montar(tmp_path, relogio, feed=None, postar=None):
    enviados = []
    avisos = Avisos("https://exemplo/webhook", pasta=tmp_path / "logs", postar=postar or (lambda url, corpo: enviados.append(corpo)))
    feed = feed or FeedFalso()
    v = Vendedor([SempreCompra()], REGRAS, feed, avisos, pasta=tmp_path, relogio=relogio)
    return v, feed, enviados


def titulos(enviados):
    return [c["embeds"][0]["title"] for c in enviados]


def test_dia_completo_sinal_entrada_e_alvo(tmp_path):
    relogio = Relogio("2026-10-26T16:20")  # segunda, depois do fechamento
    v, feed, enviados = montar(tmp_path, relogio)
    assert v.passo() == "processou_fechamento"
    assert "sempre_compra" in v.estado.pendentes_entrada

    relogio.ir("2026-10-27T09:31")  # terça, abriu
    feed.barra("09:30", 20000, 20010, 19990, 20005)
    assert v.passo() == "operando"
    pos = v.estado.posicoes["sempre_compra"]
    assert pos["entrada"] == 20000.25 and pos["stop"] == 19950 and pos["alvo"] == 20100

    relogio.ir("2026-10-27T10:05")
    feed.barra("10:04", 20050, 20120, 20040, 20110)  # passa do alvo
    v.passo()
    assert v.estado.posicoes == {}
    trade = [l for l in (tmp_path / "logs" / "vendedor_trades.jsonl").read_text(encoding="utf-8").splitlines()][0]
    assert '"motivo": "alvo"' in trade
    assert v.estado.realizado_hoje == pytest.approx((20099.75 - 20000.25) * 2 - 1.24)
    assert any("Entrada sempre_compra" in t for t in titulos(enviados))


def test_trava_diaria_fecha_tudo_e_para_ate_amanha(tmp_path):
    relogio = Relogio("2026-10-26T16:20")
    v, feed, enviados = montar(tmp_path, relogio)
    v.passo()
    v.estrategias["sempre_compra"].stop_atr = 999  # stop longe: só a trava protege
    v.estado.pendentes_entrada["sempre_compra"]["dist_stop"] = 5000.0
    relogio.ir("2026-10-27T09:31")
    feed.barra("09:30", 20000, 20000, 19990, 20000)
    v.passo()
    relogio.ir("2026-10-27T11:00")
    feed.barra("10:59", 19900, 19900, 19800, 19820)  # -180 pontos = -US$ 360
    assert v.passo() == "travou"
    assert v.estado.posicoes == {}
    assert v.estado.bloqueado_ate == "2026-10-27"
    relogio.ir("2026-10-27T11:30")
    assert v.passo() == "travado_hoje"
    assert any("TRAVA ATIVADA" in t for t in titulos(enviados))


def test_botao_de_parar(tmp_path):
    relogio = Relogio("2026-10-26T16:20")
    v, feed, enviados = montar(tmp_path, relogio)
    v.passo()
    relogio.ir("2026-10-27T09:31")
    feed.barra("09:30", 20000, 20005, 19995, 20002)
    v.passo()
    (tmp_path / "PARAR").write_text("")
    assert v.passo() == "parado_pelo_botao"
    assert v.estado.posicoes == {} and v.estado.desligado
    assert not (tmp_path / "PARAR").exists()
    assert v.passo() == "desligado"


def test_volta_de_onde_parou_depois_de_reiniciar(tmp_path):
    relogio = Relogio("2026-10-26T16:20")
    v, feed, _ = montar(tmp_path, relogio)
    v.passo()
    relogio.ir("2026-10-27T09:31")
    feed.barra("09:30", 20000, 20005, 19995, 20002)
    v.passo()
    assert "sempre_compra" in v.estado.posicoes

    # "PC reiniciou": um Vendedor novo lendo o mesmo estado.json
    v2, _, _ = montar(tmp_path, relogio, feed=feed)
    assert v2.estado.posicoes["sempre_compra"]["entrada"] == 20000.25
    relogio.ir("2026-10-27T09:40")
    feed.barra("09:39", 19960, 19962, 19940, 19945)  # bate o stop
    v2.passo()
    assert v2.estado.posicoes == {}


def test_dado_velho_nao_opera(tmp_path):
    relogio = Relogio("2026-10-26T16:20")
    v, feed, enviados = montar(tmp_path, relogio)
    v.passo()
    relogio.ir("2026-10-27T11:00")
    feed.barra("09:30", 20000, 20005, 19995, 20002)  # última barra 1h30 atrás
    assert v.passo() == "dado_velho"
    assert v.estado.posicoes == {}
    assert any("Dado velho" in t for t in titulos(enviados))


def test_fim_de_semana_nao_faz_nada(tmp_path):
    v, _, _ = montar(tmp_path, Relogio("2026-10-31T11:00"))  # sábado
    assert v.passo() == "fora_do_horario"


def test_discord_fora_do_ar_guarda_na_fila_e_reenvia(tmp_path):
    caido = {"sim": True}
    recebidos = []

    def postar(url, corpo):
        if caido["sim"]:
            raise ConnectionError("sem internet")
        recebidos.append(corpo)

    avisos = Avisos("https://exemplo/webhook", pasta=tmp_path, postar=postar)
    assert avisos.enviar("info", "primeiro") == "na_fila"
    caido["sim"] = False
    assert avisos.enviar("info", "segundo") == "enviado"
    assert [c["embeds"][0]["title"] for c in recebidos] == ["primeiro", "segundo"]


def test_sem_webhook_so_registra_local(tmp_path):
    avisos = Avisos(None, pasta=tmp_path)
    assert avisos.enviar("info", "oi") == "so_local"
    assert "oi" in (tmp_path / "avisos.jsonl").read_text(encoding="utf-8")
