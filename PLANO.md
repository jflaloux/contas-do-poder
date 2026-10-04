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

- [x] Câmara: 13º, férias, acertos, ajuda de custo e diárias dos deputados, pelo contracheque detalhado de cada mês
  (exceção ao robots.txt; leitura do mais recente para o mais antigo) — Claude
- [x] Câmara: contracheques lidos de fev/2023 a set/2026 (23.781; depois só os meses novos) — Claude
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
- [x] Página própria por político, estado e cidade (endereço fixo, título, descrição e resumo para o Google e o WhatsApp) — Claude
- [x] Governo federal: presidente, vice e ministros (salário, jetons, viagens) — Claude
- [x] Fotos do governo federal: Congresso ou Wikimedia Commons com crédito (62 de 71, 17 escolhidas à mão em
  `dados/referencia/fotos_governo.json`; faltam 9 sem foto de licença livre) — Claude
- [x] Colegas e ranking numa seção só; detalhe dos gastos no contracheque; guia com o governo federal — Claude
- [x] Judiciário, prova de conceito: levantamento do STF, STJ, TST, STM, TSE, CNJ, TJs e PGR, com amostra conferida (`dados/referencia/judiciario.json`) — Claude
- [x] Judiciário, passo 1: ministros do STF, STJ, TST, STM e TSE, conselheiros do CNJ e o PGR, mês a mês desde jan/2025 (STJ, TST, CNJ e PGR pela fonte oficial; STF, STM e TSE pelo DadosJusBr), em dados/judiciario/ e site/dados/judiciario.json — Claude
- [x] Judiciário no site: página /judiciario e página de pessoa — Agente de Site
- [x] Judiciário: STJ e PGR vêm do DadosJusBr nos meses em que o robô oficial falhar (TST e CNJ não: o DadosJusBr não bate com a fonte) — Agente de Dados
- [ ] Judiciário: exceção ao robots.txt da consulta do STF (egesp-portal) e do STM (rem_web), depois da conversa com o advogado — Jean-François
- [x] Contato com o DadosJusBr (Transparência Brasil): observações sobre os dados e propostas de troca (02/10/2026) — Jean-François
- [ ] TCU; presidentes de estatais — depois
- [x] Vereadores, passo 1: a Câmara de cada cidade (custo, por habitante, vereadores eleitos, teto do salário) — Claude
- [x] Vereadores, passo 2a: São Paulo (capital), vereador por vereador: salário, verba do gabinete com fornecedores, equipe — Claude
- [x] Prefeitura de São Paulo: prefeito, vice, secretários e subprefeitos, mês a mês (folha nos dados abertos) — Claude
- [x] Vereadores, passo 2b: Fortaleza, Goiânia, Manaus, Natal e Recife, vereador por vereador (robô comum a várias cidades) — Claude
- [x] Vereadores, passo 2c: Rio de Janeiro, Belo Horizonte, Porto Alegre, Maceió e São Luís (robôs rodam no Mac, no Brasil) — Claude
- [x] Vereadores, passo 2d: Aracaju (folha) e Boa Vista (subsídio da resolução e verba por tipo) — Claude
- [ ] Vereadores, passo 2e: Curitiba (Betha Cloud) e Palmas (NúcleoGov e prodata, em JavaScript). Teresina e João Pessoa: as Câmaras
  mudaram de endereço (teresina.pi.leg.br, joaopessoa.pb.leg.br); não há proibição no robots.txt (o "bloqueio" era o endereço antigo fora do ar). Salvador, Belém, Campo Grande, Florianópolis, Cuiabá e Vitória só com autorização da Câmara ou pedido pela LAI (robots.txt ou CAPTCHA)
- [x] Capitais e estados que bloqueiam o exterior: rodada semanal no Mac (`rotina/semana-brasil.sh`, launchd), com `coleta/onde.py` e o relatório `dados/processados/situacao.md` — Claude
- [ ] Instalar a rodada no Mac: `bash rotina/instalar-mac.sh` e uma primeira vez com `bash rotina/semana-brasil.sh --agora` — Jean-François
- [x] Prefeituras, robô comum (`coleta/prefeituras/`): São Paulo, Recife, Fortaleza, Vitória e Porto Alegre, prefeito, vice e secretários mês a mês pela folha — Claude
- [x] Prefeituras: Salvador, Curitiba, Natal, Campo Grande (desde jun/2025) e Rio (só prefeito e vice: a folha não diz o cargo) — Claude
- [ ] Prefeituras, próximas: Macapá (portal de
  terceiro em Bubble), João Pessoa (Incapsula, não contornamos). Belo Horizonte: o portal bloqueia robôs (WAF) — Claude
- [x] Governadores, v1: salário (subsídio) do governador e do vice nos 27 estados, com a lei ou a fonte de cada valor, quem governou desde 2023 e se a folha abre (`dados/governadores/governadores.json`, mantido à mão) — Claude
- [x] Governadores, v2: o mês a mês pela folha onde ela é aberta (AC, DF, ES, MG, PB, PR, PE, RO, RR, SC, SP) — Claude
- [x] Governadores, v3: folha mês a mês em 24 estados (+ AL, AM, BA, CE, GO, MA, MS, PA, PI, RJ, RN, RS, SE). AP e MT pedem CAPTCHA (não contornamos); TO só funciona clicando — Claude
- [x] Governadores: completar os meses do RN (jan/2025 a ago/2026) — Claude
- [x] Logo novo (prédio público cujas colunas são um gráfico de barras), favicon e prévia do link; rodapé sem nome, com fontes oficiais, código aberto e contato — Claude
- [x] E-mail contato@contasdopoder.com (Cloudflare Email Routing; envio pelo Gmail como contato@) — Jean-François
- [x] Governadores: leis achadas e lidas no texto oficial: SE (9.136/2022), RS (15.940/2023), MA (12.282/2024), RJ (6.651/2013),
  PR (19.901/2019 e 21.348/2022); GO pela cadeia de reajustes desde a Lei 17.254/2011 — Claude
- [x] Governadores com página própria: id por pessoa, endereço pelo nome, fotos (TAREFA-SITE-governadores-como-pessoas.txt) — Claude
- [x] Governadores: levantamento das viagens (diárias e passagens) nos 27 estados (`dados/referencia/viagens_governadores.json`) — Claude
- [x] Governadores: robôs das viagens de AM, MG, SP, PB e SE, desde jan/2025, na rodada semanal (03/10/2026) — Agente de Dados
- [x] Governadores: viagens no site — Agente de Site
- [ ] Governadores: viagens dos outros estados (ver dados/referencia/viagens_governadores.json) — Agente de Dados
- [ ] Governadores: AL (revisões gerais 9.551/2025 e 9.852/2026 citadas; falta a lei do valor base e a de ago/2026) e RN (só a Lei 8.259/2002, arquivo fora do ar) — Agente de Dados
- [ ] Vereadores de SP: fotos com licença confirmada por escrito pela Câmara; 13º e contracheque (só com CPF, não coletamos) — Jean-François
- [x] Vereadores, passo 3: Paraíba e Ceará pela folha nos Tribunais de Contas (vereadores, prefeito, vice e, na PB, secretários; `coleta/tce/`, `site/dados/interior/<uf>.json`) — Claude
- [x] Tribunais de Contas de ES (78 cidades), PE (184) e RJ (91): robôs feitos em 03/10/2026, valor por cargo, jan/2025 a ago/2026 — Agente de Dados
- [x] Tribunais de Contas de ES, PE e RJ no site, na página da cidade, como valor por cargo — Agente de Site
- [x] Site: vereadores, prefeito e vice nas páginas das cidades da PB e do CE — chat do site
- [x] Índice de acesso aos salários dos governadores: 26 estados com nota, cada uma com a prova (`dados/indice/governadores.json`,
  mantido à mão → `site/dados/indice.json`). MT a conferir: a consulta de servidores não abriu em 01/10/2026 — Claude
- [x] Página `/indice` no site, publicada já, sem esperar a eleição (decisão de 01/10/2026) — chat do site
- [x] Deputados estaduais, passo 1: SP (Alesp), PE (Alepe) e MS (Alems): subsídio da lei e verba com fornecedores, em
  `site/dados/assembleias.json`; levantamento das 27 em `dados/referencia/assembleias.json` — Claude
- [x] Deputados estaduais no site: página, busca, seção na página do estado — chat do site
- [x] Deputados estaduais, passo 2: BA, CE, PB, GO, SC, RO, TO, SE, ES, RS e AP (ES, RS e AP rodam no Mac, no Brasil) — Claude
- [x] Deputados estaduais, passo 3: as 11 que faltavam (DF, AM, MA, PR, RN, PI, PA, AC, AL, RR, MT); as 27 com robô. Sem verba: RN (a API exige autenticação), AC e MT (não publicam), AL (formulário escaneado) — Claude
  AC (só salário); MG e RJ só com exceção ao robots.txt (decisão do Jean-François); PR e MT têm CAPTCHA — Claude
- [x] Fotos do TSE (candidaturas de 2022 e 2024, dados abertos CC BY) para deputados estaduais, vereadores, prefeitos, vices e governadores sem foto — Claude
- [ ] Índice: conferir o MT quando o portal voltar — Claude
- [x] Avisos do site (02/10/2026): Assembleias com 1.059 no cargo para 1.059 cadeiras (GO 40/41 e AL 28/27 são da fonte);
  equipe no MT e em RR; RR com ~80 por gabinete é o que a fonte mostra; presidências do STJ pela página oficial — Agente de Dados
- [x] Página "Atualização dos dados" (/atualizacao): até quando vai cada fonte, de `site/dados/situacao.json`, refeito a
  cada rodada — Agente de Dados e Agente de Site

## Fase 3 — Testes e confiabilidade

- [ ] Manutenção (raio-X de 03/10/2026, aprovado): rodada do Brasil mensal; congelar folhas do PA e do RJ e a Prefeitura
  de Campo Grande; folha de governador como complemento da lei; plano de queda das 17 fontes de risco alto; Tribunal de
  Contas como reserva de Fortaleza, Câmara do Recife e Vitória — Agente de Dados
- [ ] Refazer o raio-X das fontes no fim de novembro, com o histórico das rodadas — Agente de Dados
- [x] Bens declarados ao TSE (2018, 2022, 2024), versão neutra: dados e página prontos, dormentes até 26/10/2026 — Agentes de Dados e de Site
- [ ] 27/10/2026: conferir que a rodada gravou bens.json e bens-interior/, que o bloco aparece e que os links do TSE abrem — Agente de Site

- [ ] Página "Como calculamos" — Claude rascunha, você revisa
- [ ] Testar com 5 a 10 pessoas não técnicas: acham o político delas e entendem em 30 s? — Você
- [ ] Uma conversa com advogado (linguagem, LGPD) — Você (sem data: não no futuro próximo, 02/10/2026)
- [x] Canal para pedir correção de dados: "Encontrou um erro?" em cada página (primeiro a fonte, depois o e-mail) e a lista
  pública em /correcoes — Claude
- [x] Conferência dos robots.txt de todos os sites usados; a sessão dos robôs agora bloqueia o que é proibido e respeita
  o Crawl-delay (CKAN pela página do conjunto; Prefeitura de SP e Paraná parados) — Claude
- [x] Regra do robots.txt: convenção, não lei; exceções para dados que a LAI manda abrir (Câmara, Prefeitura de SP, Paraná) — Jean-François e Claude
- [x] Pedidos pela LAI junto com as exceções ao robots.txt: não precisa (decisão de 01/10/2026: quando a única barreira é o robots.txt, o robô lê) — Jean-François

## Fase 4 — Lançamento

- [x] Registrar contasdopoder.com — Você
- [ ] Registrar contasdopoder.com.br — Você
- [x] Código no GitHub (público): jflaloux/contas-do-poder — Você e Claude
- [x] Atualização automática semanal (GitHub Actions), com trava se a conferência falhar — Claude
- [ ] Primeira execução no GitHub: ver se os sites do governo aceitam os servidores do GitHub — Você (botão "Run workflow")
- [x] Cloudflare Pages conectado ao repositório (build `node publicacao/gerar.mjs`, pasta `publicar`) e domínio contasdopoder.com — Você
- [x] Cópias fora do repositório: Zenodo (DOI de todas as versões 10.5281/zenodo.23109646) e Software Heritage (02/10/2026) — Você e Claude
- [x] Espelho no Codeberg (03/10/2026): cada `git push` vai para o GitHub e para o Codeberg — Você
- [ ] Divulgação: Reddit (r/brdev) e primeiros e-mails a jornalistas e organizações em 30/09; o resto depois da eleição — Você

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
- [x] Índice de Transparência com 4 blocos: governo, Assembleia, prefeitura e Câmara da capital (01/10/2026) — Claude
- [x] Índice: blocos atrás de CAPTCHA ou bloqueio conferidos no Chrome (Câmaras de Florianópolis, Campo Grande, BH e Cuiabá; prefeituras de BH e São Luís) — Jean-François e Claude
- [x] Índice: prefeituras de Maceió e Cuiabá conferidas em 03/10/2026; os 27 estados com nota geral — Agente de Dados
- [x] Prova de conceito: os 26 Tribunais de Contas que fiscalizam municípios (dados/referencia/tribunais.json; prova na Paraíba) — Claude
- [x] Robôs dos Tribunais de Contas: PB (TCE-PB, CSV) e CE (TCE-CE, API), com vereadores, prefeito, vice e (PB) secretários, mês a mês desde jan/2025 — Claude
- [ ] Pedir acesso: token da API do TCM-GO, chave da API do TCM-BA, acesso em lote ao TCE-MG e ao TCE-SC — Jean-François decide
