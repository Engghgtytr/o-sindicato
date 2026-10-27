"""Alimentador de dados: baixa, limpa e guarda preços em .parquet.

Fonte grátis: yfinance (não oficial; pode mudar ou limitar a qualquer hora).
Formato padrão de todas as tabelas, com a data como índice:
    abertura, maxima, minima, fechamento, volume
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Callable

import pandas as pd

from .config import RAIZ

PASTA_HISTORICO = RAIZ / "dados" / "historico"
COLUNAS = ["abertura", "maxima", "minima", "fechamento", "volume"]
_NOMES = {"Open": "abertura", "High": "maxima", "Low": "minima", "Close": "fechamento", "Volume": "volume"}


def baixar_yfinance(ticker: str, inicio: str, intervalo: str = "1d") -> pd.DataFrame:
    import yfinance as yf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # o yfinance avisa sobre mudanças do pandas
        return yf.download(ticker, start=inicio, interval=intervalo, progress=False, auto_adjust=False)


def limpar(bruto: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Padroniza as colunas e remove lixo. Devolve a tabela e quantas linhas saíram por quê."""
    df = bruto.copy()
    if isinstance(df.columns, pd.MultiIndex):  # yfinance põe o ticker num segundo nível
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=_NOMES)[COLUNAS]
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:  # tudo em UTC, sem fuso guardado
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    df.index.name = "data"

    removidas = {}
    antes = len(df)
    df = df.dropna(subset=["abertura", "maxima", "minima", "fechamento"])
    removidas["vazias"] = antes - len(df)

    antes = len(df)
    df = df[(df[["abertura", "maxima", "minima", "fechamento"]] > 0).all(axis=1)]
    removidas["zeradas"] = antes - len(df)

    antes = len(df)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    removidas["repetidas"] = antes - len(df)

    # A máxima tem que ser o maior preço do dia e a mínima, o menor.
    antes = len(df)
    ok = (df["maxima"] >= df[["abertura", "fechamento"]].max(axis=1)) & (
        df["minima"] <= df[["abertura", "fechamento"]].min(axis=1)
    )
    df = df[ok]
    removidas["incoerentes"] = antes - len(df)

    df["volume"] = df["volume"].fillna(0).astype("int64")
    return df, removidas


def arquivo_de(ticker: str, intervalo: str = "1d") -> Path:
    nome = ticker.replace("^", "").replace("=", "_").replace("/", "_")
    return PASTA_HISTORICO / f"{nome}_{intervalo}.parquet"


def salvar_historico(
    ticker: str,
    intervalo: str = "1d",
    inicio: str = "2010-01-01",
    baixar: Callable[[str, str, str], pd.DataFrame] = baixar_yfinance,
    pasta: Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Baixa o histórico. Se já existe no disco, baixa só os últimos dias e junta."""
    arquivo = (pasta / arquivo_de(ticker, intervalo).name) if pasta else arquivo_de(ticker, intervalo)
    arquivo.parent.mkdir(parents=True, exist_ok=True)

    antigo = pd.read_parquet(arquivo) if arquivo.exists() else None
    # Volta alguns dias para corrigir o último candle, que pode ter mudado depois do fechamento.
    desde = (antigo.index[-1] - pd.Timedelta(days=5)).strftime("%Y-%m-%d") if antigo is not None else inicio

    novo, removidas = limpar(baixar(ticker, desde, intervalo))
    junto = novo if antigo is None else pd.concat([antigo, novo])
    junto = junto[~junto.index.duplicated(keep="last")].sort_index()
    junto.to_parquet(arquivo)
    return junto, {"arquivo": str(arquivo), "novas_linhas": len(junto) - (0 if antigo is None else len(antigo)), **removidas}


def carregar(ticker: str, intervalo: str = "1d") -> pd.DataFrame:
    arquivo = arquivo_de(ticker, intervalo)
    if not arquivo.exists():
        raise FileNotFoundError(f"Ainda não baixei {ticker}. Rode: python laboratorio.py baixar")
    return pd.read_parquet(arquivo)
