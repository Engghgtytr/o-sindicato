"""Linha de comando do laboratório.

    python laboratorio.py baixar
    python laboratorio.py testar --estrategia rompimento --param dias=55
    python laboratorio.py testar --estrategia rompimento --periodo cego --motivo "versão final"
    python laboratorio.py diario
    python laboratorio.py avaliar --estrategia macd --mercado win   (mini índice)

Nada aqui envia ordem para corretora.
"""
from __future__ import annotations

import argparse
import json
import sys

from sindicato.config import carregar_regras
from sindicato.dados import carregar, salvar_historico
from sindicato.diario import Diario
from sindicato.estrategia import ESTRATEGIAS
from sindicato.metricas import calcular, resumo_texto
from sindicato.motor import Custos, rodar
from sindicato.periodos import CofreFechado, fatiar


def converter(valor: str):
    for tipo in (int, float):
        try:
            return tipo(valor)
        except ValueError:
            pass
    return valor


def cmd_baixar(regras):
    for ticker in (regras["dados"]["serie_backtest"], regras["dados"]["serie_ao_vivo"]):
        df, info = salvar_historico(ticker)
        print(f"{ticker}: {len(df)} dias, de {df.index[0]:%d/%m/%Y} a {df.index[-1]:%d/%m/%Y} | {info}")


def cmd_testar(regras, args):
    if args.estrategia not in ESTRATEGIAS:
        sys.exit(f"Estratégias disponíveis: {', '.join(ESTRATEGIAS)}")
    params = dict(p.split("=", 1) for p in args.param)
    estrategia = ESTRATEGIAS[args.estrategia](**{k: converter(v) for k, v in params.items()})

    diario = Diario()
    df = carregar(regras["dados"]["serie_backtest"])
    try:
        dados, inicio = fatiar(df, args.periodo, regras, diario, motivo=args.motivo or "")
    except CofreFechado as erro:
        sys.exit(str(erro))

    resultado = rodar(dados, estrategia, Custos.das_regras(regras), regras["risco"]["contratos"], inicio)
    m = calcular(resultado.trades, resultado.patrimonio)
    registro = diario.registrar("teste", periodo=args.periodo, parametros=estrategia.parametros(), metricas=m)

    print(resumo_texto(estrategia.nome, args.periodo, m, regras["instrumento"]["simbolo"]))
    print(f"→ versão nº {diario.contar('teste')} do diário (aberturas do cego até agora: {diario.contar('abriu_cego')})")
    return registro


def montar_estrategia(nome: str, params: list[str]):
    if nome not in ESTRATEGIAS:
        sys.exit(f"Estratégias disponíveis: {', '.join(ESTRATEGIAS)}")
    valores = dict(p.split("=", 1) for p in params)
    return ESTRATEGIAS[nome](**{k: converter(v) for k, v in valores.items()})


def cmd_avaliar(regras, args):
    from sindicato.relatorio import avaliar

    estrategia = montar_estrategia(args.estrategia, args.param)
    diario = Diario()
    df = carregar(regras["dados"]["serie_backtest"])
    try:
        aquecimento = getattr(estrategia, "aquecimento", 250)
        dados, inicio = fatiar(df, args.periodo, regras, diario, motivo=args.motivo or "", aquecimento=aquecimento)
    except CofreFechado as erro:
        sys.exit(str(erro))

    s = regras["instrumento"]["simbolo"]
    print(f"{regras['instrumento']['nome']}: avaliando {estrategia.nome} [{args.periodo}] com {regras['avaliacao']['rodadas_coin_flip']} moedas…")
    r = avaliar(dados, inicio, args.periodo, estrategia, regras, diario)
    m, cf, v, mc = r["metricas"], r["coin_flip"], r["veredito"], r["monte_carlo"]
    print(resumo_texto(estrategia.nome, args.periodo, m, s) if m["trades"] else m.get("aviso"))
    print(f"  coin flip: {cf['sorteios_que_fizeram_melhor']} de {cf['rodadas']} sorteios fizeram igual ou melhor "
          f"(média da sorte: {s} {cf['media_lucro']:,.0f})")
    print(f"  comprar e segurar: {s} {r['comprar_e_segurar']['lucro_liquido']:,.0f}")
    if mc.get("rodadas"):
        print(f"  Monte Carlo: pior queda provável (95%) {s} {mc['drawdown_p95']:,.0f} | "
              f"chance de estourar o limite: {mc['chance_estourar_limite_pct']}%")
    if r.get("imposto"):
        print(f"  IR estimado: {s} {r['imposto']['imposto']:,.0f} → lucro depois do IR {s} {r['imposto']['lucro_depois_do_ir']:,.0f}")
    print(f"  VEREDITO: {'APROVADA' if v['aprovada'] else 'REPROVADA'} — {'; '.join(v['motivos'])}")
    print(f"  (versão nº {r['versao']} do diário; {v['versoes_testadas']} versões contadas no ajuste)")


def cmd_sindicato(regras, args):
    from sindicato.portfolio import montar
    from sindicato.relatorio import ler_todos

    relatorios = [r for r in ler_todos(so_ultima=True, instrumento=regras["instrumento"]["id"]) if r["periodo"] == "treino"]
    aprovadas = {r["estrategia"] for r in relatorios if r["veredito"]["aprovada"]}
    nomes = args.membros or sorted(aprovadas)
    if not nomes:
        sys.exit("Nenhuma estratégia aprovada no treino. Use --membros para montar um sindicato de demonstração.")
    por_nome = {r["estrategia"]: r for r in relatorios}
    membros = []
    for nome in nomes:
        params = {k: v for k, v in por_nome.get(nome, {}).get("parametros", {}).items() if k != "estrategia"}
        membros.append(ESTRATEGIAS[nome](**params))

    df = carregar(regras["dados"]["serie_backtest"])
    dados, inicio = fatiar(df, "treino", regras)
    r = montar(dados, inicio, "treino", membros, aprovadas, regras)
    c = r["combinado"]
    s = regras["instrumento"]["simbolo"]
    print(f"Sindicato [treino, {regras['instrumento']['nome']}] com {', '.join(nomes)}")
    print(f"  juntas: lucro {s} {c['lucro_liquido']:,.0f}, pior queda {s} {c['drawdown_max_usd']:,.0f} "
          f"(pior queda de uma sozinha: {s} {r['pior_drawdown_sozinha']:,.0f})")
    for par in r["pares_muito_parecidos"]:
        print(f"  atenção, muito parecidas: {par}")


def cmd_prever(regras, args):
    """Chance de subir no próximo pregão, para qualquer ativo do Yahoo (ex.: PETR4.SA, AAPL, ^NDX)."""
    import json as _json

    from sindicato.config import RAIZ
    from sindicato.dados import salvar_historico
    from sindicato.previsao import avaliar_acerto, prever_amanha, walk_forward

    diario = Diario()
    cego_inicio = pd_timestamp(regras["periodos"]["cego_inicio"])
    resultados = []
    for ticker in args.tickers:
        df, _ = salvar_historico(ticker)
        if len(df) < 800:
            print(f"{ticker}: histórico curto demais ({len(df)} dias) para treinar com honestidade.")
            continue
        prob = walk_forward(df)
        treino = avaliar_acerto(df[df.index < cego_inicio], prob[prob.index < cego_inicio])
        cego = None
        if args.motivo:
            diario.registrar("abriu_cego", motivo=f"previsor {ticker}: {args.motivo}")
            cego = avaliar_acerto(df[df.index >= cego_inicio], prob[prob.index >= cego_inicio])
        amanha = prever_amanha(df)
        r = {"ticker": ticker, "dias_de_historico": len(df), "acerto_treino": treino, "acerto_cego": cego, "amanha": amanha}
        diario.registrar("previsao", ticker=ticker, acerto_treino=treino, acerto_cego=cego, amanha=amanha)
        pasta = RAIZ / "relatorios" / "previsoes"
        pasta.mkdir(parents=True, exist_ok=True)
        nome = ticker.replace("^", "").replace("=", "_").replace("/", "_")
        (pasta / f"{nome}.json").write_text(_json.dumps(r, ensure_ascii=False, default=str), encoding="utf-8")
        resultados.append(r)

        print(f"\n{ticker} — último fechamento {amanha['fechamento']} em {amanha['base']}")
        print(f"  chance de subir no próximo pregão: {amanha['chance_subir_pct']}%  → {amanha['leitura']}")
        print(f"  acerto até 2020 (treinando só com o passado): {treino['acerto_pct']}% ± {treino['margem_pct']}  "
              f"| chutar 'sempre sobe': {treino['chute_sempre_sobe_pct']}%  "
              f"| {'GANHOU do chute' if treino['ganhou_do_sempre_sobe'] else 'NÃO ganhou do chute'}")
        if cego:
            print(f"  acerto 2021→hoje (cego): {cego['acerto_pct']}% ± {cego['margem_pct']}  "
                  f"| chutar 'sempre sobe': {cego['chute_sempre_sobe_pct']}%")
    return resultados


def pd_timestamp(texto):
    import pandas as pd

    return pd.Timestamp(texto)


def criar_avisos(mercado: str = "mnq"):
    from sindicato.avisos import Avisos
    from sindicato.config import carregar_env

    # Cada mercado pode ter o seu canal (ex.: DISCORD_WEBHOOK_URL_WIN); sem ele, usa o geral.
    env = carregar_env()
    webhook = env.get(f"DISCORD_WEBHOOK_URL_{mercado.upper()}") or env.get("DISCORD_WEBHOOK_URL")
    return Avisos(webhook, env.get("DISCORD_MEU_ID"))


def cmd_vendedor(regras, args):
    import time

    from sindicato.relatorio import ler_todos
    from sindicato.vendedor import FeedYahoo, Vendedor

    relatorios = {r["estrategia"]: r for r in ler_todos(so_ultima=True, instrumento=regras["instrumento"]["id"]) if r["periodo"] == "treino"}
    aprovadas = [n for n, r in relatorios.items() if r["veredito"]["aprovada"]]
    nomes = aprovadas
    if args.demonstracao:
        nomes = args.demonstracao
        print(f"ATENÇÃO: modo demonstração com estratégias NÃO aprovadas: {', '.join(nomes)}")
    if not nomes:
        sys.exit("Nenhuma estratégia aprovada. Para ver o Vendedor funcionando mesmo assim, use "
                 "--demonstracao rompimento (fica marcado como demonstração).")
    estrategias = []
    for nome in nomes:
        params = {k: v for k, v in relatorios.get(nome, {}).get("parametros", {}).items() if k != "estrategia"}
        estrategias.append(ESTRATEGIAS[nome](**params))

    avisos = criar_avisos(regras["instrumento"]["id"])
    if not avisos.webhook:
        print("Discord não configurado (.env sem DISCORD_WEBHOOK_URL): os avisos ficam só no painel.")
    vendedor = Vendedor(estrategias, regras, FeedYahoo(regras["dados"]["serie_ao_vivo"]), avisos)
    if args.uma_vez:
        print(vendedor.passo())
        return

    avisos.enviar("info", "O Sindicato ligou (simulado, sem ordens reais)", {"Mercado": regras["instrumento"]["nome"], "Estratégias": ", ".join(nomes)})
    ultimo = None
    try:
        while True:
            try:
                situacao = vendedor.passo()
            except Exception as erro:  # a internet caiu, o Yahoo mudou…: avisa e tenta de novo
                situacao = f"erro: {erro}"
                avisos.enviar("alerta", "Erro no Vendedor (vai tentar de novo em 1 minuto)", {"Erro": str(erro)[:200]}, urgente=True)
            if situacao != ultimo:
                print(f"{time.strftime('%H:%M')} {situacao}")
                ultimo = situacao
            if situacao in ("parado_pelo_botao", "desligado"):
                break
            time.sleep(60)
    except KeyboardInterrupt:
        print("Desligado pelo teclado. O estado está salvo; ligue de novo para continuar de onde parou.")


def cmd_parar():
    from sindicato.vendedor import apertar_parar

    apertar_parar()
    print("Botão de parar apertado: no próximo minuto todo Vendedor ligado fecha tudo (no papel) e desliga.")


def cmd_religar():
    from sindicato.vendedor import religar

    religar()
    print("Pronto: o Vendedor pode ser ligado de novo.")


def cmd_bot():
    from sindicato.bot_discord import rodar
    from sindicato.config import carregar_env

    token = carregar_env().get("DISCORD_BOT_TOKEN")
    if not token:
        sys.exit("Falta o DISCORD_BOT_TOKEN no arquivo .env (aba Bot do Discord Developer Portal → Reset Token).")
    print("Ligando o bot do Discord (Ctrl+C para desligar)…")
    rodar(token)


def cmd_discord_teste():
    avisos = criar_avisos()
    if not avisos.webhook:
        sys.exit("Falta o DISCORD_WEBHOOK_URL no arquivo .env (veja o .env.example).")
    print(avisos.enviar("info", "Teste do Sindicato: se você está lendo isto, o Discord funciona", {"Modo": "simulado"}))


def cmd_painel(args):
    from sindicato.painel import gerar

    arquivo = gerar()
    print(f"Painel atualizado: {arquivo}")
    if not args.nao_abrir:
        import webbrowser

        webbrowser.open(arquivo.as_uri())


def cmd_diario():
    for r in Diario().ler():
        print(json.dumps(r, ensure_ascii=False, default=str))


def main(argv=None):
    from sindicato.config import instrumentos_disponiveis

    p = argparse.ArgumentParser(description="O Sindicato: laboratório de estratégias (sem ordens reais)")
    sub = p.add_subparsers(dest="cmd", required=True)
    mercado = argparse.ArgumentParser(add_help=False)
    mercado.add_argument("--mercado", choices=instrumentos_disponiveis() or None,
                         help="mnq = Nasdaq (padrão), win = mini índice Bovespa")
    sub.add_parser("baixar", parents=[mercado], help="baixa/atualiza os dados grátis")
    t = sub.add_parser("testar", parents=[mercado], help="roda uma estratégia")
    t.add_argument("--estrategia", required=True)
    t.add_argument("--param", action="append", default=[], help="ex.: --param dias=55")
    t.add_argument("--periodo", choices=["treino", "cego"], default="treino")
    t.add_argument("--motivo", help="obrigatório para abrir o teste cego")
    a = sub.add_parser("avaliar", parents=[mercado], help="backtest + coin flip + comprar e segurar + Monte Carlo + veredito")
    a.add_argument("--estrategia", required=True)
    a.add_argument("--param", action="append", default=[])
    a.add_argument("--periodo", choices=["treino", "cego"], default="treino")
    a.add_argument("--motivo")
    s = sub.add_parser("sindicato", parents=[mercado], help="junta as estratégias aprovadas num portfólio")
    s.add_argument("--membros", nargs="*", help="para demonstração, escolhe membros mesmo sem aprovação")
    v = sub.add_parser("vendedor", parents=[mercado], help="liga o simulado ao vivo (sem ordens reais)")
    v.add_argument("--demonstracao", nargs="*", help="roda estratégias NÃO aprovadas, só para ver funcionando")
    v.add_argument("--uma-vez", action="store_true", help="roda um ciclo só e sai")
    pv = sub.add_parser("prever", help="chance de subir amanhã + quanto o previsor acertou no passado")
    pv.add_argument("tickers", nargs="+", help="ex.: PETR4.SA AAPL ^NDX")
    pv.add_argument("--motivo", help="se preencher, mostra também o acerto em 2021+ (abre o teste cego)")
    sub.add_parser("parar", help="botão de emergência: fecha tudo no papel e desliga o Vendedor")
    sub.add_parser("religar", help="libera o Vendedor depois do botão de parar")
    sub.add_parser("discord-teste", help="manda uma mensagem de teste para o Discord")
    sub.add_parser("bot", help="liga o bot do Discord (/organizar, /placar, /vendedor, /parar, /religar)")
    pn = sub.add_parser("painel", help="gera e abre o app com tudo o que o robô fez")
    pn.add_argument("--nao-abrir", action="store_true")
    sub.add_parser("diario", help="mostra todas as versões testadas")
    args = p.parse_args(argv)

    regras = carregar_regras(instrumento=getattr(args, "mercado", None))
    comandos = {
        "baixar": lambda: cmd_baixar(regras),
        "testar": lambda: cmd_testar(regras, args),
        "avaliar": lambda: cmd_avaliar(regras, args),
        "sindicato": lambda: cmd_sindicato(regras, args),
        "vendedor": lambda: cmd_vendedor(regras, args),
        "prever": lambda: cmd_prever(regras, args),
        "parar": cmd_parar,
        "religar": cmd_religar,
        "discord-teste": cmd_discord_teste,
        "bot": cmd_bot,
        "painel": lambda: cmd_painel(args),
        "diario": cmd_diario,
    }
    comandos[args.cmd]()


if __name__ == "__main__":
    main()
