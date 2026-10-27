"""O Vendedor (The Dealer): o simulado ao vivo.

Roda as estratégias do Sindicato em dias NOVOS, com preço de verdade (futuro NQ=F,
grátis e com atraso), mas SEM ORDEM REAL. Registra cada trade e avisa no Discord.

Ciclo (chamado a cada minuto):
  1. Botão de parar apertado? Fecha tudo no papel e desliga.
  2. Fora do horário (Nasdaq: 9h30–16h de Nova York; mini índice: 10h–17h de Brasília)?
     Depois do fechamento, processa o dia:
     sinais no gráfico diário → entradas e saídas pendentes para a abertura de amanhã.
  3. No horário: confere se o dado não está velho; executa as pendências na primeira
     barra depois da abertura; confere stop e alvo minuto a minuto (pior caso: stop);
     soma o resultado do dia e, se bater a perda máxima, fecha tudo e trava até amanhã.
  4. Batimento (heartbeat) a cada hora no Discord.

O estado fica salvo em estado.json (mini índice: estado_win.json): se o PC reiniciar, ele volta de onde parou.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from .avisos import Avisos
from .config import RAIZ
from .estrategia import Estrategia

NY = ZoneInfo("America/New_York")
ABRE, FECHA, PROCESSA = time(9, 30), time(16, 0), time(16, 15)


class Feed(Protocol):
    def diario(self) -> pd.DataFrame: ...
    def minutos(self) -> pd.DataFrame: ...  # índice em UTC (tz-aware), colunas padrão


@dataclass
class Estado:
    dia: str = ""
    posicoes: dict = field(default_factory=dict)  # estrategia -> posição
    pendentes_entrada: dict = field(default_factory=dict)
    pendentes_saida: list = field(default_factory=list)
    realizado_hoje: float = 0.0
    bloqueado_ate: str = ""  # data (fuso do mercado) até a qual não opera
    ultimo_minuto: str = ""
    ultimo_batimento: str = ""
    processou_fechamento: str = ""
    aviso_dado_velho: str = ""
    desligado: bool = False

    @classmethod
    def carregar(cls, arquivo: Path) -> "Estado":
        if arquivo.exists():
            return cls(**json.loads(arquivo.read_text(encoding="utf-8")))
        return cls()

    def salvar(self, arquivo: Path) -> None:
        temporario = arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
        temporario.replace(arquivo)  # troca de uma vez: o arquivo nunca fica pela metade


class Vendedor:
    def __init__(
        self,
        estrategias: list[Estrategia],
        regras: dict,
        feed: Feed,
        avisos: Avisos,
        pasta: Path = RAIZ,
        relogio: Callable[[], datetime] | None = None,
        tolerancia_dado_velho: timedelta = timedelta(minutes=25),
    ):
        self.estrategias = {e.nome: e for e in estrategias}
        self.regras = regras
        self.feed = feed
        self.avisos = avisos
        self.tolerancia = tolerancia_dado_velho

        # Mercado: Nasdaq (Nova York) por padrão; mini índice usa o horário da B3.
        inst = regras.get("instrumento") or {"id": "mnq", "nome": "NQ=F", "simbolo": "US$"}
        mercado = regras.get("mercado") or {"fuso": "America/New_York", "abre": "09:30", "fecha": "16:00", "processa": "16:15"}
        self.id = inst["id"]
        self.simbolo = inst["simbolo"]
        self.instrumento = f"{regras.get('dados', {}).get('serie_ao_vivo', 'NQ=F')} (simulado, {regras['risco']['contratos']} contrato)"
        self.fuso = ZoneInfo(mercado["fuso"])
        self.abre, self.fecha, self.processa = (time.fromisoformat(mercado[k]) for k in ("abre", "fecha", "processa"))
        self.relogio = relogio if relogio is not None else (lambda: datetime.now(self.fuso))
        self.local = "NY" if mercado["fuso"] == "America/New_York" else "Brasília"
        self.rotulo_hora = f"Hora ({self.local})"

        sufixo = "" if self.id == "mnq" else f"_{self.id}"
        self.arquivo_estado = pasta / f"estado{sufixo}.json"
        self.arquivo_parar = pasta / f"PARAR{sufixo}"
        self.arquivo_trades = pasta / "logs" / f"vendedor_trades{sufixo}.jsonl"
        self.arquivo_trades.parent.mkdir(parents=True, exist_ok=True)
        self.estado = Estado.carregar(self.arquivo_estado)

        c = regras["contrato"]
        self.mult = c.get("valor_por_ponto", c.get("dolares_por_ponto")) * regras["risco"]["contratos"]
        self.slip = c["tick"] * c["slippage_ticks_por_lado"]
        self.comissao = c["comissao_por_lado"] * 2 * regras["risco"]["contratos"]
        self.perda_maxima = regras["risco"]["perda_maxima_diaria"]

    # ---------- utilidades ----------

    def _salvar(self):
        self.estado.salvar(self.arquivo_estado)

    def _registrar_trade(self, trade: dict):
        with open(self.arquivo_trades, "a", encoding="utf-8") as f:
            f.write(json.dumps(trade, ensure_ascii=False, default=str) + "\n")

    def _fechar(self, nome: str, preco: float, quando: datetime, motivo: str):
        pos = self.estado.posicoes.pop(nome)
        d = pos["direcao"]
        preco_saida = float(preco) - self.slip * d
        pontos = (preco_saida - pos["entrada"]) * d
        resultado = round(pontos * self.mult - self.comissao, 2)
        self.estado.realizado_hoje = round(self.estado.realizado_hoje + resultado, 2)
        trade = {
            "estrategia": nome, "direcao": "compra" if d == 1 else "venda", "instrumento": self.instrumento,
            "entrada_em": pos["quando"], "preco_entrada": pos["entrada"],
            "saida_em": quando.isoformat(timespec="minutes"), "preco_saida": round(preco_saida, 2),
            "motivo": motivo, "pontos": round(pontos, 2), "resultado_usd": resultado,
        }
        self._registrar_trade(trade)
        self.avisos.enviar(
            "compra" if resultado > 0 else "venda",
            f"Saída {nome}: {'+' if resultado > 0 else ''}{self.simbolo} {resultado:,.2f}",
            {"Motivo": motivo, "Preço": f"{preco_saida:,.2f}", "Resultado do dia": f"{self.simbolo} {self.estado.realizado_hoje:,.2f}"},
        )

    def _abrir(self, nome: str, pend: dict, preco_ref: float, quando: datetime):
        d = pend["direcao"]
        preco_ref = float(preco_ref)  # preço inteiro (comum no mini índice) vira número do Python
        entrada = preco_ref + self.slip * d
        self.estado.posicoes[nome] = {
            "direcao": d, "entrada": round(entrada, 2), "quando": quando.isoformat(timespec="minutes"), "dias": 0,
            "stop": round(preco_ref - d * pend["dist_stop"], 2), "alvo": round(preco_ref + d * pend["dist_alvo"], 2),
        }
        p = self.estado.posicoes[nome]
        self.avisos.enviar(
            "compra" if d == 1 else "venda",
            f"Entrada {nome}: {'COMPRA' if d == 1 else 'VENDA'} 1 contrato (simulado)",
            {"Preço": f"{entrada:,.2f}", "Stop": f"{p['stop']:,.2f}", "Alvo": f"{p['alvo']:,.2f}", self.rotulo_hora: quando.strftime("%H:%M")},
        )

    def resultado_do_dia(self, preco_atual: float | None) -> float:
        aberto = 0.0
        if preco_atual is not None:
            for pos in self.estado.posicoes.values():
                aberto += (preco_atual - pos["entrada"]) * pos["direcao"] * self.mult
        return round(self.estado.realizado_hoje + aberto, 2)

    # ---------- o ciclo ----------

    def passo(self) -> str:
        agora = self.relogio().astimezone(self.fuso)
        hoje = agora.date().isoformat()

        if self.estado.desligado:
            return "desligado"

        if self.estado.dia != hoje:  # dia novo: zera o resultado do dia
            self.estado.dia = hoje
            self.estado.realizado_hoje = 0.0
            self._salvar()

        # 1) Botão de parar
        if self.arquivo_parar.exists():
            ultimo = self._ultimo_preco()
            for nome in list(self.estado.posicoes):
                self._fechar(nome, ultimo if ultimo is not None else self.estado.posicoes[nome]["entrada"], agora, "botao_parar")
            self.estado.pendentes_entrada, self.estado.pendentes_saida = {}, []
            self.estado.desligado = True
            self._salvar()
            self.arquivo_parar.unlink()
            self.avisos.enviar("alerta", "BOTÃO DE PARAR: tudo fechado e o Vendedor desligou", {}, urgente=True)
            return "parado_pelo_botao"

        dia_util = agora.weekday() < 5
        no_horario = dia_util and self.abre <= agora.time() < self.fecha

        # 2) Fora do horário: processa o fechamento do dia uma vez
        if not no_horario:
            if dia_util and agora.time() >= self.processa and self.estado.processou_fechamento != hoje:
                self._processar_fechamento(agora)
                return "processou_fechamento"
            return "fora_do_horario"

        # Batimento a cada hora
        if not self.estado.ultimo_batimento or agora - datetime.fromisoformat(self.estado.ultimo_batimento) >= timedelta(hours=1):
            self.estado.ultimo_batimento = agora.isoformat(timespec="minutes")
            self.avisos.enviar("info", "Batimento: Vendedor ativo", {
                self.rotulo_hora: agora.strftime("%H:%M"), "Posições": len(self.estado.posicoes),
                "Resultado do dia": f"{self.simbolo} {self.estado.realizado_hoje:,.2f}"})
            self._salvar()

        if self.estado.bloqueado_ate == hoje:
            return "travado_hoje"

        # 3) Barras novas de minuto
        barras = self.feed.minutos()
        if barras is None or barras.empty:
            return "sem_dados"
        barras = barras.tz_convert(self.fuso)
        barras = barras[barras.index.date == agora.date()]
        barras = barras[barras.index.time >= self.abre]
        if barras.empty:
            return "sem_dados"

        if agora - barras.index[-1].to_pydatetime() > self.tolerancia:
            if self.estado.aviso_dado_velho != hoje:
                self.estado.aviso_dado_velho = hoje
                self.avisos.enviar("alerta", "Dado velho: sem preço recente, nada de novas entradas", {
                    f"Última barra ({self.local})": barras.index[-1].strftime("%H:%M")}, urgente=True)
                self._salvar()
            return "dado_velho"

        if self.estado.ultimo_minuto:
            novas = barras[barras.index > pd.Timestamp(self.estado.ultimo_minuto)]
        else:
            novas = barras

        for quando, barra in novas.iterrows():
            q = quando.to_pydatetime()
            # Pendências executam na primeira barra do dia
            for nome in list(self.estado.pendentes_saida):
                if nome in self.estado.posicoes:
                    self._fechar(nome, barra["abertura"], q, "sinal_saida")
            self.estado.pendentes_saida = []
            for nome, pend in list(self.estado.pendentes_entrada.items()):
                if nome not in self.estado.posicoes:
                    self._abrir(nome, pend, barra["abertura"], q)
            self.estado.pendentes_entrada = {}

            for nome in list(self.estado.posicoes):
                pos = self.estado.posicoes[nome]
                d = pos["direcao"]
                tocou_stop = barra["minima"] <= pos["stop"] if d == 1 else barra["maxima"] >= pos["stop"]
                tocou_alvo = barra["maxima"] >= pos["alvo"] if d == 1 else barra["minima"] <= pos["alvo"]
                if tocou_stop:
                    self._fechar(nome, min(pos["stop"], barra["abertura"]) if d == 1 else max(pos["stop"], barra["abertura"]), q, "stop")
                elif tocou_alvo:
                    self._fechar(nome, pos["alvo"], q, "alvo")

            # Trava de perda diária (fechados + abertos)
            if self.resultado_do_dia(barra["fechamento"]) <= -self.perda_maxima:
                for nome in list(self.estado.posicoes):
                    self._fechar(nome, barra["fechamento"], q, "trava_diaria")
                self.estado.bloqueado_ate = hoje
                self.estado.ultimo_minuto = quando.isoformat()
                self._salvar()
                self.avisos.enviar("alerta", f"TRAVA ATIVADA: perda do dia passou de {self.simbolo} {self.perda_maxima:,.0f}", {
                    "Resultado do dia": f"{self.simbolo} {self.estado.realizado_hoje:,.2f}", "Volta a operar": "amanhã"}, urgente=True)
                return "travou"

            self.estado.ultimo_minuto = quando.isoformat()

        self._salvar()
        return "operando"

    def _ultimo_preco(self) -> float | None:
        try:
            b = self.feed.minutos()
            return None if b is None or b.empty else float(b["fechamento"].iloc[-1])
        except Exception:
            return None

    def _processar_fechamento(self, agora: datetime):
        diario = self.feed.diario()
        hoje = agora.date().isoformat()
        sinais_do_dia = []
        for nome, est in self.estrategias.items():
            if nome in self.estado.posicoes:
                pos = self.estado.posicoes[nome]
                pos["dias"] += 1
                if bool(est.saida(diario).iloc[-1]) or pos["dias"] >= est.max_dias:
                    self.estado.pendentes_saida.append(nome)
                continue
            s = int(est.sinais(diario).iloc[-1])
            stop, alvo = (x.iloc[-1] for x in est.distancias(diario))
            if s != 0 and pd.notna(stop):
                self.estado.pendentes_entrada[nome] = {"direcao": s, "dist_stop": float(stop), "dist_alvo": float(alvo)}
                sinais_do_dia.append(f"{nome}: {'compra' if s == 1 else 'venda'}")
        self.estado.processou_fechamento = hoje
        self._salvar()
        self.avisos.enviar("relatorio", f"Fechamento de {agora:%d/%m}", {
            "Resultado do dia": f"{self.simbolo} {self.estado.realizado_hoje:,.2f}",
            "Posições abertas": len(self.estado.posicoes),
            "Para amanhã": ", ".join(sinais_do_dia) or "nenhuma entrada",
        })


class FeedYahoo:
    """Preços grátis do Yahoo (atrasados alguns minutos). Só para o simulado."""

    def __init__(self, ticker: str = "NQ=F"):
        self.ticker = ticker

    def diario(self) -> pd.DataFrame:
        from .dados import salvar_historico

        df, _ = salvar_historico(self.ticker)
        return df

    def minutos(self) -> pd.DataFrame:
        import warnings

        import yfinance as yf

        from .dados import limpar

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bruto = yf.download(self.ticker, period="1d", interval="1m", progress=False, auto_adjust=False)
        if bruto is None or bruto.empty:
            return pd.DataFrame()
        df, _ = limpar(bruto)
        return df.tz_localize("UTC")


def apertar_parar(pasta: Path = RAIZ) -> list[Path]:
    """Botão de emergência: um arquivo por mercado, então desliga todo Vendedor que estiver ligado."""
    from .config import instrumentos_disponiveis

    arquivos = [pasta / ("PARAR" if i == "mnq" else f"PARAR_{i}") for i in instrumentos_disponiveis() or ["mnq"]]
    for arquivo in arquivos:
        arquivo.write_text("parar", encoding="utf-8")
    return arquivos


def religar(pasta: Path = RAIZ) -> None:
    """Libera os Vendedores depois do botão de parar."""
    for arquivo in pasta.glob("estado*.json"):
        estado = Estado.carregar(arquivo)
        estado.desligado = False
        estado.salvar(arquivo)
    for botao in pasta.glob("PARAR*"):
        botao.unlink()
