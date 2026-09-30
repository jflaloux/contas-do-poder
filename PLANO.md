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
- [x] Governo federal: presidente, vice e ministros (salário, jetons, viagens) — Claude
- [x] Fotos do governo federal: Congresso ou Wikimedia Commons com crédito (45 de 71; o resto com iniciais) — Claude
- [x] Colegas e ranking numa seção só; detalhe dos gastos no contracheque; guia com o governo federal — Claude
- [ ] Judiciário: ministros do STF e dos tribunais superiores — próximo passo sugerido
- [ ] TCU; presidentes de estatais — depois
- [x] Vereadores, passo 1: a Câmara de cada cidade (custo, por habitante, vereadores eleitos, teto do salário) — Claude
- [x] Vereadores, passo 2a: São Paulo (capital), vereador por vereador: salário, verba do gabinete com fornecedores, equipe — Claude
- [x] Prefeitura de São Paulo: prefeito, vice, secretários e subprefeitos, mês a mês (folha nos dados abertos) — Claude
- [x] Vereadores, passo 2b: Fortaleza, Goiânia, Manaus, Natal e Recife, vereador por vereador (robô comum a várias cidades) — Claude
- [ ] Vereadores, passo 2c: as outras capitais. Parciais: Belo Horizonte, Curitiba, Salvador, João Pessoa, Porto Velho, Rio Branco, Palmas, Maceió. Bloqueiam acesso de fora do Brasil (o robô do GitHub roda nos EUA): Porto Alegre, Vitória, Cuiabá, Distrito Federal, São Luís. Muito difíceis: Rio, Florianópolis, Campo Grande, Teresina (a folha mostra CPF), Aracaju, Boa Vista, Belém, Macapá — Claude
- [ ] Capitais que bloqueiam o exterior: rodar o robô num computador no Brasil (runner próprio do GitHub no seu Mac ou num servidor brasileiro) — Jean-François decide
- [x] Prefeituras, robô comum (`coleta/prefeituras/`): São Paulo, Recife, Fortaleza, Vitória e Porto Alegre, prefeito, vice e secretários mês a mês pela folha — Claude
- [ ] Prefeituras, próximas: Curitiba (a exportação da folha dá erro), Natal, João Pessoa, Salvador, Rio, Campo Grande, Macapá. Belo Horizonte: o portal bloqueia robôs (WAF), não contornamos; só se a Prefeitura liberar ou publicar os dados abertos — Claude
- [x] Governadores, v1: salário (subsídio) do governador e do vice nos 27 estados, com a lei ou a fonte de cada valor, quem governou desde 2023 e se a folha abre (`dados/governadores/governadores.json`, mantido à mão) — Claude
- [ ] Governadores, v2: o mês a mês pela folha onde ela é aberta (AC, DF, ES, MG, PB, PR, PE, RO, RR, SC, SP) — Claude
- [ ] Governadores: achar as leis que faltam (AL, AP, GO, MA, RJ, SE só pela imprensa) — Claude, com ajuda de quem estiver no Brasil (portais bloqueiam o exterior)
- [ ] Vereadores de SP: fotos com licença confirmada por escrito pela Câmara; 13º e contracheque (só com CPF, não coletamos) — Jean-François
- [ ] Vereadores, passo 3: estados cujo tribunal de contas publica a folha — Claude

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
