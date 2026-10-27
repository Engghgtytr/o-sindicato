"""Gera os dados do app (painel/dados.js) a partir de tudo que o robô fez.

O app é um HTML local que abre com dois cliques, sem servidor e sem internet:
os dados entram como um arquivo .js (window.PAINEL = {...}).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import RAIZ, carregar_env, carregar_regras, instrumentos_disponiveis
from .diario import Diario
from .relatorio import PASTA, ler_todos, versoes_testadas
from .vendedor import Estado

PASTA_APP = RAIZ / "painel"


def _jsonl(arquivo: Path, ultimos: int | None = None) -> list[dict]:
    if not arquivo.exists():
        return []
    linhas = [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]
    return linhas[-ultimos:] if ultimos else linhas


def _dias_uteis(de: str, ate: str) -> int:
    return len(pd.bdate_range(de, ate))


def _descricao(regras: dict) -> str:
    c, i = regras["contrato"], regras["instrumento"]
    valor = c.get("valor_por_ponto", c.get("dolares_por_ponto"))
    return f"{i['nome']}, 1 contrato ({i['simbolo']} {valor:g} por ponto)"


def montar_dados(raiz: Path = RAIZ) -> dict:
    arquivo_regras = raiz / "regras.json"
    ids = instrumentos_disponiveis(arquivo_regras) or ["mnq"]
    diario = Diario(raiz / "diario" / "pesquisa.jsonl")
    estrategias = ler_todos()  # todas as versões (o painel mostra cada uma)
    ultimas = ler_todos(so_ultima=True)  # o placar conta a versão mais nova de cada estratégia

    for r in estrategias:
        # Cada rodada sorteia, todo dia, se entra ou não: é uma "moeda" por dia por rodada.
        r["coin_flip"]["moedas_jogadas"] = r["coin_flip"]["rodadas"] * _dias_uteis(r["de"], r["ate"])

    sindicatos = {i: {} for i in ids}
    for arquivo in sorted(PASTA.glob("sindicato__*.json")):
        s = json.loads(arquivo.read_text(encoding="utf-8"))
        s.setdefault("simbolo", "US$")
        sindicatos.setdefault(s.get("instrumento_id", "mnq"), {})[s["periodo"]] = s

    previsoes = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted((raiz / "relatorios" / "previsoes").glob("*.json"))
    ] if (raiz / "relatorios" / "previsoes").exists() else []

    # Cada mercado tem o seu Vendedor: estado.json / estado_win.json, e os trades de cada um.
    mercados, vendedores = {}, {}
    for i in ids:
        regras = carregar_regras(arquivo_regras, instrumento=i)
        sufixo = "" if i == "mnq" else f"_{i}"
        estado_arquivo = raiz / f"estado{sufixo}.json"
        vendedores[i] = {
            "estado": Estado.carregar(estado_arquivo).__dict__ if estado_arquivo.exists() else None,
            "trades": _jsonl(raiz / "logs" / f"vendedor_trades{sufixo}.jsonl"),
        }
        mercados[i] = {
            "nome": regras["instrumento"]["nome"],
            "simbolo": regras["instrumento"]["simbolo"],
            "descricao": _descricao(regras),
            "serie_backtest": regras["dados"]["serie_backtest"],
            "serie_ao_vivo": regras["dados"]["serie_ao_vivo"],
            "custos": {k: v for k, v in regras["contrato"].items() if not k.startswith("_")},
            "risco": {k: v for k, v in regras["risco"].items() if not k.startswith("_")},
            "mercado": regras.get("mercado"),
            "imposto": {k: v for k, v in (regras.get("imposto") or {}).items() if not k.startswith("_")} or None,
        }
    avisos = _jsonl(raiz / "logs" / "avisos.jsonl", ultimos=300)

    por_mercado = {}
    for i in ids:
        todas = [r for r in estrategias if r["instrumento_id"] == i]
        novas = [r for r in ultimas if r["instrumento_id"] == i]
        por_mercado[i] = {
            "estrategias_avaliadas": len(novas),
            "avaliacoes": len(todas),
            "aprovadas": sum(1 for r in novas if r["veredito"]["aprovada"]),
            "rodadas_coin_flip": sum(r["coin_flip"]["rodadas"] for r in todas),
            "moedas_jogadas": sum(r["coin_flip"]["moedas_jogadas"] for r in todas),
            "trades_backtest": sum(r["metricas"]["trades"] for r in todas),
            "trades_vendedor": len(vendedores[i]["trades"]),
        }

    diario_resumido = []
    for e in diario.ler():
        m = e.get("metricas") or {}
        diario_resumido.append(
            {
                "n": e["n"], "quando": e["quando"], "tipo": e["tipo"],
                "estrategia": (e.get("parametros") or {}).get("estrategia"),
                "periodo": e.get("periodo"), "motivo": e.get("motivo"),
                "trades": m.get("trades"), "lucro": m.get("lucro_liquido"),
                "aprovada": (e.get("veredito") or {}).get("aprovada"),
                "instrumento": e.get("instrumento", "mnq") if e["tipo"] in ("teste", "avaliacao") else None,
            }
        )

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resumo": {
            "versoes_testadas": versoes_testadas(diario),
            "aberturas_cego": diario.contar("abriu_cego"),
            "estrategias_avaliadas": len(ultimas),
            "avaliacoes": len(estrategias),
            "aprovadas": sum(1 for r in ultimas if r["veredito"]["aprovada"]),
            "rodadas_coin_flip": sum(r["coin_flip"]["rodadas"] for r in estrategias),
            "moedas_jogadas": sum(r["coin_flip"]["moedas_jogadas"] for r in estrategias),
            "trades_backtest": sum(r["metricas"]["trades"] for r in estrategias),
            "trades_vendedor": sum(len(v["trades"]) for v in vendedores.values()),
            "avisos": len(_jsonl(raiz / "logs" / "avisos.jsonl")),
            "discord_configurado": bool(carregar_env(raiz / ".env").get("DISCORD_WEBHOOK_URL")),
        },
        "por_mercado": por_mercado,
        "mercados": mercados,
        "periodos": regras["periodos"],
        "estrategias": estrategias,
        "sindicatos": sindicatos,
        "previsoes": previsoes,
        "vendedores": vendedores,
        "avisos": avisos,
        "diario": diario_resumido,
    }


def gerar(raiz: Path = RAIZ, pasta_app: Path = PASTA_APP) -> Path:
    dados = montar_dados(raiz)
    texto = json.dumps(dados, ensure_ascii=True, separators=(",", ":"))
    (pasta_app / "dados.js").write_text(f"window.PAINEL = {texto};\n", encoding="utf-8")
    return pasta_app / "index.html"
