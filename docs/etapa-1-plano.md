# O Sindicato: plano (etapa 1)

Laboratório para testar estratégias de trading no **Nasdaq** com honestidade: custos reais, teste em anos nunca vistos, comparação com a sorte (coin flip) e um simulado ao vivo que avisa no Discord. **Nenhuma ordem real, nenhum dinheiro real.** Projeto de estudo e de portfólio; não é recomendação de investimento.

Baseado no vídeo "Claude Code Trading Bot: Full Step-by-Step Tutorial" (transcrição na pasta do portfólio), com as correções da análise `O Sindicato - análise do plano.md`.

## Decisões

| Item | Decisão | Por quê |
|---|---|---|
| Dados | **Grátis** (yfinance) | Sem gastar antes de saber se funciona |
| Gráfico | **Diário** para o teste de 2010–2026 | É o único com 16 anos de graça. 1 minuto só tem 8 dias |
| Série do backtest | Índice **Nasdaq-100 (^NDX)** em pontos | Sem "emendas" de vencimento de contrato (o futuro contínuo grátis tem saltos a cada 3 meses) |
| Resultado em dólar | Como **1 contrato micro (MNQ)**: US$ 2 por ponto, tick de 0,25 | É o que o vídeo opera |
| Custos | Comissão por lado + **1 tick de slippage por lado** (ajustável) | Sem custo, o backtest mente |
| Treino / teste cego | Treino **2010–2020**, cego **2021→hoje** | Igual ao vídeo |
| Simulado | "O Vendedor": roda no horário do mercado, usa o futuro **NQ=F** de 1–5 min (atrasado, grátis), registra os trades e avisa no Discord | Prova em dias novos, sem dinheiro |
| Linguagem | Python com pandas, numpy, pyarrow, requests; testes com pytest | Leve e padrão em finanças |

**Limitação que fica escrita em todo relatório:** índice diário ≠ futuro de 1 minuto. O futuro negocia quase 24 h e tem custo de carregamento; o gráfico diário não mostra o que aconteceu dentro do dia. Estratégias de day trade de verdade só poderiam ser testadas com dados de 1 minuto (pagos).

## Etapas

| Etapa | Entrega | O teste que prova |
|---|---|---|
| 1 | Este plano | — |
| 2 | **Dados**: baixar, limpar, salvar em `.parquet`, atualizar só o que falta | Sem datas repetidas, sem linhas vazias, preços coerentes (mínima ≤ abertura/fechamento ≤ máxima) |
| 3 | **Motor de backtest**: estratégia como classe; entra na abertura do **dia seguinte** ao sinal; stop e alvo; se o stop e o alvo cabem no mesmo dia, conta o **stop** (pior caso); se abre além do stop (gap), sai na abertura; custos em toda ordem | Testes com preços inventados de resultado conhecido |
| 4 | **Cofre do teste cego + diário de pesquisa**: o motor recusa os anos 2021+ no modo treino; toda versão testada vira uma linha que nunca se apaga; o relatório mostra quantas versões já foram testadas | Tentar ler 2021 no treino dá erro; o diário só cresce |
| 5 | **Coin flip**: 500 versões aleatórias com o mesmo stop, alvo e número de trades; também compara com "comprar e segurar" e faz o Monte Carlo do pior caminho | Uma estratégia aleatória tem que reprovar quase sempre |
| 6 | **Sindicato**: junta as aprovadas num portfólio e mostra se o pior momento fica menor | — |
| 7 | **Relatório** em HTML local (sem CDN): curva de patrimônio, drawdown, nuvem do coin flip | — |
| 8 | **O Vendedor** (simulado ao vivo) + **avisos no Discord** (chave no `.env`, fila para reenviar se a internet cair) + trava diária + botão de parar | Simular um dia ruim: ele precisa parar sozinho |

## Regras do projeto

- Nunca enviar ordem para corretora. Não existe código de ordem real neste projeto.
- Chaves (webhook do Discord) só no `.env`, que fica fora do Git.
- Toda estratégia testada vai para o diário, inclusive as que deram errado.
- "Bom demais para ser verdade" é tratado como bug até provar o contrário.
