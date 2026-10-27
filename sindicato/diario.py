"""Diário de pesquisa: toda versão testada vira uma linha. Nada se apaga.

O vídeo testou 26 mil variações. Com tantas tentativas, algumas "passam" só por sorte;
o único antídoto é saber quantas tentativas foram feitas. Por isso este arquivo só cresce.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import RAIZ

ARQUIVO = RAIZ / "diario" / "pesquisa.jsonl"


class Diario:
    def __init__(self, arquivo: Path = ARQUIVO):
        self.arquivo = Path(arquivo)

    def ler(self) -> list[dict]:
        if not self.arquivo.exists():
            return []
        with open(self.arquivo, encoding="utf-8") as f:
            return [json.loads(linha) for linha in f if linha.strip()]

    def registrar(self, tipo: str, **dados) -> dict:
        registro = {
            "n": len(self.ler()) + 1,
            "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tipo": tipo,
            **dados,
        }
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        with open(self.arquivo, "a", encoding="utf-8") as f:  # "a" = só acrescenta
            f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
        return registro

    def contar(self, tipo: str) -> int:
        return sum(1 for r in self.ler() if r["tipo"] == tipo)
