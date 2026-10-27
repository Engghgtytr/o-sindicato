"""Bot do Discord: textos dos comandos, botão de parar e montagem dos comandos (sem internet)."""
import json

import pytest

from sindicato import bot_discord, relatorio
from sindicato.config import RAIZ
from sindicato.vendedor import Estado, apertar_parar, religar


def _relatorio(pasta, estrategia, lucro, melhores, aprovada, versao, instrumento="win"):
    r = {
        "estrategia": estrategia, "periodo": "treino", "versao": versao, "instrumento_id": instrumento,
        "metricas": {"lucro_liquido": lucro}, "veredito": {"aprovada": aprovada},
        "coin_flip": {"rodadas": 500, "sorteios_que_fizeram_melhor": melhores},
        "comprar_e_segurar": {"lucro_liquido": 10141.0},
    }
    (pasta / f"{estrategia}__{instrumento}__treino__v{versao:05d}.json").write_text(json.dumps(r), encoding="utf-8")


def test_dinheiro_em_reais_e_negativo():
    assert bot_discord.dinheiro(13932.4, "R$") == "R$ 13.932"
    assert bot_discord.dinheiro(-4228, "R$") == "−R$ 4.228"
    assert bot_discord.dinheiro(None, "US$") == "—"


def test_placar_ordena_por_lucro_e_conta_aprovadas(tmp_path, monkeypatch):
    pasta = tmp_path / "estrategias"
    pasta.mkdir()
    monkeypatch.setattr(relatorio, "PASTA", tmp_path)
    _relatorio(pasta, "macd", 13932, 31, False, 42)
    _relatorio(pasta, "rompimento", 4791, 265, False, 36)
    _relatorio(pasta, "macd", 999, 1, False, 1, instrumento="mnq")  # outro mercado: não entra
    msg = bot_discord.placar("win", raiz=RAIZ)
    assert msg["titulo"].endswith("0 de 2 estratégias aprovadas")
    assert msg["campos"][0][0] == "MACD"
    assert "R$ 13.932" in msg["campos"][0][1] and "6%" in msg["campos"][0][1]
    assert msg["campos"][-1] == ("Só comprar e segurar", "R$ 10.141")


def test_placar_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "PASTA", tmp_path)
    assert "nenhuma estratégia" in bot_discord.placar("win", raiz=RAIZ)["titulo"]


def test_vendedor_le_estado_do_mercado_certo(tmp_path):
    (tmp_path / "regras.json").write_text((RAIZ / "regras.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert "ainda não rodou" in bot_discord.vendedor("win", raiz=tmp_path)["titulo"]
    Estado(dia="2026-10-28", realizado_hoje=-12.5, pendentes_entrada={"macd": {}}).salvar(tmp_path / "estado_win.json")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "vendedor_trades_win.jsonl").write_text(
        json.dumps({"estrategia": "macd", "resultado_usd": 17.0, "motivo": "alvo"}) + "\n", encoding="utf-8")
    campos = dict(bot_discord.vendedor("win", raiz=tmp_path)["campos"])
    assert campos["Situação"] == "pronto para operar"
    assert campos["Resultado do dia"] == "−R$ 12"
    assert campos["Entradas para a próxima abertura"] == "MACD"
    assert "MACD: R$ 17 (alvo)" in campos["Últimos trades (1 no total)"]


def test_parar_e_religar_todos_os_mercados(tmp_path):
    Estado(desligado=True).salvar(tmp_path / "estado_win.json")
    arquivos = apertar_parar(tmp_path)
    assert {a.name for a in arquivos} == {"PARAR", "PARAR_win"}
    religar(tmp_path)
    assert not list(tmp_path.glob("PARAR*"))
    assert Estado.carregar(tmp_path / "estado_win.json").desligado is False


def test_comandos_montam_sem_conectar(monkeypatch):
    discord = pytest.importorskip("discord")
    chamado = {}
    monkeypatch.setattr(discord.Client, "run", lambda self, token, **kw: chamado.setdefault("token", token))
    bot_discord.rodar("token-falso")
    assert chamado["token"] == "token-falso"
