// Painel do Sindicato. Lê window.PAINEL (gerado por `python laboratorio.py painel`)
// e desenha tudo com DOM e SVG. Todo texto entra por textContent: nada vira HTML.
(function () {
  'use strict';

  const D = window.PAINEL;
  const main = document.getElementById('conteudo');
  const SVG = 'http://www.w3.org/2000/svg';

  // ---------- utilidades ----------
  function h(tag, props, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const f of filhos.flat()) if (f != null && f !== false) el.append(f instanceof Node ? f : document.createTextNode(String(f)));
    return el;
  }
  function s(tag, attrs, ...filhos) {
    const el = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
    for (const f of filhos.flat()) if (f != null) el.append(f instanceof Node ? f : document.createTextNode(String(f)));
    return el;
  }
  // Mercado escolhido no topo: "mnq" (Nasdaq, em US$) ou "win" (mini índice, em R$).
  let MERCADO = 'mnq';
  let MOEDA = 'US$';
  const M = () => D.mercados[MERCADO];
  const flag = () => (MERCADO === 'mnq' ? '' : ` --mercado ${MERCADO}`);
  const usd = (v, sim = MOEDA) => (v == null ? '—' : `${v < 0 ? '−' : ''}${sim} ${Math.abs(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`);
  const usd2 = (v, sim = MOEDA) => (v == null ? '—' : `${v < 0 ? '−' : ''}${sim} ${Math.abs(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
  const num = (v, casas = 0) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: casas }));
  const data = (iso) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—');
  const classeValor = (v) => (v > 0 ? 'ganho' : v < 0 ? 'perda' : '');
  const MOTIVO = { alvo: 'alvo', stop: 'stop', gap_stop: 'gap além do stop', gap_alvo: 'gap além do alvo', sinal_saida: 'sinal de saída', tempo: 'tempo máximo', fim_dos_dados: 'fim dos dados', trava_diaria: 'trava diária', botao_parar: 'botão de parar' };
  const NOME = {
    cruzamento_medias: 'Cruzamento de médias', rompimento: 'Rompimento de 20 dias', reversao_ifr2: 'Reversão IFR(2)',
    tendencia_200: 'Tendência dos 200 dias', tartaruga_55: 'Tartaruga (55/20)', bollinger_reversao: 'Bollinger: reversão',
    tres_quedas: 'Três quedas seguidas', macd: 'MACD', virada_do_mes: 'Virada do mês', venda_abaixo_200: 'Venda abaixo dos 200 dias',
    previsor: 'Previsor (modelo)',
  };
  const nome = (n) => NOME[n] || n;
  // Parâmetros que mudaram em relação ao padrão aparecem no nome da versão (ex.: "dias=5").
  const PADRAO = { virada_do_mes: { dias: 4 } };
  const rotuloVersao = (r) => {
    const extras = Object.entries(PADRAO[r.estrategia] || {})
      .filter(([k, v]) => r.parametros[k] !== v)
      .map(([k]) => `${k}=${r.parametros[k]}`);
    return `${nome(r.estrategia)}${extras.length ? ` (${extras.join(', ')})` : ''} · v${r.versao}`;
  };

  function vazio(texto, comando) {
    return h('div', { class: 'vazio' }, h('p', { text: texto }), comando ? h('code', { text: comando }) : null);
  }

  function selo(aprovada, demo) {
    if (demo) return h('span', { class: 'veredito veredito--demo', text: 'demonstração' });
    return h('span', { class: `veredito ${aprovada ? 'veredito--sim' : 'veredito--nao'}`, text: aprovada ? 'APROVADA' : 'REPROVADA' });
  }

  // ---------- gráficos SVG ----------
  // Linhas: séries [{nome, cor, pontos: [[data, valor]], tracejado}]
  // No celular, um desenho mais estreito: assim os números não ficam minúsculos.
  const larguraGrafico = () => (window.innerWidth < 640 ? 420 : 800);

  function graficoLinhas(series, { altura = 260, rotulo = '' } = {}) {
    const W = larguraGrafico(), H = altura, m = { e: 64, d: 12, t: 12, b: 26 };
    const todos = series.flatMap((x) => x.pontos);
    if (!todos.length) return vazio('Sem dados para o gráfico.');
    const tempos = todos.map((p) => Date.parse(p[0]));
    const valores = todos.map((p) => p[1]).concat(0);
    const t0 = Math.min(...tempos), t1 = Math.max(...tempos);
    let v0 = Math.min(...valores), v1 = Math.max(...valores);
    if (v0 === v1) { v0 -= 1; v1 += 1; }
    const x = (t) => m.e + ((t - t0) / (t1 - t0 || 1)) * (W - m.e - m.d);
    const y = (v) => m.t + (1 - (v - v0) / (v1 - v0)) * (H - m.t - m.b);

    // Linhas de referência; a do zero só ganha rótulo se não encostar nas outras.
    const marcas = [v0, (v0 + v1) / 2, v1];
    if (marcas.every((v) => Math.abs(y(v) - y(0)) > 16)) marcas.push(0);
    const grade = marcas.concat(marcas.includes(0) ? [] : [null]).map((v) =>
      v === null
        ? s('line', { x1: m.e, x2: W - m.d, y1: y(0), y2: y(0), stroke: '#9aa3af', 'stroke-width': 1 }) :
      s('g', null,
        s('line', { x1: m.e, x2: W - m.d, y1: y(v), y2: y(v), stroke: v === 0 ? '#9aa3af' : '#e3e6ea', 'stroke-width': 1 }),
        s('text', { x: m.e - 6, y: y(v) + 4, 'text-anchor': 'end', class: 'eixo' }, usd(v)),
      ));
    const anos = [new Date(t0).getFullYear(), new Date(t1).getFullYear()];
    const eixoX = [
      s('text', { x: m.e, y: H - 6, class: 'eixo' }, anos[0]),
      s('text', { x: W - m.d, y: H - 6, 'text-anchor': 'end', class: 'eixo' }, anos[1]),
    ];
    const linhas = series.map((sr) =>
      s('polyline', {
        points: sr.pontos.map((p) => `${x(Date.parse(p[0])).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' '),
        fill: 'none', stroke: sr.cor, 'stroke-width': sr.grossa ? 2.2 : 1.5,
        'stroke-dasharray': sr.tracejado ? '5 4' : null, 'stroke-linejoin': 'round',
      }));
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': rotulo }, grade, eixoX, linhas);
    const legenda = h('p', { class: 'legenda' }, series.map((sr) => h('span', null, h('i', { style: `background:${sr.cor}` }), sr.nome)));
    return h('figure', { class: 'grafico' }, svg, legenda);
  }

  // Histograma dos lucros do coin flip, com a linha da estratégia.
  function histograma(valores, marca, { rotulo = '' } = {}) {
    const W = larguraGrafico(), H = 230, m = { e: 12, d: 12, t: 22, b: 26 };
    if (!valores.length) return vazio('A estratégia não fez trades, então não houve coin flip.');
    const min = Math.min(...valores, marca), max = Math.max(...valores, marca);
    const caixas = 36, largura = (max - min) / caixas || 1;
    const contagem = new Array(caixas).fill(0);
    for (const v of valores) contagem[Math.min(caixas - 1, Math.floor((v - min) / largura))]++;
    const topo = Math.max(...contagem);
    const x = (v) => m.e + ((v - min) / (max - min || 1)) * (W - m.e - m.d);
    const bw = (W - m.e - m.d) / caixas;
    const barras = contagem.map((c, i) => {
      const altura = (c / topo) * (H - m.t - m.b);
      const meio = min + (i + 0.5) * largura;
      return s('rect', { x: m.e + i * bw + 1, y: H - m.b - altura, width: bw - 2, height: altura, rx: 2, fill: meio >= marca ? '#b07a10' : '#e5cf9e' });
    });
    const xm = x(marca);
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': rotulo },
      barras,
      s('line', { x1: xm, x2: xm, y1: m.t - 6, y2: H - m.b, stroke: '#1f4fbf', 'stroke-width': 2.5 }),
      s('text', { x: Math.min(Math.max(xm, 90), W - 90), y: 12, 'text-anchor': 'middle', class: 'eixo', style: 'fill:#1f4fbf;font-weight:700' }, `estratégia: ${usd(marca)}`),
      s('text', { x: m.e, y: H - 6, class: 'eixo' }, usd(min)),
      s('text', { x: W - m.d, y: H - 6, 'text-anchor': 'end', class: 'eixo' }, usd(max)),
    );
    const legenda = h('p', { class: 'legenda' },
      h('span', null, h('i', { style: 'background:#b07a10' }), 'sorteios que fizeram igual ou melhor'),
      h('span', null, h('i', { style: 'background:#e5cf9e' }), 'sorteios que fizeram pior'),
      h('span', null, h('i', { style: 'background:#1f4fbf' }), 'resultado da estratégia'));
    return h('figure', { class: 'grafico' }, svg, legenda);
  }

  function tabela(colunas, linhas, { porPagina = 25, rotulo = 'Tabela' } = {}) {
    let mostrando = porPagina;
    const corpo = h('tbody');
    // tabindex: no celular a tabela rola de lado; quem usa teclado precisa conseguir rolar também.
    const caixa = h('div', { class: 'tabela-caixa', tabindex: '0', role: 'region', 'aria-label': rotulo },
      h('table', null,
        h('thead', null, h('tr', null, colunas.map((c) => h('th', { class: c.num ? 'num' : null, scope: 'col', text: c.titulo })))),
        corpo));
    const mais = h('button', { class: 'botao', type: 'button' });
    function desenhar() {
      corpo.replaceChildren(...linhas.slice(0, mostrando).map((l) =>
        h('tr', null, colunas.map((c) => {
          const v = c.valor(l);
          return h('td', { class: [c.num ? 'num' : '', c.cor ? classeValor(c.cor(l)) : ''].join(' ').trim() || null, text: v });
        }))));
      mais.textContent = `Mostrar mais (${linhas.length - mostrando} restantes)`;
      mais.hidden = mostrando >= linhas.length;
    }
    mais.addEventListener('click', () => { mostrando += porPagina * 2; desenhar(); });
    desenhar();
    return h('div', null, caixa, mais);
  }

  function metricas(m) {
    const itens = [
      ['Trades', num(m.trades), null],
      ['Lucro líquido', usd(m.lucro_liquido), m.lucro_liquido],
      ['Taxa de acerto', m.taxa_acerto_pct == null ? '—' : `${num(m.taxa_acerto_pct, 1)}%`, null],
      ['Profit factor', m.profit_factor == null ? '∞' : num(m.profit_factor, 2), null],
      ['Payoff', m.payoff == null ? '—' : num(m.payoff, 2), null],
      ['Pior queda (drawdown)', usd(m.drawdown_max_usd), null],
      ['Maior sequência de perdas', num(m.maior_sequencia_perdas), null],
      ['Custos pagos', usd(m.custos_totais_usd), null],
    ];
    return h('dl', { class: 'metricas' }, itens.map(([t, v, c]) => h('div', null, h('dt', { text: t }), h('dd', { class: c == null ? null : classeValor(c), text: v }))));
  }

  // ---------- seções ----------
  let estrategias = [];
  let escolhida = 0;
  function escolherMercado(id) {
    MERCADO = D.mercados[id] ? id : 'mnq';
    MOEDA = M().simbolo;
    estrategias = D.estrategias.filter((r) => r.instrumento_id === MERCADO);
    escolhida = 0;
    try { localStorage.setItem('sindicato.mercado', MERCADO); } catch (e) { /* sem armazenamento: tudo bem */ }
  }

  function imposto(e) {
    if (!e.imposto) return null;
    const ir = e.imposto;
    const pt = ir.por_tipo || {};
    return h('div', { class: 'cartao', style: 'margin-top:16px' },
      h('p', null, h('strong', { text: `Depois do IR: ${usd(ir.lucro_depois_do_ir)}` }), ` (imposto estimado de ${usd(ir.imposto)})`),
      h('p', { class: 'muted pequeno', text: `Day trade paga 20% e swing trade (de um dia para o outro) paga 15%, apurado por mês e descontando prejuízos anteriores. Aqui: day trade ${usd(pt.day_trade || 0)}, swing trade ${usd(pt.swing_trade || 0)}. É estimativa: o DARF de verdade pode dar diferente.` }));
  }

  function seletorEstrategias(aoEscolher) {
    return h('div', { class: 'seletor', role: 'group', 'aria-label': 'Escolher estratégia' },
      estrategias.map((r, i) => h('button', {
        class: 'chip', type: 'button', 'aria-pressed': String(i === escolhida),
        text: rotuloVersao(r),
        onclick: () => { escolhida = i; aoEscolher(); },
      })));
  }

  const SECOES = {
    resumo: {
      titulo: 'Resumo',
      render() {
        const r = { ...D.resumo, ...D.por_mercado[MERCADO] };
        const titulo = r.estrategias_avaliadas === 0
          ? 'Nenhuma estratégia avaliada ainda'
          : r.aprovadas === 0
            ? `Nenhuma estratégia passou no teste da honestidade (0 de ${r.estrategias_avaliadas})`
            : `${r.aprovadas} de ${r.estrategias_avaliadas} estratégias passaram no teste da honestidade`;
        return [
          h('h1', { text: titulo }),
          h('p', { class: 'lead', text: `${M().nome}. ` + 'Cada estratégia foi testada de 2010 a 2020 com custos reais e comparada com centenas de versões que entram no sorteio (coin flip). Só passa quem ganha da sorte mesmo contando todas as tentativas.' }),
          h('div', { class: 'numeros' },
            h('div', { class: 'numero' }, h('strong', { text: num(r.versoes_testadas) }), h('span', { text: 'versões testadas (diário)' })),
            h('div', { class: 'numero numero--moeda' }, h('strong', { text: num(r.rodadas_coin_flip) }), h('span', { text: `rodadas de coin flip (${num(r.moedas_jogadas)} moedas jogadas)` })),
            h('div', { class: 'numero' }, h('strong', { text: num(r.trades_backtest) }), h('span', { text: 'trades no backtest' })),
            h('div', { class: 'numero' }, h('strong', { text: num(r.aberturas_cego) }), h('span', { text: 'vezes que o teste cego (2021+) foi aberto' })),
            h('div', { class: 'numero' }, h('strong', { text: num(r.trades_vendedor) }), h('span', { text: 'trades no simulado ao vivo' })),
            h('div', { class: 'numero' }, h('strong', { text: num(r.avisos) }), h('span', { text: r.discord_configurado ? 'avisos enviados ao Discord' : 'avisos (Discord ainda não ligado)' })),
          ),
          h('h2', { text: 'Placar das estratégias' }),
          estrategias.length
            ? h('ul', { class: 'placar' }, estrategias.map((e) => h('li', null,
                h('span', { class: 'nome', text: `${rotuloVersao(e)} · ${e.periodo}` }),
                selo(e.veredito.aprovada),
                h('span', { class: 'detalhe', text: `${usd(e.metricas.lucro_liquido)} em ${num(e.metricas.trades)} trades${e.imposto ? ` (${usd(e.imposto.lucro_depois_do_ir)} depois do IR)` : ''} · ${e.coin_flip.sorteios_que_fizeram_melhor} de ${e.coin_flip.rodadas} sorteios fizeram igual ou melhor · comprar e segurar: ${usd(e.comprar_e_segurar.lucro_liquido)}` }),
              )))
            : vazio('Ainda não há estratégias avaliadas neste mercado.', `python laboratorio.py avaliar --estrategia rompimento${flag()}`),
          h('p', { class: 'nota', text: `Instrumento: ${M().descricao}. Custos por lado: corretagem e taxas ${usd2(M().custos.comissao_por_lado)} + ${M().custos.slippage_ticks_por_lado} tick de slippage. Limite: gráfico diário (dados grátis); não mostra o que acontece dentro do dia.${MERCADO === 'win' ? ' O Yahoo não tem o contrato WIN: o teste usa o índice Ibovespa, que o WIN acompanha de perto.' : ''}` }),
        ];
      },
    },

    estrategias: {
      titulo: 'Estratégias',
      render(redesenhar) {
        if (!estrategias.length) return [h('h1', { text: 'Estratégias' }), vazio('Nenhuma estratégia avaliada neste mercado.', `python laboratorio.py avaliar --estrategia rompimento${flag()}`)];
        const e = estrategias[escolhida];
        const trades = e.trades.slice().reverse();
        return [
          h('h1', { text: rotuloVersao(e) }),
          h('p', { class: 'lead', text: `Período ${e.periodo} (${data(e.de)} a ${data(e.ate)}) · ${e.instrumento} · versão nº ${e.versao} do diário` }),
          seletorEstrategias(redesenhar),
          h('div', { class: 'cartao', style: 'margin-top:16px' },
            h('p', null, selo(e.veredito.aprovada)),
            h('ul', { class: 'motivos' }, e.veredito.motivos.map((m) => h('li', { text: m }))),
            metricas(e.metricas),
          ),
          imposto(e),
          h('h2', { text: 'Patrimônio ao longo do tempo' }),
          h('div', { class: 'cartao' }, graficoLinhas([
            { nome: 'Estratégia (1 contrato)', cor: '#1f4fbf', pontos: e.curva, grossa: true },
            { nome: 'Comprar e segurar (1 contrato)', cor: '#8a93a0', pontos: e.curva_comprar_e_segurar, tracejado: true },
          ], { rotulo: `Patrimônio da estratégia termina em ${usd(e.metricas.lucro_liquido)}; comprar e segurar termina em ${usd(e.comprar_e_segurar.lucro_liquido)}` })),
          h('h2', { text: 'Monte Carlo: e se os trades viessem em outra ordem?' }),
          e.monte_carlo.rodadas
            ? h('div', { class: 'cartao' }, h('p', { text: `Em ${num(e.monte_carlo.rodadas)} sorteios da sequência de trades: a pior queda provável (95% dos casos) é ${usd(e.monte_carlo.drawdown_p95)}; a chance de passar do limite de ${usd(M().risco.limite_drawdown_conta)} é ${num(e.monte_carlo.chance_estourar_limite_pct, 1)}%; a chance de terminar no prejuízo é ${num(e.monte_carlo.chance_terminar_no_prejuizo_pct, 1)}%.` }))
            : vazio('Sem trades para sortear.'),
          h('h2', { text: `Todos os trades (${trades.length})` }),
          trades.length ? tabela([
            { titulo: 'Entrada', valor: (t) => data(t.entrada) },
            { titulo: 'Saída', valor: (t) => data(t.saida) },
            { titulo: 'Instrumento', valor: (t) => t.instrumento },
            { titulo: 'Direção', valor: (t) => t.direcao },
            { titulo: 'Preço entrada', num: true, valor: (t) => num(t.preco_entrada, 2) },
            { titulo: 'Preço saída', num: true, valor: (t) => num(t.preco_saida, 2) },
            { titulo: 'Motivo', valor: (t) => MOTIVO[t.motivo] || t.motivo },
            { titulo: 'Resultado', num: true, valor: (t) => usd2(t.resultado_usd), cor: (t) => t.resultado_usd },
          ], trades) : vazio('Nenhum trade neste período.'),
        ];
      },
    },

    coinflip: {
      titulo: 'Coin flip',
      render(redesenhar) {
        if (!estrategias.length) return [h('h1', { text: 'Coin flip' }), vazio('Nenhuma estratégia avaliada neste mercado.', `python laboratorio.py avaliar --estrategia rompimento${flag()}`)];
        const e = estrategias[escolhida];
        const cf = e.coin_flip;
        return [
          h('h1', { text: `${cf.sorteios_que_fizeram_melhor} de ${cf.rodadas} sorteios fizeram igual ou melhor que ${rotuloVersao(e)}` }),
          h('p', { class: 'lead', text: `Cada sorteio entra em dias escolhidos por "cara ou coroa", com o mesmo stop, o mesmo alvo, a mesma regra de saída, os mesmos custos e, em média, o mesmo número de trades (${num(cf.media_trades, 1)} contra ${num(e.metricas.trades)}). Ao todo foram ${num(cf.moedas_jogadas)} moedas jogadas para esta estratégia.` }),
          seletorEstrategias(redesenhar),
          h('div', { class: 'cartao', style: 'margin-top:16px' },
            histograma(cf.lucros, e.metricas.lucro_liquido || 0, { rotulo: `Distribuição do lucro de ${cf.rodadas} sorteios; a estratégia fez ${usd(e.metricas.lucro_liquido)}` }),
          ),
          h('dl', { class: 'metricas' },
            h('div', null, h('dt', { text: 'Lucro da estratégia' }), h('dd', { class: classeValor(e.metricas.lucro_liquido), text: usd(e.metricas.lucro_liquido) })),
            h('div', null, h('dt', { text: 'Lucro médio da sorte' }), h('dd', { text: usd(cf.media_lucro) })),
            h('div', null, h('dt', { text: 'Chance de ser sorte (p)' }), h('dd', { text: `${num(e.veredito.p_valor * 100, 1)}%` })),
            h('div', null, h('dt', { text: `Ajustado por ${e.veredito.versoes_testadas} versões` }), h('dd', { text: `${num(e.veredito.p_ajustado * 100, 1)}%` })),
          ),
          h('p', { class: 'nota', text: 'Para passar, a sorte precisa fazer igual ou melhor em menos de 5% das vezes, já multiplicando pelo número de versões testadas no diário. Quanto mais versões você testa, mais difícil fica passar: é o que impede de "achar" uma estratégia só por insistência.' }),
        ];
      },
    },

    previsao: {
      titulo: 'Previsão',
      render() {
        const lista = D.previsoes || [];
        if (!lista.length) return [h('h1', { text: 'Previsão' }), vazio('Nenhuma previsão feita ainda.', 'python laboratorio.py prever PETR4.SA AAPL ^NDX')];
        const ganhou = lista.filter((p) => p.acerto_treino.ganhou_do_sempre_sobe).length;
        return [
          h('h1', { text: `O previsor ganhou do chute "sempre sobe" em ${ganhou} de ${lista.length} ativos` }),
          h('p', { class: 'lead', text: 'Para cada ativo: a chance de o próximo fechamento ser maior que o último, e quanto o modelo acertou no passado aprendendo só com os anos anteriores. Ninguém prevê a direção do dia seguinte de forma confiável; esta aba mostra o tamanho real da dúvida.' }),
          tabela([
            { titulo: 'Ativo', valor: (p) => p.ticker },
            { titulo: 'Último fechamento', valor: (p) => `${num(p.amanha.fechamento, 2)} (${data(p.amanha.base)})` },
            { titulo: 'Chance de subir', num: true, valor: (p) => `${num(p.amanha.chance_subir_pct, 1)}%` },
            { titulo: 'Leitura', valor: (p) => p.amanha.leitura },
            { titulo: 'Acerto no passado', num: true, valor: (p) => `${num(p.acerto_treino.acerto_pct, 1)}% ± ${num(p.acerto_treino.margem_pct, 1)}` },
            { titulo: 'Chute "sempre sobe"', num: true, valor: (p) => `${num(p.acerto_treino.chute_sempre_sobe_pct, 1)}%` },
            { titulo: 'Ganhou do chute?', valor: (p) => (p.acerto_treino.ganhou_do_sempre_sobe ? 'sim' : 'não') },
            { titulo: 'Acerto 2021+ (cego)', num: true, valor: (p) => (p.acerto_cego ? `${num(p.acerto_cego.acerto_pct, 1)}%` : 'não aberto') },
          ], lista, { rotulo: 'Previsões por ativo' }),
          h('p', { class: 'nota', text: '"Ganhou do chute" só conta se o acerto, já descontada a margem de erro, ficou acima de simplesmente chutar "sobe" todo dia. Acerto de 52% num ativo que sobe 53% dos dias não é previsão: é o mercado subindo.' }),
        ];
      },
    },

    sindicato: {
      titulo: 'Sindicato',
      render() {
        const sd = (D.sindicatos[MERCADO] || {}).treino;
        if (!sd) return [h('h1', { text: 'Sindicato' }), vazio('Ainda não foi montado neste mercado.', `python laboratorio.py sindicato${flag()}`)];
        const algumaReprovada = sd.membros.some((m) => !m.aprovada);
        const cores = ['#1f4fbf', '#2e9e5b', '#b07a10', '#8a4fbf', '#d64545'];
        const nomes = sd.correlacao.nomes;
        return [
          h('h1', { text: `Juntas: ${usd(sd.combinado.lucro_liquido)} com pior queda de ${usd(sd.combinado.drawdown_max_usd)}` }),
          h('p', { class: 'lead', text: 'O Sindicato opera várias estratégias ao mesmo tempo, 1 contrato cada. Estratégias diferentes tendem a perder em dias diferentes.' }),
          algumaReprovada ? h('p', { class: 'nota', text: 'Demonstração: este sindicato usa estratégias que REPROVARAM no coin flip, só para mostrar como a junção funciona. Na vida real ele só aceita aprovadas.' }) : null,
          h('div', { class: 'cartao', style: 'margin-top:16px' }, graficoLinhas([
            { nome: 'Sindicato (todas juntas)', cor: '#121820', pontos: sd.curva, grossa: true },
            ...Object.entries(sd.curvas_membros).map(([n, p], i) => ({ nome: nome(n), cor: cores[i % cores.length], pontos: p })),
          ], { rotulo: 'Patrimônio do sindicato e de cada estratégia' })),
          h('h2', { text: 'Membros' }),
          tabela([
            { titulo: 'Estratégia', valor: (m) => nome(m.nome) },
            { titulo: 'Situação', valor: (m) => (m.aprovada ? 'aprovada' : 'reprovada (demonstração)') },
            { titulo: 'Trades', num: true, valor: (m) => num(m.metricas.trades) },
            { titulo: 'Lucro', num: true, valor: (m) => usd(m.metricas.lucro_liquido), cor: (m) => m.metricas.lucro_liquido },
            { titulo: 'Pior queda', num: true, valor: (m) => usd(m.metricas.drawdown_max_usd) },
          ], sd.membros),
          h('h2', { text: 'Correlação dos resultados diários' }),
          h('p', { class: 'muted pequeno', text: 'Perto de 1 = ganham e perdem juntas (só duplica o risco). Perto de 0 ou negativa = se complementam (bom).' }),
          tabela([{ titulo: 'Estratégia', valor: (l) => nome(l.nome) }, ...nomes.map((n, j) => ({ titulo: nome(n), num: true, valor: (l) => num(l.valores[j], 2) }))],
            nomes.map((n, i) => ({ nome: n, valores: sd.correlacao.valores[i] })), { rotulo: 'Correlação entre as estratégias' }),
        ];
      },
    },

    vendedor: {
      titulo: 'Vendedor (ao vivo)',
      render() {
        const v = D.vendedores[MERCADO] || { estado: null, trades: [] };
        const est = v.estado;
        const hr = M().mercado || {};
        const fonte = MERCADO === 'win' ? 'do índice Bovespa (o Yahoo não tem o WIN), no horário da B3' : 'do futuro do Nasdaq, no horário de Nova York';
        const partes = [h('h1', { text: 'O Vendedor: simulado ao vivo' }),
          h('p', { class: 'lead', text: `Roda as estratégias em dias novos com o preço ${fonte} (${hr.abre || ''}–${hr.fecha || ''}, atrasado e grátis). Entra e sai só no papel, aplica a trava de perda diária e avisa tudo no Discord.` })];
        if (!est) {
          partes.push(vazio('O Vendedor deste mercado ainda não rodou. Para ligar (fica rodando; Ctrl+C para sair):', `python laboratorio.py vendedor --demonstracao rompimento${flag()}`));
        } else {
          const situacao = est.desligado ? 'desligado pelo botão de parar' : est.bloqueado_ate === est.dia ? 'travado hoje (bateu a perda máxima)' : 'pronto para operar';
          partes.push(h('div', { class: 'numeros' },
            h('div', { class: 'numero numero--texto' }, h('strong', { text: situacao }), h('span', { text: `dia ${data(est.dia)}` })),
            h('div', { class: 'numero' }, h('strong', { class: classeValor(est.realizado_hoje), text: usd2(est.realizado_hoje) }), h('span', { text: 'resultado do dia' })),
            h('div', { class: 'numero' }, h('strong', { text: num(Object.keys(est.posicoes).length) }), h('span', { text: 'posições abertas' })),
            h('div', { class: 'numero numero--texto' }, h('strong', { text: Object.keys(est.pendentes_entrada).map(nome).join(', ') || 'nenhuma' }), h('span', { text: 'entradas marcadas para a próxima abertura' })),
          ));
          const abertas = Object.entries(est.posicoes);
          if (abertas.length) {
            partes.push(h('h2', { text: 'Posições abertas (no papel)' }), tabela([
              { titulo: 'Estratégia', valor: (p) => nome(p[0]) },
              { titulo: 'Direção', valor: (p) => (p[1].direcao === 1 ? 'compra' : 'venda') },
              { titulo: 'Entrada', valor: (p) => p[1].quando.replace('T', ' ') },
              { titulo: 'Preço', num: true, valor: (p) => num(p[1].entrada, 2) },
              { titulo: 'Stop', num: true, valor: (p) => num(p[1].stop, 2) },
              { titulo: 'Alvo', num: true, valor: (p) => num(p[1].alvo, 2) },
            ], abertas));
          }
        }
        partes.push(h('h2', { text: `Trades do simulado (${v.trades.length})` }));
        partes.push(v.trades.length ? tabela([
          { titulo: 'Entrada', valor: (t) => t.entrada_em.replace('T', ' ') },
          { titulo: 'Saída', valor: (t) => t.saida_em.replace('T', ' ') },
          { titulo: 'Estratégia', valor: (t) => nome(t.estrategia) },
          { titulo: 'Instrumento', valor: (t) => t.instrumento },
          { titulo: 'Direção', valor: (t) => t.direcao },
          { titulo: 'Motivo', valor: (t) => MOTIVO[t.motivo] || t.motivo },
          { titulo: 'Resultado', num: true, valor: (t) => usd2(t.resultado_usd), cor: (t) => t.resultado_usd },
        ], v.trades.slice().reverse()) : vazio('Nenhum trade simulado ainda. Os trades aparecem aqui conforme o Vendedor opera nos dias de mercado.'));

        const COR = { compra: '#2e9e5b', venda: '#d64545', info: '#2f6fde', relatorio: '#2f6fde', alerta: '#8b0000' };
        const SITUACAO = { enviado: 'enviado ao Discord', na_fila: 'na fila (sem internet)', so_local: 'só no painel' };
        const avisos = D.avisos || [];
        partes.push(h('h2', { text: `Avisos de todos os mercados (${avisos.length})` }));
        partes.push(avisos.length ? h('ul', { class: 'feed' }, avisos.slice().reverse().map((a) => h('li', null,
          h('span', { class: 'ponto', style: `background:${COR[a.tipo] || '#2f6fde'}`, 'aria-hidden': 'true' }),
          h('span', { class: 'titulo', text: a.titulo }),
          h('span', { class: 'quando', text: `${a.quando.slice(0, 16).replace('T', ' ')} UTC · ${SITUACAO[a.situacao] || a.situacao}` }),
          Object.keys(a.campos || {}).length ? h('span', { class: 'campos', text: Object.entries(a.campos).map(([k, x]) => `${k}: ${x}`).join(' · ') }) : null,
        ))) : vazio('Nenhum aviso ainda.'));
        return partes;
      },
    },

    diario: {
      titulo: 'Diário de pesquisa',
      render() {
        const linhas = D.diario.slice().reverse();
        const TIPO = { teste: 'teste rápido', avaliacao: 'avaliação completa', abriu_cego: 'abriu o teste cego' };
        return [
          h('h1', { text: `${num(D.resumo.versoes_testadas)} versões testadas, nada apagado` }),
          h('p', { class: 'lead', text: 'Toda tentativa fica registrada, inclusive as que deram errado. É esse número que entra no ajuste do coin flip: quem testa mil coisas acha "vencedoras" por acaso.' }),
          linhas.length ? tabela([
            { titulo: 'Nº', num: true, valor: (r) => r.n },
            { titulo: 'Quando (UTC)', valor: (r) => r.quando.slice(0, 16).replace('T', ' ') },
            { titulo: 'Tipo', valor: (r) => TIPO[r.tipo] || r.tipo },
            { titulo: 'Estratégia', valor: (r) => (r.estrategia ? nome(r.estrategia) : r.motivo || '—') },
            { titulo: 'Período', valor: (r) => r.periodo || '—' },
            { titulo: 'Trades', num: true, valor: (r) => num(r.trades) },
            { titulo: 'Mercado', valor: (r) => (r.instrumento && D.mercados[r.instrumento] ? D.mercados[r.instrumento].nome.split(' (')[0] : '—') },
            { titulo: 'Lucro', num: true, valor: (r) => usd(r.lucro, r.instrumento && D.mercados[r.instrumento] ? D.mercados[r.instrumento].simbolo : 'US$'), cor: (r) => r.lucro },
            { titulo: 'Veredito', valor: (r) => (r.aprovada == null ? '—' : r.aprovada ? 'aprovada' : 'reprovada') },
          ], linhas, { porPagina: 50 }) : vazio('O diário está vazio.'),
        ];
      },
    },
  };

  // ---------- abas ----------
  const abas = document.getElementById('abas');
  const ordem = Object.keys(SECOES);

  function abrir(id, focar) {
    if (!SECOES[id]) id = 'resumo';
    for (const b of abas.children) b.setAttribute('aria-selected', String(b.dataset.id === id));
    const redesenhar = () => abrir(id, false);
    main.replaceChildren(h('section', { class: 'secao', role: 'tabpanel', 'aria-label': SECOES[id].titulo }, SECOES[id].render(redesenhar)));
    document.title = `${SECOES[id].titulo} · O Sindicato`;
    if (location.hash.slice(1) !== id) history.replaceState(null, '', `#${id}`);
    if (focar) main.focus({ preventScroll: true });
  }

  if (!D) {
    main.replaceChildren(vazio('Os dados do painel ainda não foram gerados. Na pasta do projeto, rode:', 'python laboratorio.py painel'));
    return;
  }

  let salvo = null;
  try { salvo = localStorage.getItem('sindicato.mercado'); } catch (e) { /* sem armazenamento */ }
  escolherMercado(salvo || 'mnq');
  const botoesMercado = Object.entries(D.mercados).map(([id, m]) => h('button', {
    class: 'chip', type: 'button', 'aria-pressed': String(id === MERCADO), 'data-id': id,
    text: `${m.nome.split(' (')[0]} (${m.simbolo})`,
    onclick: () => {
      escolherMercado(id);
      for (const b of botoesMercado) b.setAttribute('aria-pressed', String(b.dataset.id === MERCADO));
      abrir(location.hash.slice(1) || 'resumo', false);
    },
  }));
  document.getElementById('mercados').replaceChildren(h('span', { class: 'mercados__rotulo', text: 'Mercado' }), ...botoesMercado);

  document.getElementById('gerado').textContent = `Atualizado em ${new Date(D.gerado_em).toLocaleString('pt-BR')}`;
  for (const id of ordem) {
    abas.append(h('button', { class: 'aba', type: 'button', role: 'tab', 'data-id': id, text: SECOES[id].titulo, onclick: () => abrir(id, true) }));
  }
  abas.addEventListener('keydown', (e) => {
    const atual = ordem.indexOf(location.hash.slice(1) || 'resumo');
    const passo = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!passo) return;
    const proximo = ordem[(atual + passo + ordem.length) % ordem.length];
    abrir(proximo, false);
    abas.querySelector(`[data-id="${proximo}"]`).focus();
  });
  abrir(location.hash.slice(1) || 'resumo', false);
})();
