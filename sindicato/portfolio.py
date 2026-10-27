"""O Sindicato: várias estratégias operando juntas, 1 contrato cada.

A ideia do vídeo: estratégias diferentes perdem em dias diferentes, então juntas o pior
momento (drawdown) tende a ser menor que o de cada uma sozinha.

Correlação: mostrada só como informação. Correlação NEGATIVA entre estratégias lucrativas
é boa (uma ganha quando a outra perde); o problema é correlação muito ALTA, que só duplica
o risco.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from .estrategia import Estrategia
from .metricas import calcular
from .motor import Custos, rodar
from .relatorio import PASTA, _curva_semanal, _limpo, info_instrumento


def montar(dados: pd.DataFrame, inicio: pd.Timestamp, periodo: str, membros: list[Estrategia], aprovadas: set[str], regras: dict) -> dict:
    custos = Custos.das_regras(regras)
    contratos = regras["risco"]["contratos"]
    curvas, trades, individuais = {}, [], {}
    for est in membros:
        r = rodar(dados, est, custos, contratos, inicio)
        curvas[est.nome] = r.patrimonio
        trades.append(r.trades.assign(estrategia=est.nome))
        individuais[est.nome] = calcular(r.trades, r.patrimonio)

    tabela = pd.DataFrame(curvas).ffill().fillna(0)
    total = tabela.sum(axis=1)
    todos = pd.concat(trades, ignore_index=True).sort_values("saida")
    combinado = calcular(todos, total)

    variacao_diaria = tabela.diff().fillna(0)
    correlacao = variacao_diaria.corr().round(2)
    pares_altos = [
        f"{a} × {b}: {correlacao.loc[a, b]}"
        for i, a in enumerate(correlacao.index)
        for b in correlacao.columns[i + 1 :]
        if correlacao.loc[a, b] >= 0.85
    ]

    inst = info_instrumento(regras)
    relatorio = _limpo(
        {
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "periodo": periodo,
            "instrumento": inst["nome"],
            "instrumento_id": inst["id"],
            "simbolo": inst["simbolo"],
            "membros": [{"nome": e.nome, "aprovada": e.nome in aprovadas, "metricas": individuais[e.nome]} for e in membros],
            "combinado": combinado,
            "pior_drawdown_sozinha": max((m.get("drawdown_max_usd", 0) for m in individuais.values()), default=0),
            "correlacao": {"nomes": list(correlacao.index), "valores": correlacao.values.tolist()},
            "pares_muito_parecidos": pares_altos,
            "curva": _curva_semanal(total),
            "curvas_membros": {nome: _curva_semanal(s) for nome, s in curvas.items()},
        }
    )
    meio = "" if inst["id"] == "mnq" else f"{inst['id']}__"
    arquivo = PASTA / f"sindicato__{meio}{periodo}.json"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(relatorio, ensure_ascii=False), encoding="utf-8")
    return relatorio
