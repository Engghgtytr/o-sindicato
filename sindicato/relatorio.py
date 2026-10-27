"""Monta e salva os relatórios que o app (painel) mostra."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .avaliacao import coin_flip, comprar_e_segurar, monte_carlo, p_valor, veredito
from .config import RAIZ
from .diario import Diario
from .estrategia import Estrategia
from .metricas import calcular, imposto_estimado
from .motor import Custos, rodar

PASTA = RAIZ / "relatorios"


def info_instrumento(regras: dict) -> dict:
    return regras.get("instrumento") or {"id": "mnq", "nome": "Nasdaq-100 (contrato micro MNQ)", "simbolo": "US$"}


def _limpo(valor):
    """Converte para algo que o JSON aceita (sem NaN nem infinito)."""
    if isinstance(valor, dict):
        return {k: _limpo(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpo(v) for v in valor]
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return None if not math.isfinite(valor) else round(float(valor), 4)
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.strftime("%Y-%m-%d")
    return valor


def _curva_semanal(serie: pd.Series) -> list:
    """Uma amostra por semana basta para o gráfico (e deixa o arquivo leve)."""
    s = serie.resample("W").last().dropna()
    return [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in s.items()]


def versoes_testadas(diario: Diario) -> int:
    return diario.contar("teste") + diario.contar("avaliacao")


def avaliar(
    dados: pd.DataFrame,
    inicio: pd.Timestamp,
    periodo: str,
    estrategia: Estrategia,
    regras: dict,
    diario: Diario,
) -> dict:
    custos = Custos.das_regras(regras)
    contratos = regras["risco"]["contratos"]
    cfg = regras["avaliacao"]

    r = rodar(dados, estrategia, custos, contratos, inicio)
    m = calcular(r.trades, r.patrimonio)
    bh = comprar_e_segurar(dados, custos, contratos, inicio)

    if m["trades"] == 0:
        cf = {"rodadas": 0, "lucros": np.array([]), "trades": np.array([0]), "drawdowns": np.array([])}
        p = 1.0
    else:
        cf = coin_flip(dados, estrategia, custos, contratos, inicio, m["trades"], cfg["rodadas_coin_flip"])
        p = p_valor(m["lucro_liquido"], cf["lucros"])
    mc = monte_carlo(r.trades["resultado_usd"].to_numpy(), regras["risco"]["limite_drawdown_conta"], cfg["rodadas_monte_carlo"])

    # Treino: a melhor de muitas tentativas pode ser sorte, então conta TODAS as versões.
    # Teste cego: a estratégia foi escolhida antes e testada nos anos nunca vistos; o que
    # conta é quantas vezes o cofre foi aberto (abrir várias vezes também vira "tentativa").
    versoes = diario.contar("abriu_cego") if periodo == "cego" else versoes_testadas(diario) + 1
    v = veredito(m.get("lucro_liquido", 0.0), p, versoes, bh["lucro_liquido"], mc, cfg["alfa"])

    melhores = int(np.sum(cf["lucros"] >= m.get("lucro_liquido", 0.0))) if len(cf["lucros"]) else 0
    inst = info_instrumento(regras)
    ir = imposto_estimado(r.trades, regras["imposto"]) if regras.get("imposto") else None
    relatorio = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "estrategia": estrategia.nome,
        "parametros": estrategia.parametros(),
        "periodo": periodo,
        "de": inicio,
        "ate": dados.index[-1],
        "instrumento": inst["nome"],
        "instrumento_id": inst["id"],
        "simbolo": inst["simbolo"],
        "imposto": ir,
        "metricas": m,
        "comprar_e_segurar": {"lucro_liquido": bh["lucro_liquido"], "drawdown_max_usd": bh["drawdown_max_usd"]},
        "coin_flip": {
            "rodadas": cf["rodadas"],
            "sorteios_que_fizeram_melhor": melhores,
            "media_lucro": float(np.mean(cf["lucros"])) if len(cf["lucros"]) else 0.0,
            "media_trades": float(np.mean(cf["trades"])),
            "lucros": [round(float(x), 2) for x in cf["lucros"]],
        },
        "monte_carlo": mc,
        "veredito": v,
        "curva": _curva_semanal(r.patrimonio),
        "curva_comprar_e_segurar": _curva_semanal(bh["curva"]),
        "trades": r.trades.assign(instrumento=inst["nome"]).to_dict("records"),
    }
    relatorio = _limpo(relatorio)

    registro = diario.registrar(
        "avaliacao",
        instrumento=inst["id"],
        periodo=periodo,
        parametros=estrategia.parametros(),
        metricas=relatorio["metricas"],
        coin_flip={"rodadas": cf["rodadas"], "fizeram_melhor": melhores},
        veredito=relatorio["veredito"],
    )
    relatorio["versao"] = registro["n"]
    salvar(relatorio)
    return relatorio


def nome_arquivo(estrategia: str, periodo: str, versao: int, instrumento: str = "mnq") -> Path:
    # Um arquivo por versão: testar outra duração não apaga o relatório anterior.
    meio = "" if instrumento == "mnq" else f"{instrumento}__"
    return PASTA / "estrategias" / f"{estrategia}__{meio}{periodo}__v{versao:05d}.json"


def salvar(relatorio: dict) -> Path:
    arquivo = nome_arquivo(relatorio["estrategia"], relatorio["periodo"], relatorio["versao"], relatorio.get("instrumento_id", "mnq"))
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(relatorio, ensure_ascii=False), encoding="utf-8")
    return arquivo


def ler_todos(so_ultima: bool = False, instrumento: str | None = None) -> list[dict]:
    """Todas as versões avaliadas, da mais antiga para a mais nova.
    so_ultima=True: só a versão mais recente de cada estratégia/mercado/período."""
    pasta = PASTA / "estrategias"
    if not pasta.exists():
        return []
    todos = []
    for f in pasta.glob("*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        r.setdefault("instrumento_id", "mnq")  # relatórios de antes de existir o mini índice
        r.setdefault("simbolo", "US$")
        if instrumento is None or r["instrumento_id"] == instrumento:
            todos.append(r)
    todos.sort(key=lambda r: r["versao"])
    if not so_ultima:
        return todos
    ultimas = {}
    for r in todos:
        ultimas[(r["estrategia"], r["instrumento_id"], r["periodo"])] = r
    return list(ultimas.values())
