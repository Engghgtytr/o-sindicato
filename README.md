# O Sindicato

Laboratório para testar estratégias de trading no **Nasdaq** com honestidade, inspirado no vídeo *"Claude Code Trading Bot: Full Step-by-Step Tutorial"*. **Nenhuma ordem real é enviada, nunca.** É um projeto de estudo e de portfólio; não é recomendação de investimento.

O que ele faz:

1. **Baixa dados grátis** (Yahoo Finance): 16 anos de gráfico diário do Nasdaq-100.
2. **Backtest que não mente**: entra no dia seguinte ao sinal, conta o stop quando stop e alvo cabem no mesmo dia, sai na abertura quando o preço "pula" o stop, cobra comissão e slippage em toda ordem. Resultado em dólar como 1 contrato micro (MNQ, US$ 2 por ponto).
3. **Teste cego trancado**: treino em 2010–2020; os anos de 2021 em diante só abrem com um motivo escrito, e cada abertura fica registrada.
4. **Coin flip**: 500 versões aleatórias com o mesmo stop, alvo, regra de saída, custos e número de trades. Também compara com "comprar e segurar" e faz um Monte Carlo do pior caminho.
5. **Diário de pesquisa** que nunca se apaga: o número de versões testadas entra no veredito (quem testa mil coisas acha "vencedoras" por acaso).
6. **Sindicato**: junta as estratégias aprovadas num portfólio.
7. **O Vendedor**: simulado ao vivo com o futuro do Nasdaq (grátis, atrasado), trava de perda diária, botão de parar, volta de onde parou se o PC reiniciar e avisa no **Discord**.
8. **Painel**: um app local com tudo o que o robô fez.

## Primeiro resultado

As 3 estratégias clássicas testadas (cruzamento de médias, rompimento de 20 dias, reversão IFR(2)) **reprovaram**: a sorte fez igual ou melhor em 32%, 82% e 36% das vezes. Nesse período, só comprar e segurar 1 micro teria rendido US$ 22 mil. É o laboratório funcionando: ele impediu de levar adiante três estratégias que pareciam lucrativas.

## Mini índice (WIN)

O laboratório também testa o **mini índice da B3** (`--mercado win`), em reais: R$ 0,20 por ponto, tick de 5 pontos, horário 10h–17h de Brasília e **estimativa do IR** (20% day trade, 15% swing, com compensação de prejuízo mês a mês). O Yahoo não tem o contrato WIN, então os testes usam o índice Ibovespa (`^BVSP`), que o WIN acompanha. A corretagem (R$ 0,50 por lado) é estimativa: confira a da sua corretora.

Resultado no treino (2010–2020): as 11 estratégias **reprovaram**. MACD (R$ 13.932) foi a única que ganhou do comprar e segurar (R$ 10.141), mas a sorte fez igual ou melhor em 6% das vezes e o risco de estourar o limite de perda passou de 98%.

## Como usar (Windows)

Atalhos de dois cliques na pasta:

| Arquivo | O que faz |
|---|---|
| `ABRIR O PAINEL.bat` | Atualiza e abre o app com tudo o que o robô fez |
| `LIGAR O VENDEDOR.bat` | Liga o simulado ao vivo (deixe a janela aberta no pregão: 10h30–17h de Brasília, varia com o horário de verão dos EUA) |
| `LIGAR O VENDEDOR (MINI INDICE).bat` | O mesmo simulado no mini índice (10h–17h de Brasília) |
| `PARAR O SINDICATO.bat` | Botão de emergência: fecha tudo no papel e desliga (todos os mercados) |

Pelo terminal (na pasta do projeto):

```bash
.venv\Scripts\python.exe laboratorio.py baixar                     # dados grátis
.venv\Scripts\python.exe laboratorio.py avaliar --estrategia rompimento --param dias=55
.venv\Scripts\python.exe laboratorio.py avaliar --estrategia rompimento --periodo cego --motivo "versão final"
.venv\Scripts\python.exe laboratorio.py sindicato
.venv\Scripts\python.exe laboratorio.py vendedor --demonstracao rompimento
.venv\Scripts\python.exe laboratorio.py avaliar --estrategia macd --mercado win   # mini índice
.venv\Scripts\python.exe laboratorio.py painel
.venv\Scripts\python.exe -m pytest                                 # testes
```

Instalar do zero: `python -m venv .venv` e depois `.venv\Scripts\python.exe -m pip install -r requirements.txt`.

## Ligar o Discord (grátis)

1. No seu servidor do Discord, crie um canal (ex.: `#sindicato`).
2. Configurações do canal → **Integrações** → **Webhooks** → **Novo webhook** → **Copiar URL do webhook**.
3. Copie `.env.example` para `.env` e cole a URL em `DISCORD_WEBHOOK_URL`.
4. Teste: `.venv\Scripts\python.exe laboratorio.py discord-teste`.

O `.env` fica fora do Git: quem tem a URL do webhook consegue mandar mensagens no seu canal.

## Limitações (escritas em todo relatório)

- **Gráfico diário, não 1 minuto.** Dados de 1 minuto de graça só existem para os últimos ~8 dias. Estratégias de day trade de verdade precisariam de dados pagos.
- **Índice, não futuro.** O backtest usa o índice Nasdaq-100 (sem os "saltos" de vencimento dos contratos); o futuro negocia quase 24 h e tem custo de carregamento.
- **Yahoo Finance não é oficial**: pode mudar ou limitar a qualquer hora, e o preço ao vivo vem com atraso.
- **Dinheiro real** (mesas proprietárias, corretoras de futuros) exige 18 anos e não faz parte deste projeto.
