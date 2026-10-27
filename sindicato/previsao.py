"""Previsor: estima a CHANCE de o próximo fechamento ser maior que o de hoje.

Honestidade antes de tudo:
- Ninguém prevê de forma confiável a direção do dia seguinte. Bons modelos ficam perto
  de 50–55% de acerto. Por isso o previsor sempre mostra quanto acertou de verdade e
  compara com "chutar que sempre sobe" (num mercado que sobe, isso já acerta ~55%).
- Treino "andando para a frente" (walk-forward): para prever o ano Y, o modelo só
  aprende com dados de antes de Y. Ele nunca vê o ano que está prevendo.

Modelo: regressão logística simples (feita com numpy), com indicadores comuns:
retornos recentes, distância das médias, IFR, volatilidade e virada do mês.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .estrategia import Estrategia, ifr

NOMES_INDICADORES = [
    "retorno_1d", "retorno_5d", "retorno_20d", "dist_media_20", "dist_media_50", "dist_media_200",
    "ifr_14", "volatilidade_20", "faixa_do_dia", "virada_do_mes",
]


def indicadores(df: pd.DataFrame) -> pd.DataFrame:
    """Tudo calculado com dados até o fechamento do próprio dia."""
    f = df["fechamento"]
    r = f.pct_change()
    datas = pd.Series(df.index, index=df.index)
    virada = ((datas + pd.offsets.BDay(3)).dt.month != datas.dt.month).astype(float)
    x = pd.DataFrame(
        {
            "retorno_1d": r,
            "retorno_5d": f.pct_change(5),
            "retorno_20d": f.pct_change(20),
            "dist_media_20": f / f.rolling(20).mean() - 1,
            "dist_media_50": f / f.rolling(50).mean() - 1,
            "dist_media_200": f / f.rolling(200).mean() - 1,
            "ifr_14": ifr(f, 14) / 100,
            "volatilidade_20": r.rolling(20).std(),
            "faixa_do_dia": (df["maxima"] - df["minima"]) / f,
            "virada_do_mes": virada,
        },
        index=df.index,
    )
    return x[NOMES_INDICADORES]


def alvo(df: pd.DataFrame) -> pd.Series:
    """1 se o próximo fechamento for maior que o de hoje. Último dia: desconhecido (NaN)."""
    f = df["fechamento"]
    amanha = f.shift(-1)
    return (amanha > f).astype(float).where(amanha.notna())


class Logistica:
    """Regressão logística com regularização L2, treinada por gradiente."""

    def __init__(self, l2: float = 1.0, passos: int = 400, taxa: float = 0.5):
        self.l2, self.passos, self.taxa = l2, passos, taxa

    def treinar(self, x: np.ndarray, y: np.ndarray) -> "Logistica":
        self.media = x.mean(axis=0)
        self.desvio = x.std(axis=0) + 1e-12
        z = (x - self.media) / self.desvio
        n, k = z.shape
        self.w, self.b = np.zeros(k), 0.0
        for _ in range(self.passos):
            p = 1 / (1 + np.exp(-(z @ self.w + self.b)))
            erro = p - y
            self.w -= self.taxa * (z.T @ erro / n + self.l2 * self.w / n)
            self.b -= self.taxa * erro.mean()
        return self

    def prob(self, x: np.ndarray) -> np.ndarray:
        z = (x - self.media) / self.desvio
        return 1 / (1 + np.exp(-(z @ self.w + self.b)))


def walk_forward(df: pd.DataFrame, minimo_linhas: int = 500) -> pd.Series:
    """Chance de subir para cada dia, prevista por um modelo treinado só com anos anteriores."""
    x, y = indicadores(df), alvo(df)
    prob = pd.Series(np.nan, index=df.index)
    proximo_dia = pd.Series(df.index, index=df.index).shift(-1)
    for ano in sorted(set(df.index.year)):
        inicio = pd.Timestamp(f"{ano}-01-01")
        # Só linhas cujo "amanhã" também é antes do ano previsto (senão o rótulo vaza o futuro).
        treino = (df.index < inicio) & (proximo_dia < inicio) & x.notna().all(axis=1) & y.notna()
        if treino.sum() < minimo_linhas:
            continue
        modelo = Logistica().treinar(x[treino].to_numpy(), y[treino].to_numpy())
        alvo_ano = (df.index.year == ano) & x.notna().all(axis=1)
        if alvo_ano.any():
            prob[alvo_ano] = modelo.prob(x[alvo_ano].to_numpy())
    return prob


def avaliar_acerto(df: pd.DataFrame, prob: pd.Series) -> dict:
    """Quanto o previsor acertou, comparado com chutes simples."""
    y = alvo(df)
    ok = prob.notna() & y.notna()
    p, real = prob[ok], y[ok]
    n = int(ok.sum())
    if n == 0:
        return {"dias": 0}
    acerto = float(((p > 0.5) == (real == 1)).mean())
    sempre_sobe = float(real.mean())
    repete_ontem = float((df["fechamento"].pct_change()[ok] > 0).astype(float).eq(real).mean())
    margem = 1.96 * np.sqrt(acerto * (1 - acerto) / n)
    confiante = p[(p > 0.55) | (p < 0.45)]
    acerto_confiante = float(((confiante > 0.5) == (real[confiante.index] == 1)).mean()) if len(confiante) else None
    return {
        "dias": n,
        "acerto_pct": round(100 * acerto, 1),
        "margem_pct": round(100 * margem, 1),
        "chute_sempre_sobe_pct": round(100 * sempre_sobe, 1),
        "chute_repete_ontem_pct": round(100 * repete_ontem, 1),
        # bool() do Python: o do numpy viraria o texto "False" no JSON, que o JavaScript lê como verdadeiro.
        "ganhou_do_sempre_sobe": bool(acerto - margem > sempre_sobe),
        "dias_confiante": int(len(confiante)),
        "acerto_quando_confiante_pct": None if acerto_confiante is None else round(100 * acerto_confiante, 1),
    }


def prever_amanha(df: pd.DataFrame) -> dict:
    """Treina com TODO o histórico disponível e dá a chance para o próximo pregão."""
    x, y = indicadores(df), alvo(df)
    treino = x.notna().all(axis=1) & y.notna()
    modelo = Logistica().treinar(x[treino].to_numpy(), y[treino].to_numpy())
    ultimo = x.iloc[[-1]]
    chance = float(modelo.prob(ultimo.to_numpy())[0])
    pesos = sorted(zip(NOMES_INDICADORES, modelo.w), key=lambda t: -abs(t[1]))
    return {
        "base": df.index[-1].strftime("%Y-%m-%d"),
        "fechamento": round(float(df["fechamento"].iloc[-1]), 2),
        "chance_subir_pct": round(100 * chance, 1),
        "leitura": "sobe" if chance > 0.55 else "cai" if chance < 0.45 else "incerto (perto de 50%)",
        "indicadores_que_mais_pesam": [{"nome": n, "peso": round(float(w), 3)} for n, w in pesos[:4]],
    }


@dataclass
class Previsor(Estrategia):
    """Estratégia: compra quando a chance prevista de subir passa do limite; segura 1 dia.
    Assim o previsor passa pelo mesmo teste da honestidade (coin flip) que as outras."""

    limite: float = 0.55
    vende_abaixo: bool = False
    stop_atr: float = 2.0
    alvo_atr: float = 1000.0
    max_dias: int = 1
    aquecimento: int = 3000  # no teste cego, treina com os anos de antes de 2021
    nome = "previsor"

    def sinais(self, df):
        p = walk_forward(df)
        compra = (p > self.limite).astype(int)
        if self.vende_abaixo:
            compra = compra - (p < 1 - self.limite).astype(int)
        return compra.fillna(0).astype(int)
