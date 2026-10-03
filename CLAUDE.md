# Guia para quem trabalha neste código (inclusive assistentes de IA)

Leia antes o `README.md` (como tudo funciona) e o `PLANO.md` (o que falta). Este arquivo reúne as regras e as
armadilhas que não estão escritas em outro lugar.

## Regras que não mudam

- Só dados públicos oficiais, e cada número com o link da fonte.
- Não contornar CAPTCHA, bloqueio de robôs (WAF), login ou consulta que pede CPF: isso é barreira técnica, e não se
  passa por cima. Se o portal bloqueia, o estado fica como "captcha" ou "navegador" e segue sem o dado. Não usar
  credenciais que apareçam no código dos portais (no Mato Grosso do Sul, só a chave anônima de `/Auth/Token`, que o
  portal entrega a qualquer visitante).
- CPF: o inteiro, nunca. Mascarado (como o Portal da Transparência publica), só de agente público, quando a fonte
  oficial já publica assim e serve para separar homônimos (ex.: ministros nas viagens). De fornecedor pessoa física,
  não, nem mascarado (`vereadores/comum.mascarar` devolve ""). Decisão do Jean-François, 01/10/2026.
- Não guardar os descontos pessoais da folha (pensão, empréstimo, imposto de cada um).
- `robots.txt`: é uma convenção, não lei (decisão do Jean-François, 30/09/2026). Por padrão, respeitar o robots.txt e o
  `Crawl-delay`, com pausas entre as consultas: a sessão de `coleta/util.py` (`_sessao()`, `SessaoEducada`) faz isso, e
  todo robô usa essa sessão, nunca `requests.get` direto.
  Exceção: dados públicos que a LAI manda publicar e abrir para acesso automatizado (Lei 12.527/2011, art. 8º, § 3º,
  III), como a remuneração de agentes públicos, podem ser lidos mesmo quando o robots.txt proíbe, desde que:
  - o endereço esteja na lista de exceções do código, com o motivo, e no README (público);
  - a leitura seja mínima: só as páginas necessárias, no máximo uma vez por semana, com pausa entre os pedidos e
    respeitando o Crawl-delay;
  - o robô se identifique (User-Agent "ContasDoPoder");
  - o robô pare se o órgão pedir ou bloquear (e aí vale a regra do WAF acima).
  Quando a única barreira é o robots.txt, não precisa de pedido pela LAI em paralelo (decisão do Jean-François,
  01/10/2026).
- Nunca desligar a verificação de TLS. Se a cadeia do certificado estiver incompleta, completar com o certificado
  intermediário certo (AIA) junto com o `certifi`.
- Fotos só com licença livre ou autorização, com crédito em `site/fotos/creditos.json`.
- Linguagem neutra: fatos, sem adjetivos nem acusações. Quando o dado da fonte parece estranho, o site descreve o que a
  fonte mostra; quem investiga é a imprensa.
- Erro nosso: corrigir e registrar em `site/dados/correcoes.json` (aparece em contasdopoder.com/correcoes).
- Endereço publicado não muda (`site/dados/enderecos.json`, ver README).

## Onde e como rodar

- Vários portais de estados e capitais só abrem de dentro do Brasil. Esses robôs rodam num computador no Brasil; o
  GitHub Actions roda nos EUA e pega só o que abre de fora. Quem roda o quê está em `coleta/onde.py` (`SO_BRASIL` e o
  histórico de cada fonte em `dados/processados/coletas_*.json`); a rodada do Mac é `rotina/semana-brasil.sh`
  (README, "Duas rodadas"). Robô novo que só abre do Brasil: o nome dele em `SO_BRASIL`. Grupo novo de fontes: o laço
  de `coletar()` com `onde.pular(...)` e `with onde.registrar(...)`, como em `coleta/vereadores/__init__.py`, e o
  grupo em `coletar.py rodada_brasil()` e em `coleta/situacao.py`.
- No Mac, os robôs rodam com `.venv/bin/python` (criado por `rotina/instalar-mac.sh`), não com o `python3` do sistema.
  Dependência nova no `requirements.txt`: rodar também `.venv/bin/pip install -r requirements.txt`, ou a rodada do
  Brasil falha (em 02/10/2026, a Assembleia da PB parou por falta do odfpy no `.venv`).
- `dados/processados/situacao.md` (`python3 coletar.py situacao`) mostra cada fonte: último mês, última coleta certa,
  erro. Atraso que é da própria fonte vai em `ATRASOS_CONHECIDOS` (`coleta/situacao.py`), com o motivo.
- No Cowork, `git status` cria `.git/index.lock` e, sem permissão para apagar arquivos na pasta, não consegue tirar
  a trava, que fica lá e bloqueia os commits (os seus e os do chat do site). Peça a permissão de apagar no começo da
  sessão ou, sem ela, tire a trava com `mv` para fora de `.git/`.
- Em sessões com tempo limitado por comando (Cowork: uns 3 minutos, sem processo em segundo plano), rode em partes:
  `python3 coletar.py <etapa> --tempo-max 150`, ou, para a folha de um estado,
  `python3 -m coleta.folhas_estaduais rn 150`. Os robôs gravam o que já pegaram e continuam de onde pararam.
  Ponha também `timeout 170` na frente: alguns robôs só conferem o tempo entre uma consulta e outra, e uma consulta
  lenta passa do limite.
- Para ver o site: `python3 coletar.py site && node publicacao/gerar.mjs && node publicacao/servir.mjs`
  (http://localhost:8000).
- Testes do site: `node publicacao/gerar.mjs` e depois `node publicacao/testes/rodar.mjs` (README, "Testes do site").
  Nunca rode o build enquanto os testes rodam (o build limpa `publicar/`), nem com outro agente fazendo build ao
  mesmo tempo. O Google Analytics só carrega em contasdopoder.com: testes e prévias não contam visitas.

## Equipe: um orquestrador e três agentes

O Jean-François conversa com uma sessão só, o **orquestrador**, que divide o trabalho entre três agentes
(definidos em `.claude/agents/`). Cada agente cuida dos próprios arquivos:

| Agente | Cuida de | Arquivos |
|---|---|---|
| `dados` | Robôs, coleta, base e os JSON que o site lê. É quem roda os robôs. | `coleta/`, `dados/`, `coletar.py`, `rotina/`, `.github/`, `requirements.txt`, `site/dados/*.json` (gerados por `python3 coletar.py site`), `site/fotos/` |
| `site` | Páginas, visual e publicação. Não roda robôs: usa os dados que já estão em `site/dados/`. | `site/app.js`, `site/estilo.css`, `site/index.html`, `site/_headers`, `site/robots.txt`, `site/favicon.svg`, `site/og.png`, `publicacao/` |
| `divulgacao` | Imprensa, parcerias e avisos a órgãos: pesquisa contatos e escreve rascunhos. Nunca envia nada. | `NOTAS-PRIVADAS.md` (seção "Imprensa e parcerias"), `RASCUNHOS-DIVULGACAO.md` |

- `README.md`: cada agente atualiza a parte do próprio trabalho. `PLANO.md` e as seções "Onde estamos" e "Pendências"
  do `NOTAS-PRIVADAS.md`: o orquestrador.
- Recados entre agentes: `TAREFA-SITE-*.txt` (do `dados` para o `site`) e `TAREFA-DADOS-*.txt` (do `site` para o
  `dados`), fora do Git. Arquivo de outro agente não se edita: diga na resposta o que precisa.
- Commit só dos próprios arquivos (`git add <arquivos>`, nunca `git add -A`), um de cada vez. Antes, confira que não
  existe `.git/index.lock`: se existir, outro agente está fazendo commit.
- Ao terminar, cada agente responde ao orquestrador em poucas linhas: o que fez, arquivos e commit, o que falta, o que
  precisa do Jean-François ou de outro agente.
- Painel dos agentes (só no Mac, fora do Git): http://localhost:4777 mostra o que cada agente está fazendo, a partir dos
  hooks em `.claude/settings.local.json` (`.claude/painel/`). Escreva a descrição de cada comando (campo `description`
  do Bash) em português e em poucas palavras: é ela que aparece no painel.

### Para o orquestrador (a sessão principal; os agentes ignoram esta parte)

- Não faça o trabalho: entenda o pedido, passe ao agente certo e junte as respostas. Ler arquivos para responder a
  uma pergunta rápida, sim; editar código, rodar robôs ou escrever e-mails, não.
- O agente não vê esta conversa: mande um pedido completo (o que, por quê, quais arquivos, quando está pronto).
- Chame o agente pelo nome (`site`, `dados`, `divulgacao`). Quando for continuação do mesmo assunto, mande a mensagem
  ao agente que já fez a primeira parte em vez de começar outro: ele lembra o que fez e gasta menos.
- Trabalho independente (uma página nova e um robô novo), em paralelo. Quando um depende do outro, em sequência: o
  `dados` prepara os dados e escreve um `TAREFA-SITE-*.txt`; depois o `site` faz a página.
- Assunto que pode virar notícia (dado novo, correção, achado nas folhas): pergunte ao Jean-François se quer que a
  `divulgacao` prepare algo.
- Rascunho de e-mail da `divulgacao`: mostre o texto inteiro ao Jean-François, sem resumir.
- Rascunhos no Gmail: `rotina/rascunhos_gmail.py` lê o `RASCUNHOS-DIVULGACAO.md` (cada bloco com a caixa ```email:
  para, cc, assunto) e cria ou atualiza os rascunhos com De: contato@ e links diretos; nunca envia. Quem roda é o
  Jean-François (a credencial do Google fica no Mac dele). Não grave rascunhos pela ferramenta de Gmail da sessão: ela
  põe o remetente pessoal e troca os links por redirecionamentos do Google.
- Peça o OK do Jean-François antes de: enviar qualquer coisa (e-mail, formulário, post: quem envia é ele), `git push`,
  mudança no Cloudflare ou no DNS, e qualquer nova exceção ao robots.txt.
- No fim de um bloco de trabalho, peça a cada agente usado que guarde na memória dele o que aprendeu. Regra ou
  armadilha que vale para qualquer pessoa vai para este arquivo.
- Para o Jean-François, respostas curtas: o que ficou pronto e o que precisa dele.

## Git e publicação

- Commits com a identidade `Jean-François Laloux <jeanfrancois@laloux.me>`. Quem faz o `git push` é o Jean-François.
- Cada push publica o site no Cloudflare Pages (build `node publicacao/gerar.mjs`, pasta `publicar`).
- Mudança de DNS ou de configuração no Cloudflare: só com o OK dele.
- Contato público: contato@contasdopoder.com, caixa própria do projeto no Google Workspace (desde 03/10/2026; MX, SPF,
  DKIM e DMARC no DNS do Cloudflare). Os rascunhos de e-mail são criados nessa conta, e quem envia é o Jean-François.

## Como acrescentar

- **Estado com folha**: um módulo em `coleta/folhas_estaduais/` com `coletar()` (ver `comum.py`: `a_fazer`, `linha`,
  `gravar`), incluído em `ESTADOS` no `__init__.py`; em `dados/governadores/governadores.json`, `folha_nome` e
  `folha` do estado.
- **Capital (vereadores)**: `coleta/vereadores/<cidade>.py` com `comum.montar(...)`, incluído em `CIDADES`; a fonte
  vai na lista de fontes do `site/index.html` e no rodapé.
- **Correção**: um item em `site/dados/correcoes.json` (data, título, texto, `paginas` com os ids ou `governador/uf`).

## Armadilhas conhecidas

- Fotos do TSE (`coleta/fotos_tse.py`): o zip de fotos de SP de 2024 tem 2,3 GB. Nunca baixar inteiro: o leitor
  por pedaços (HTTP Range) lê o índice do zip e só as fotos que faltam. Casar só por nome exato com um único SQ
  (homônimos ficam sem foto). O conjunto de dados do TSE é Creative Commons Atribuição: sempre com o crédito.
- Regenerar `camaras.json` ou `governadores.json` fora da rodada semanal muda mais do que se quer (o último mês
  fechado avança, a nota do Paraná sobre o robots.txt some). Para mudar só as fotos, trocar só `f`/`fc` no arquivo.
- Câmara: a página de remuneração de cada deputado lista pagamentos de meses fora do mandato (aposentadoria de
  ex-deputado, antes da posse de suplentes). `coleta/site.py` (`_sem_pagamento_fora_do_mandato`) tira esses meses
  pelo histórico oficial.
- Governadores: o 13º adiantado vem marcado e fica fora da média (`_serie` em `coleta/governadores.py`).
- Rio Grande do Norte limita as consultas (erro 429): pausa de 10 s. A exportação em CSV por órgão passou a dar 429
  sempre; o robô usa a busca pelo nome (JSON), que sai antes da lista por órgão. Cada mês leva ~1 min.
- Bahia e Rio Grande do Sul: painéis Power BI, lidos com a chave anônima que a própria página entrega
  (`coleta/folhas_estaduais/powerbi.py`).
- Node 22: `fs.cpSync` falha em pastas montadas de máquina virtual; `gerar.mjs` copia arquivo por arquivo.
- Ao passar arquivos entre máquinas, use nomes únicos e confira o md5 (uma cópia antiga já foi publicada por engano).
- Câmara: o robots.txt (desde 18/09/2026) proíbe `/deputados/*/*`; essas páginas são exceção (lista em
  `coleta/util.py`). O que já foi lido fica em `dados/camara/` (no Git) e não é baixado de novo. Os contracheques
  detalhados (~530 por mês) são lidos aos poucos, do mais recente para o mais antigo (`CAMARA_MAX_DETALHE`, 6.000 por
  vez); o padronizar só usa os meses completos (`DETALHE_DESDE`). Nunca guardar IR, previdência ou líquido.
- Portais CKAN proíbem `/api/` no robots.txt: ache os arquivos pela página do conjunto (`util.recursos_ckan`).
- Prefeitura de SP (`Disallow: /`) e Paraná (`Disallow: /pte`): exceções ao robots.txt; para parar, `BLOQUEADO_ROBOTS = True`.
- No Cowork, a pasta montada não deixa apagar arquivos: `node publicacao/gerar.mjs` falha ao limpar `publicar/`. Para
  conferir o build, copie `site/` e `publicacao/` para uma pasta fora de `mnt/` e rode lá.

- Assembleias: o TSE de 2022 traz o partido da eleição; muitos deputados mudaram na janela de 2026. Use o partido da
  própria Assembleia (SP, PE) ou o da candidatura de 2026 (`assembleias.comum.partido_2026`); sem nenhum dos dois,
  sem partido. O arquivo de 2026 traz CPF: só nome e partido são lidos, nada é guardado.
- Alepe (PE): as notas da verba vêm uma prestação por pedido; o robô baixa no máximo 400 por vez (as que faltam
  entram com o total, sem detalhe).
- Prefeitura do Rio: o CSV mensal não tem o cargo; só prefeito e vice entram, pelo nome dos eleitos de 2024.
- CPF solto em texto livre: o MEI tem como razão social "NOME 12345678901", e algumas fontes põem o CPF no histórico do
  pagamento (Alep) ou no nome do beneficiário (Aleam). `vereadores/comum.limpar_cpfs(pasta)` roda depois de cada coleta
  das capitais e das Assembleias, e `comum.empresa()` tira o número do nome no site. Fonte nova com texto livre: varrer
  os CSVs por 11 dígitos antes do commit.
- Assembleias: o deputado licenciado (secretário de Estado, por exemplo) costuma continuar na folha com o subsídio (PR,
  PI, PA): estar na folha não é estar no cargo. Use um sinal de exercício (gabinete com comissionados no PR, notas da
  verba no PI, verba ou gabinete no PA).
- ALRN (RN): a API do Portal da Transparência exige autenticação e não é usada (verba e folha ficam de fora). A lista
  de parlamentares (api-transparencialegislativa) é aberta, mas traz CPF e data de nascimento: ler só nome, vigência e
  partido.
- Problema de segurança de um órgão (dados pessoais expostos, credencial no código, site invadido): não descrever em
  arquivo que vai para o Git (código, README, PLANO, este arquivo, `dados/referencia/`) nem no site enquanto o órgão não
  for avisado. O registro fica em `NOTAS-PRIVADAS.md`; no público, só "exige autenticação" ou "não usamos".
- Alema (MA): JSF/PrimeFaces; o número de cada parlamentar só sai do clique (AJAX) no nome da lista, e o robô guarda o
  número (`dados/assembleias/ma/parlamentares.csv`). O robots.txt responde 403, que a sessão trata como "sem robots.txt"
  (RFC 9309).
- CLDF (DF): o arquivo de fev/2026 no CKAN é cópia do de jun/2025 (o robô deixa o mês de fora); o 13º vem em folhas à
  parte (002 e 003, adiantamento; 016, dezembro).
- ALE-AL: a lista da folha leva ~18 s por letra, e a letra sem nomes (X) devolve a lista do A. A VIAP é imagem, com o
  total corrigido à mão: não publicar por OCR.
- ALMT: o portal Elotech carrega o script do reCAPTCHA, mas ele só aparece em entidades integradas ao Oxy
  (`isIntegradoOxy` em `configuracoes-gerais`): conferir antes de rodar. A api.al.mt.gov.br pede login e não é usada.
- TCE-CE: a API limita quem lê muito (em 02/10/2026, depois de ~3 h com 3 pedidos por vez, parou de responder ao Mac por
  ~12 min): 2 pedidos por vez, com pausa. O CPF cifrado só liga folha e cadastro na memória; nunca é gravado.
- Cowork: a ligação com o Mac cai (em 02/10/2026, por ~13 h) e, antes de cair, o limite de cada comando encurta (de ~150
  s para ~20 s); chamadas em paralelo se derrubam. Rode os robôs em partes curtas (`definir_prazo(70)` com `timeout 85`),
  um por vez. Depois que a ligação volta, a permissão de apagar arquivos na pasta precisa ser pedida de novo.
- Judiciário: STF, STM e TSE vêm do DadosJusBr (CC BY 4.0, sempre com o crédito). Não ler a consulta do STF
  (egesp-portal, robots.txt Disallow: /) nem a do STM (www2.stm.jus.br/rem_web) sem a exceção; o 403 do TSE não se
  contorna. Do STF, os valores saem da cópia do arquivo oficial (backups/), não do pacote: dez/2025 tem colunas e linhas
  repetidas, e o sinal das férias de jul/2026 se acerta pelos totais do próprio arquivo.
- Judiciário: a "remuneração do órgão de origem" (TSE, CNJ) nunca entra, para não somar duas vezes. Quem aparece na folha
  e não está em dados/judiciario/composicao.json vira aviso no log (os nomes "fora" já conferidos ficam no arquivo).
- STJ: o CSV detalhado vem com o BOM duas vezes; a retenção pelo teto vem com tipo "Remuneratória": os grupos de desconto
  saem pelo nome. TST: o leiaute muda de um mês para outro, jun/2025 veio em MacRoman, e aposentado aparece como INATIVO
  ou APOSENTADO. CNJ: mês com dois dígitos; a página mistura números em formato americano e brasileiro e às vezes perde o
  primeiro algarismo do subsídio (",10.37"). MPF: usar o endereço sem www; o ODS é lido sem odfpy.
- Cloudflare Pages (plano gratuito): no máximo 20.000 arquivos e 2.000 redirecionamentos. Em 02/10/2026: ~13.900
  arquivos e 811 redirecionamentos. Nada de página por pessoa abaixo dos tribunais superiores nem para o interior
  (vereadores do interior ficam na página da cidade). O `gerar.mjs` avisa a partir de 18.000 arquivos ou 1.800
  redirecionamentos e falha acima do limite. Se faltar espaço: juntar os arquivos por pessoa (`dados/pessoa/<id>.json`,
  ~2.650) em pedaços por estado e grupo, o que libera ~2.500 arquivos.
- Robô que falha não grava arquivo vazio por cima do último dado bom: mantém o anterior e a situação marca a falha. Em
  02/10/2026 a API de despesas da Câmara do Recife deu erro para todos, o robô gravou vazio e a cidade sumiu do site.
  `coleta/situacao.py` agora marca como "falhando" cidade ou estado que falta no arquivo do site.
- "No cargo" nas Assembleias: estar na folha ou nas notas da verba no último mês não basta (licenciados continuam
  recebendo; suplentes saem quando o titular volta; quem ainda não lançou a verba some). Use a lista de quem está em
  exercício que a própria Assembleia publica (e a de afastamentos, com as datas, em GO).
