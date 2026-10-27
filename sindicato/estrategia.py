"""Estratégias: cada uma é uma classe com a mesma "tomada" para o motor.

Regra de ouro: o sinal do dia i só pode usar dados até o FECHAMENTO do dia i.
O motor executa no dia seguinte. Há um teste automático que corta o futuro e confere
se os sinais passados mudam (se mudarem, a estratégia está "vendo o futuro").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """Average True Range: o tamanho médio do movimento diário, contando os gaps."""
    fech_ant = df["fechamento"].shift(1)
    faixa = pd.concat(
        [df["maxima"] - df["minima"], (df["maxima"] - fech_ant).abs(), (df["minima"] - fech_ant).abs()], axis=1
    ).max(axis=1)
    return faixa.rolling(periodo).mean()


def ifr(fechamento: pd.Series, periodo: int = 2) -> pd.Series:
    """Índice de Força Relativa (RSI), média de Wilder."""
    delta = fechamento.diff()
    alta = delta.clip(lower=0).ewm(alpha=1 / periodo, adjust=False, min_periods=periodo).mean()
    baixa = (-delta.clip(upper=0)).ewm(alpha=1 / periodo, adjust=False, min_periods=periodo).mean()
    rs = alta / baixa.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


@dataclass
class Estrategia:
    """Base. As filhas definem `sinais`. Stop e alvo em múltiplos do ATR do dia do sinal."""

    stop_atr: float = 2.0
    alvo_atr: float = 3.0
    max_dias: int = 20

    nome = "base"

    def sinais(self, df: pd.DataFrame) -> pd.Series:
        """+1 = comprar, -1 = vender, 0 = nada. Calculado no fechamento do dia."""
        raise NotImplementedError

    def saida(self, df: pd.DataFrame) -> pd.Series:
        """True = sair da posição na abertura seguinte. Padrão: nunca (só stop/alvo/tempo)."""
        return pd.Series(False, index=df.index)

    def distancias(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """Distância (em pontos) do stop e do alvo, calculada no dia do sinal."""
        a = atr(df)
        return a * self.stop_atr, a * self.alvo_atr

    def parametros(self) -> dict:
        return {"estrategia": self.nome, **asdict(self)}


@dataclass
class CruzamentoMedias(Estrategia):
    """Compra quando a média curta cruza para cima da longa."""

    rapida: int = 20
    lenta: int = 100
    nome = "cruzamento_medias"

    def sinais(self, df):
        r = df["fechamento"].rolling(self.rapida).mean()
        l = df["fechamento"].rolling(self.lenta).mean()
        cruzou = (r > l) & (r.shift(1) <= l.shift(1))
        return cruzou.astype(int)


@dataclass
class Rompimento(Estrategia):
    """Compra quando fecha acima da máxima dos últimos N dias (canal de Donchian)."""

    dias: int = 20
    nome = "rompimento"

    def sinais(self, df):
        teto = df["maxima"].rolling(self.dias).max().shift(1)  # shift: não conta o próprio dia
        return (df["fechamento"] > teto).astype(int)


@dataclass
class ReversaoIFR(Estrategia):
    """IFR(2) muito baixo numa tendência de alta (acima da média de 200): compra a queda.
    Sai quando fecha acima da média de 5 dias. É uma estratégia publicada e muito conhecida."""

    limite: float = 10.0
    tendencia: int = 200
    stop_atr: float = 3.0
    alvo_atr: float = 6.0
    max_dias: int = 10
    nome = "reversao_ifr2"

    def sinais(self, df):
        f = df["fechamento"]
        return ((ifr(f, 2) < self.limite) & (f > f.rolling(self.tendencia).mean())).astype(int)

    def saida(self, df):
        f = df["fechamento"]
        return f > f.rolling(5).mean()


@dataclass
class Tendencia200(Estrategia):
    """Compra quando fecha acima da média de 200 dias; sai quando fecha abaixo.
    Regra de "seguir a tendência" muito usada por gestores. Stop largo, sem alvo (deixa correr)."""

    media: int = 200
    stop_atr: float = 6.0
    alvo_atr: float = 1000.0
    max_dias: int = 2000
    nome = "tendencia_200"

    def sinais(self, df):
        f, m = df["fechamento"], df["fechamento"].rolling(self.media).mean()
        return ((f > m) & (f.shift(1) <= m.shift(1))).astype(int)

    def saida(self, df):
        return df["fechamento"] < df["fechamento"].rolling(self.media).mean()


@dataclass
class Tartaruga(Estrategia):
    """Sistema 2 das Tartarugas (anos 80): entra no rompimento da máxima de 55 dias,
    sai quando perde a mínima de 20 dias."""

    entrada: int = 55
    saida_dias: int = 20
    stop_atr: float = 2.0
    alvo_atr: float = 1000.0
    max_dias: int = 2000
    nome = "tartaruga_55"

    def sinais(self, df):
        teto = df["maxima"].rolling(self.entrada).max().shift(1)
        return (df["fechamento"] > teto).astype(int)

    def saida(self, df):
        piso = df["minima"].rolling(self.saida_dias).min().shift(1)
        return df["fechamento"] < piso


@dataclass
class BollingerReversao(Estrategia):
    """Fecha abaixo da banda inferior de Bollinger (20 dias, 2 desvios) numa alta de longo prazo:
    compra a queda; sai quando volta para a média de 20."""

    periodo: int = 20
    desvios: float = 2.0
    stop_atr: float = 3.0
    alvo_atr: float = 6.0
    max_dias: int = 15
    nome = "bollinger_reversao"

    def sinais(self, df):
        f = df["fechamento"]
        media, desvio = f.rolling(self.periodo).mean(), f.rolling(self.periodo).std()
        return ((f < media - self.desvios * desvio) & (f > f.rolling(200).mean())).astype(int)

    def saida(self, df):
        f = df["fechamento"]
        return f > f.rolling(self.periodo).mean()


@dataclass
class TresQuedas(Estrategia):
    """Larry Connors: 3 fechamentos seguidos em queda, acima da média de 200 dias. Sai acima da média de 5."""

    stop_atr: float = 3.0
    alvo_atr: float = 6.0
    max_dias: int = 10
    nome = "tres_quedas"

    def sinais(self, df):
        f = df["fechamento"]
        caiu = f < f.shift(1)
        return (caiu & caiu.shift(1, fill_value=False) & caiu.shift(2, fill_value=False) & (f > f.rolling(200).mean())).astype(int)

    def saida(self, df):
        f = df["fechamento"]
        return f > f.rolling(5).mean()


@dataclass
class MACD(Estrategia):
    """MACD (12, 26, 9) de Gerald Appel: compra quando a linha cruza para cima da sinal; sai no cruzamento contrário."""

    rapida: int = 12
    lenta: int = 26
    sinal: int = 9
    stop_atr: float = 3.0
    alvo_atr: float = 1000.0
    max_dias: int = 200
    nome = "macd"

    def _linhas(self, df):
        f = df["fechamento"]
        macd = f.ewm(span=self.rapida, adjust=False).mean() - f.ewm(span=self.lenta, adjust=False).mean()
        return macd, macd.ewm(span=self.sinal, adjust=False).mean()

    def sinais(self, df):
        macd, sinal = self._linhas(df)
        return ((macd > sinal) & (macd.shift(1) <= sinal.shift(1))).astype(int)

    def saida(self, df):
        macd, sinal = self._linhas(df)
        return macd < sinal


@dataclass
class ViradaDoMes(Estrategia):
    """Efeito da virada do mês: compra no fechamento do penúltimo dia útil do mês e fica ~4 dias.
    Usa só o calendário (que se conhece de antemão), não os preços de amanhã."""

    dias: int = 4
    stop_atr: float = 3.0
    alvo_atr: float = 1000.0
    nome = "virada_do_mes"

    def __post_init__(self):
        self.max_dias = self.dias

    def sinais(self, df):
        datas = pd.Series(df.index, index=df.index)
        # Penúltimo dia útil do calendário: daqui a 2 dias úteis já é outro mês, mas daqui a 1 não.
        dois = (datas + pd.offsets.BDay(2)).dt.month != datas.dt.month
        um = (datas + pd.offsets.BDay(1)).dt.month != datas.dt.month
        return (dois & ~um).astype(int)


@dataclass
class VendaAbaixo200(Estrategia):
    """O espelho da tendência de 200 dias: VENDE quando fecha abaixo da média; sai quando volta acima."""

    media: int = 200
    stop_atr: float = 6.0
    alvo_atr: float = 1000.0
    max_dias: int = 2000
    nome = "venda_abaixo_200"

    def sinais(self, df):
        f, m = df["fechamento"], df["fechamento"].rolling(self.media).mean()
        return -((f < m) & (f.shift(1) >= m.shift(1))).astype(int)

    def saida(self, df):
        return df["fechamento"] > df["fechamento"].rolling(self.media).mean()


ESTRATEGIAS = {
    c.nome: c
    for c in (
        CruzamentoMedias, Rompimento, ReversaoIFR, Tendencia200, Tartaruga, BollingerReversao,
        TresQuedas, MACD, ViradaDoMes, VendaAbaixo200,
    )
}


def _registrar_previsor():
    # Importado aqui para evitar import circular (previsao.py usa Estrategia).
    from .previsao import Previsor

    ESTRATEGIAS[Previsor.nome] = Previsor


_registrar_previsor()
