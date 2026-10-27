"""Bot do Discord do Sindicato: organiza o servidor e responde comandos.

Comandos (barra "/" no chat):
  /organizar  cria a categoria, os canais e o cargo do Sindicato (só o dono do bot)
  /placar     placar das estratégias de um mercado
  /vendedor   como está o simulado ao vivo de um mercado
  /parar      botão de emergência do SIMULADO (só o dono do bot)
  /religar    libera o Vendedor de novo (só o dono do bot)

O bot só lê relatórios e aperta o botão de parar do simulado. Não manda ordem para
corretora. O token fica no .env (DISCORD_BOT_TOKEN), nunca no código.
"""

import json
from pathlib import Path

from .config import RAIZ, carregar_regras, instrumentos_disponiveis

CATEGORIA = "O Sindicato"
CARGO = "Sindicato"
CANAIS = [
    ("avisos-nasdaq", "Avisos do Vendedor do Nasdaq (simulado, sem ordens reais)"),
    ("avisos-mini-indice", "Avisos do Vendedor do mini índice (simulado, sem ordens reais)"),
    ("relatorios", "Fechamentos do dia e resultados dos testes"),
    ("comandos", "Use /placar, /vendedor, /parar e /religar aqui"),
]
NOME = {
    "cruzamento_medias": "Cruzamento de médias", "rompimento": "Rompimento de 20 dias", "reversao_ifr2": "Reversão IFR(2)",
    "tendencia_200": "Tendência dos 200 dias", "tartaruga_55": "Tartaruga (55/20)", "bollinger_reversao": "Bollinger: reversão",
    "tres_quedas": "Três quedas seguidas", "macd": "MACD", "virada_do_mes": "Virada do mês",
    "venda_abaixo_200": "Venda abaixo dos 200 dias", "previsor": "Previsor (modelo)",
}
VERDE, VERMELHO, AZUL = 0x2E9E5B, 0xD64545, 0x2F6FDE
RODAPE = "O Sindicato · simulado, nenhuma ordem real"


def dinheiro(valor: float | None, simbolo: str) -> str:
    if valor is None:
        return "—"
    texto = f"{abs(valor):,.0f}".replace(",", ".")
    return f"{'−' if valor < 0 else ''}{simbolo} {texto}"


def _sufixo(mercado: str) -> str:
    return "" if mercado == "mnq" else f"_{mercado}"


def placar(mercado: str, raiz: Path = RAIZ) -> dict:
    """Mensagem do /placar: as 5 estratégias com mais lucro no treino."""
    from .relatorio import ler_todos

    inst = carregar_regras(raiz / "regras.json", instrumento=mercado)["instrumento"]
    s = inst["simbolo"]
    rel = [r for r in ler_todos(so_ultima=True, instrumento=mercado) if r["periodo"] == "treino"]
    if not rel:
        return {"titulo": f"{inst['nome']}: nenhuma estratégia avaliada ainda", "cor": AZUL, "campos": [],
                "descricao": f"No PC: laboratorio.py avaliar --estrategia rompimento --mercado {mercado}"}
    aprovadas = sum(1 for r in rel if r["veredito"]["aprovada"])
    melhores = sorted(rel, key=lambda r: r["metricas"].get("lucro_liquido", 0), reverse=True)[:5]
    campos = []
    for r in melhores:
        cf = r["coin_flip"]
        sorte = round(100 * cf["sorteios_que_fizeram_melhor"] / cf["rodadas"]) if cf["rodadas"] else 100
        campos.append((
            NOME.get(r["estrategia"], r["estrategia"]),
            f"{dinheiro(r['metricas'].get('lucro_liquido'), s)} · a sorte fez igual ou melhor em {sorte}% · "
            f"{'APROVADA' if r['veredito']['aprovada'] else 'reprovada'}",
        ))
    campos.append(("Só comprar e segurar", dinheiro(melhores[0]["comprar_e_segurar"]["lucro_liquido"], s)))
    return {
        "titulo": f"{inst['nome']}: {aprovadas} de {len(rel)} estratégias aprovadas",
        "descricao": "Treino de 2010 a 2020, com custos. As 5 de maior lucro:",
        "cor": VERDE if aprovadas else VERMELHO,
        "campos": campos,
    }


def vendedor(mercado: str, raiz: Path = RAIZ) -> dict:
    """Mensagem do /vendedor: situação do simulado ao vivo."""
    inst = carregar_regras(raiz / "regras.json", instrumento=mercado)["instrumento"]
    s = inst["simbolo"]
    arquivo = raiz / f"estado{_sufixo(mercado)}.json"
    if not arquivo.exists():
        return {"titulo": f"Vendedor do {inst['nome']}: ainda não rodou", "cor": AZUL, "campos": [],
                "descricao": "Ligue pelo atalho LIGAR O VENDEDOR no PC."}
    est = json.loads(arquivo.read_text(encoding="utf-8"))
    if est.get("desligado"):
        situacao = "desligado pelo botão de parar"
    elif est.get("bloqueado_ate") and est.get("bloqueado_ate") == est.get("dia"):
        situacao = "travado hoje (bateu a perda máxima)"
    else:
        situacao = "pronto para operar"
    campos = [
        ("Situação", situacao),
        ("Resultado do dia", dinheiro(est.get("realizado_hoje", 0.0), s)),
        ("Posições abertas", ", ".join(NOME.get(n, n) for n in est.get("posicoes", {})) or "nenhuma"),
        ("Entradas para a próxima abertura", ", ".join(NOME.get(n, n) for n in est.get("pendentes_entrada", {})) or "nenhuma"),
    ]
    log = raiz / "logs" / f"vendedor_trades{_sufixo(mercado)}.jsonl"
    trades = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()] if log.exists() else []
    if trades:
        ultimos = [f"{NOME.get(t['estrategia'], t['estrategia'])}: {dinheiro(t['resultado_usd'], s)} ({t['motivo']})" for t in trades[-3:]]
        campos.append((f"Últimos trades ({len(trades)} no total)", "\n".join(reversed(ultimos))))
    return {"titulo": f"Vendedor do {inst['nome']}", "descricao": f"Dia {est.get('dia', '—')}", "cor": AZUL, "campos": campos}


def rodar(token: str) -> None:
    import discord
    from discord import app_commands

    from .vendedor import apertar_parar, religar

    cliente = discord.Client(intents=discord.Intents.default())
    arvore = app_commands.CommandTree(cliente)
    nomes = {i: carregar_regras(instrumento=i)["instrumento"]["nome"].split(" (")[0] for i in instrumentos_disponiveis()}
    escolhas = [app_commands.Choice(name=n, value=i) for i, n in nomes.items()]

    def embed(msg: dict) -> discord.Embed:
        e = discord.Embed(title=msg["titulo"], description=msg.get("descricao"), color=msg["cor"])
        for nome, valor in msg["campos"]:
            e.add_field(name=nome, value=valor[:1024], inline=False)
        e.set_footer(text=RODAPE)
        return e

    # Os comandos que mexem no PC (parar, religar) e no servidor (organizar) só obedecem ao
    # dono do bot no Developer Portal: outro administrador do servidor não consegue usar.
    dono = {"id": None}

    def admin(interacao: discord.Interaction) -> bool:
        return dono["id"] is not None and interacao.user.id == dono["id"]

    @arvore.command(name="placar", description="Placar das estratégias de um mercado")
    @app_commands.describe(mercado="Nasdaq ou mini índice")
    @app_commands.choices(mercado=escolhas)
    async def cmd_placar(interacao: discord.Interaction, mercado: app_commands.Choice[str] | None = None):
        await interacao.response.send_message(embed=embed(placar(mercado.value if mercado else "mnq")))

    @arvore.command(name="vendedor", description="Como está o simulado ao vivo")
    @app_commands.describe(mercado="Nasdaq ou mini índice")
    @app_commands.choices(mercado=escolhas)
    async def cmd_vendedor(interacao: discord.Interaction, mercado: app_commands.Choice[str] | None = None):
        await interacao.response.send_message(embed=embed(vendedor(mercado.value if mercado else "mnq")))

    @arvore.command(name="parar", description="Botão de emergência: fecha tudo no papel e desliga o simulado")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def cmd_parar(interacao: discord.Interaction):
        if not admin(interacao):
            await interacao.response.send_message("Só o dono do bot pode apertar o botão de parar.", ephemeral=True)
            return
        apertar_parar()
        await interacao.response.send_message(
            "🛑 Botão de parar apertado: no próximo minuto todo Vendedor ligado fecha tudo (no papel) e desliga. "
            "Para voltar: /religar.")

    @arvore.command(name="religar", description="Libera o Vendedor depois do botão de parar")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def cmd_religar(interacao: discord.Interaction):
        if not admin(interacao):
            await interacao.response.send_message("Só o dono do bot pode religar.", ephemeral=True)
            return
        religar()
        await interacao.response.send_message(
            "✅ Liberado. Ligue o Vendedor de novo pelo atalho no PC (ele não religa sozinho).")

    @arvore.command(name="organizar", description="Cria a categoria, os canais e o cargo do Sindicato")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def cmd_organizar(interacao: discord.Interaction):
        if not admin(interacao):
            await interacao.response.send_message("Só o dono do bot pode organizar o servidor.", ephemeral=True)
            return
        await interacao.response.defer(ephemeral=True, thinking=True)
        servidor = interacao.guild
        feitos, ja_tinha = [], []
        if discord.utils.get(servidor.roles, name=CARGO):
            ja_tinha.append(f"cargo {CARGO}")
        else:
            await servidor.create_role(name=CARGO, colour=discord.Colour(0xB07A10), mentionable=True,
                                       reason="O Sindicato: /organizar")
            feitos.append(f"cargo {CARGO}")
        categoria = discord.utils.get(servidor.categories, name=CATEGORIA)
        if categoria:
            ja_tinha.append(f"categoria {CATEGORIA}")
        else:
            categoria = await servidor.create_category(CATEGORIA, reason="O Sindicato: /organizar")
            feitos.append(f"categoria {CATEGORIA}")
        for nome, tema in CANAIS:
            if discord.utils.get(categoria.text_channels, name=nome):
                ja_tinha.append(f"#{nome}")
            else:
                await categoria.create_text_channel(nome, topic=tema, reason="O Sindicato: /organizar")
                feitos.append(f"#{nome}")
        texto = f"Criado: {', '.join(feitos) or 'nada (já estava tudo pronto)'}."
        if ja_tinha:
            texto += f"\nJá existia: {', '.join(ja_tinha)}."
        texto += ("\nDica: para os avisos irem para #avisos-mini-indice, crie um webhook nesse canal "
                  "(Editar canal → Integrações) e cole a URL no .env como DISCORD_WEBHOOK_URL_WIN=")
        await interacao.followup.send(texto, ephemeral=True)

    @cliente.event
    async def on_ready():
        info = await cliente.application_info()
        dono["id"] = info.owner.id
        # Registrar os comandos em cada servidor faz eles aparecerem na hora (o global demora).
        for servidor in cliente.guilds:
            arvore.copy_global_to(guild=servidor)
            await arvore.sync(guild=servidor)
        print(f"Bot ligado como {cliente.user} em {len(cliente.guilds)} servidor(es). Comandos: "
              "/organizar /placar /vendedor /parar /religar")

    cliente.run(token, log_handler=None)
