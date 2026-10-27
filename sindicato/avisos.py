"""Avisos no Discord (por webhook) + registro local de tudo que foi avisado.

- A URL do webhook fica no .env (DISCORD_WEBHOOK_URL), nunca no código.
- Se a internet falhar, a mensagem vai para uma fila e é reenviada no próximo aviso.
- Sem webhook configurado, os avisos ficam só no registro local (e o painel mostra).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import RAIZ

CORES = {"compra": 0x2E9E5B, "venda": 0xD64545, "info": 0x2F6FDE, "alerta": 0x8B0000, "relatorio": 0x2F6FDE}


def _postar_requests(url: str, corpo: dict) -> None:
    import requests

    resposta = requests.post(url, json=corpo, timeout=10)
    resposta.raise_for_status()


class Avisos:
    def __init__(
        self,
        webhook: str | None,
        mencionar: str | None = None,
        pasta: Path = RAIZ / "logs",
        postar: Callable[[str, dict], None] = _postar_requests,
    ):
        self.webhook = webhook or None
        self.mencionar = mencionar
        self.registro = pasta / "avisos.jsonl"
        self.fila = pasta / "fila_discord.jsonl"
        self.postar = postar
        pasta.mkdir(parents=True, exist_ok=True)

    def _corpo(self, tipo: str, titulo: str, campos: dict, urgente: bool) -> dict:
        embed = {
            "title": titulo,
            "color": CORES.get(tipo, CORES["info"]),
            "fields": [{"name": k, "value": str(v), "inline": True} for k, v in campos.items()],
            "footer": {"text": "O Sindicato · simulado, sem ordens reais"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        corpo = {"embeds": [embed]}
        if urgente and self.mencionar:
            corpo["content"] = f"<@{self.mencionar}>"
            corpo["allowed_mentions"] = {"users": [self.mencionar]}
        return corpo

    def _anotar(self, arquivo: Path, dados: dict) -> None:
        with open(arquivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(dados, ensure_ascii=False, default=str) + "\n")

    def _reenviar_fila(self) -> None:
        if not self.fila.exists():
            return
        pendentes = [json.loads(l) for l in self.fila.read_text(encoding="utf-8").splitlines() if l.strip()]
        restantes = []
        for corpo in pendentes:
            try:
                self.postar(self.webhook, corpo)
            except Exception:
                restantes.append(corpo)
        self.fila.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in restantes), encoding="utf-8")

    def enviar(self, tipo: str, titulo: str, campos: dict | None = None, urgente: bool = False) -> str:
        """Devolve 'enviado', 'na_fila' ou 'so_local'."""
        campos = campos or {}
        corpo = self._corpo(tipo, titulo, campos, urgente)
        situacao = "so_local"
        if self.webhook:
            self._reenviar_fila()
            try:
                self.postar(self.webhook, corpo)
                situacao = "enviado"
            except Exception:
                self._anotar(self.fila, corpo)
                situacao = "na_fila"
        self._anotar(
            self.registro,
            {"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tipo": tipo, "titulo": titulo,
             "campos": campos, "urgente": urgente, "situacao": situacao},
        )
        return situacao
