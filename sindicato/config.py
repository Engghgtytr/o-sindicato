"""Lê as regras (regras.json) e os segredos (.env). Segredo nunca fica no código."""
from __future__ import annotations

import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_regras(caminho: Path | None = None, instrumento: str | None = None) -> dict:
    """Regras gerais + as do mercado escolhido ("mnq" = Nasdaq, "win" = mini índice).

    O resultado tem sempre as mesmas chaves (contrato, dados, risco, mercado), então o resto
    do código não precisa saber qual mercado está em uso.
    """
    with open(caminho or RAIZ / "regras.json", encoding="utf-8") as f:
        base = json.load(f)
    if "instrumentos" not in base:  # formato antigo, de um mercado só
        return base
    escolhido = instrumento or base["instrumento_padrao"]
    if escolhido not in base["instrumentos"]:
        raise ValueError(f"Mercado '{escolhido}' não existe. Opções: {', '.join(base['instrumentos'])}")
    inst = base["instrumentos"][escolhido]
    regras = {k: v for k, v in base.items() if k not in ("instrumentos", "instrumento_padrao")}
    regras.update({k: inst[k] for k in ("contrato", "dados", "risco", "mercado") if k in inst})
    regras["imposto"] = inst.get("imposto")
    regras["instrumento"] = {"id": escolhido, "nome": inst["nome"], "simbolo": inst["simbolo"]}
    return regras


def instrumentos_disponiveis(caminho: Path | None = None) -> list[str]:
    with open(caminho or RAIZ / "regras.json", encoding="utf-8") as f:
        return list(json.load(f).get("instrumentos", {}))


def carregar_env(caminho: Path | None = None) -> dict:
    """Lê um .env simples (CHAVE=valor). Variáveis do sistema têm prioridade."""
    valores: dict[str, str] = {}
    arquivo = caminho or RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    for chave in list(valores):
        valores[chave] = os.environ.get(chave, valores[chave])
    return valores
