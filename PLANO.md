# Plano de ação — Contas do Poder

## Objetivo da versão 1

Um site simples, feito para celular, onde qualquer pessoa busca um político federal
(513 deputados e 81 senadores) e entende em 30 segundos:

- **quanto ele ganha** (salário e auxílios pessoais);
- **quanto custa o mandato** (cota parlamentar e verba de gabinete);
- **como ele se compara** com os outros, também em salários mínimos.

Cada número tem link para a fonte oficial.

## Princípios

1. Separar o custo do parlamentar (o que vai para o bolso + as despesas dele) da equipe do gabinete
   (dinheiro que vai para outras pessoas, com número de pessoas e média por pessoa).
2. Toda cifra com fonte e data da última atualização.
3. Linguagem neutra: mostrar fatos, sem adjetivos.
4. Comparações justas: a cota é comparada em % do limite de cada estado.

## Calendário (início: 29/09/2026)

| Fase | Período | Entrega |
|---|---|---|
| 1. Dados | até ~13/10 | Robôs de coleta e base padronizada |
| 2. Protótipo | até ~27/10 | Site navegável com dados reais |
| 3. Testes e confiabilidade | até ~10/11 | Metodologia, testes com pessoas, revisão jurídica |
| 4. Lançamento | meados de nov/2026 | "Balanço 2023–2026: quanto custou cada deputado e senador" |
| 5. Nova legislatura e expansão | a partir de 01/02/2027 | Troca para os eleitos; depois estaduais, vereadores das capitais, busca por CEP |

## Fase 1 — Dados ✔ (29/09/2026)

- [x] Câmara: lista de deputados (API) — 648 que exerceram mandato, 513 em exercício
- [x] Câmara: cota parlamentar (arquivos anuais) + total mensal do site oficial (lacuna de passagens desde ago/2025)
- [x] Câmara: salário e verba de gabinete (páginas de cada deputado)
- [x] Câmara: auxílio-moradia e imóvel funcional
- [x] Senado: lista de senadores e períodos de exercício — 105 exerceram, 81 em exercício
- [x] Senado: folha de pagamento (salário, 13º, auxílios, ajuda de custo, diárias)
- [x] Senado: cota (CEAPS) e outros gastos do mandato
- [x] Senado: custo dos assessores do gabinete (estimativa)
- [x] Base padronizada: pessoa · ano · mês · grupo · categoria · valor
- [x] Conferência automática com os sites oficiais (`python3 coletar.py conferir`)
- [ ] Conferência manual: você abre 5 perfis no site oficial e compara com a base — Você

### Fase 1b — pendências de dados (antes do lançamento)

- [ ] Câmara: 13º salário e ajuda de custo dos deputados — Claude
- [ ] Câmara: diárias de viagens oficiais — Claude
- [ ] Câmara: limites históricos da cota por estado (2023–2025) — Claude
- [ ] Senado: validar a estimativa de custo dos assessores (ex.: pedir via LAI o custo por gabinete) — Você e Claude

## Fase 2 — Protótipo (em andamento)

- [x] Telas: Buscar, Perfil (com "contracheque médio"), Ranking, Comparar, Entenda — Claude
- [x] Site estático gerado a partir da base, celular primeiro, tema claro e escuro — Claude
- [x] Gráficos: mês a mês, comparação com os colegas, destino da cota — Claude
- [x] Botões de WhatsApp e "copiar texto" — Claude
- [ ] Você navegar pelo protótipo e anotar o que confunde ou falta — Você
- [x] Nome: Contas do Poder, um projeto Contas do Brasil — Você
- [x] Navegação no estilo do Contas do Brasil, com cores próprias (índigo e framboesa) — Claude
- [x] Tudo por mês: valores anuais divididos pelos meses (com aviso ≈) e cota por tipo em R$ por mês e % — Claude
- [x] Imagem para o status do WhatsApp com a foto do parlamentar (como no Contas do Brasil) — Claude
- [x] Guardar as fotos no próprio site (`site/fotos/`) — Claude
- [x] Google Analytics com eventos e prévia do link (`og.png`) — Claude
- [ ] Página própria por político para a prévia do link no WhatsApp (foto, nome, valor) — Claude

## Fase 3 — Testes e confiabilidade

- [ ] Página "Como calculamos" — Claude rascunha, você revisa
- [ ] Testar com 5 a 10 pessoas não técnicas: acham o político delas e entendem em 30 s? — Você
- [ ] Uma conversa com advogado (linguagem, LGPD) — Você
- [ ] Canal para pedir correção de dados — Claude

## Fase 4 — Lançamento

- [ ] Registrar contasdopoder.com e contasdopoder.com.br — Você
- [x] Código no GitHub (público): jflaloux/contas-do-poder — Você e Claude
- [x] Atualização automática semanal (GitHub Actions), com trava se a conferência falhar — Claude
- [ ] Primeira execução no GitHub: ver se os sites do governo aceitam os servidores do GitHub — Você (botão "Run workflow")
- [ ] Cloudflare Pages conectado ao repositório (pasta `site`) e domínio contasdopoder.com — Você
- [ ] Divulgação: jornalistas de dados, perfis de transparência, grupos — Você

## Tecnologia

- Robôs de coleta em Python.
- Site estático simples (HTML, CSS e JavaScript, sem framework) lendo os dados em JSON.
  Mais fácil de manter e hospedar do que o Astro que estava no plano; se precisar, migramos depois.
- Código versionado com Git.

## Custos

- Domínio .com.br: cerca de R$ 40 por ano.
- Hospedagem: R$ 0 no início.

## Riscos e como lidar

| Risco | Como lidar |
|---|---|
| A Câmara muda o layout da página e o robô quebra | Alerta automático e conferência mensal |
| Número errado ao lado de um nome | Conferência manual, fonte em tudo, canal de correção |
| Troca de legislatura em 01/02/2027 | Base organizada por mandato e período desde o início |
| Projeto parar por falta de tempo ou dinheiro (como o Excelências, em 2017) | Custo perto de zero e atualização automática |

## Decisões pendentes

- Você quer mexer no código ou prefere cuidar só das decisões e da divulgação?
