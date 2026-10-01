# Guia para quem trabalha neste código (inclusive assistentes de IA)

Leia antes o `README.md` (como tudo funciona) e o `PLANO.md` (o que falta). Este arquivo reúne as regras e as
armadilhas que não estão escritas em outro lugar.

## Regras que não mudam

- Só dados públicos oficiais, e cada número com o link da fonte.
- Não contornar CAPTCHA, bloqueio de robôs (WAF), login ou consulta que pede CPF: isso é barreira técnica, e não se
  passa por cima. Se o portal bloqueia, o estado fica como "captcha" ou "navegador" e segue sem o dado. Não usar
  credenciais que apareçam no código dos portais (no Mato Grosso do Sul, só a chave anônima de `/Auth/Token`, que o
  portal entrega a qualquer visitante).
- Não guardar CPF, nem mascarado, nem os descontos pessoais da folha (pensão, empréstimo, imposto de cada um).
- `robots.txt`: é uma convenção, não lei (decisão do Jean-François, 30/09/2026). Por padrão, respeitar o robots.txt e o
  `Crawl-delay`, com pausas entre as consultas: a sessão de `coleta/util.py` (`_sessao()`, `SessaoEducada`) faz isso, e
  todo robô usa essa sessão, nunca `requests.get` direto.
  Exceção: dados públicos que a LAI manda publicar e abrir para acesso automatizado (Lei 12.527/2011, art. 8º, § 3º,
  III), como a remuneração de agentes públicos, podem ser lidos mesmo quando o robots.txt proíbe, desde que:
  - o endereço esteja na lista de exceções do código, com o motivo, e no README (público);
  - a leitura seja mínima: só as páginas necessárias, no máximo uma vez por semana, com pausa entre os pedidos e
    respeitando o Crawl-delay;
  - o robô se identifique (User-Agent "ContasDoPoder");
  - o robô pare se o órgão pedir ou bloquear (e aí vale a regra do WAF acima);
  - haja, em paralelo, um pedido pela LAI dos mesmos dados.
- Nunca desligar a verificação de TLS. Se a cadeia do certificado estiver incompleta, completar com o certificado
  intermediário certo (AIA) junto com o `certifi`.
- Fotos só com licença livre ou autorização, com crédito em `site/fotos/creditos.json`.
- Linguagem neutra: fatos, sem adjetivos nem acusações. Quando o dado da fonte parece estranho, o site descreve o que a
  fonte mostra; quem investiga é a imprensa.
- Erro nosso: corrigir e registrar em `site/dados/correcoes.json` (aparece em contasdopoder.com/correcoes).
- Endereço publicado não muda (`site/dados/enderecos.json`, ver README).

## Onde e como rodar

- Vários portais de estados e capitais só abrem de dentro do Brasil. Esses robôs rodam no Mac do Jean-François; o
  GitHub Actions roda nos EUA e pega só o que abre de fora.
- Em sessões com tempo limitado por comando (Cowork: uns 3 minutos, sem processo em segundo plano), rode em partes:
  `python3 coletar.py <etapa> --tempo-max 150`, ou, para a folha de um estado,
  `python3 -m coleta.folhas_estaduais rn 150`. Os robôs gravam o que já pegaram e continuam de onde pararam.
  Ponha também `timeout 170` na frente: alguns robôs só conferem o tempo entre uma consulta e outra, e uma consulta
  lenta passa do limite.
- Para ver o site: `python3 coletar.py site && node publicacao/gerar.mjs && node publicacao/servir.mjs`
  (http://localhost:8000).

## Duas conversas ao mesmo tempo

Às vezes há duas conversas trabalhando no projeto: uma cuida dos dados, a outra do site. Para não pisar uma na outra:

- **Dados**: `coleta/`, `dados/`, `coletar.py`, `site/dados/*.json` (gerados por `python3 coletar.py site`) e
  `site/fotos/`. É também quem roda os robôs.
- **Site**: `site/app.js`, `site/estilo.css`, `site/index.html`, `publicacao/`. Não roda robôs. Para ver o site, usa
  os dados que já estão em `site/dados/`.
- Se uma conversa precisar mexer num arquivo da outra (um texto do site que fala de dados, por exemplo), avisa o
  Jean-François em vez de editar.
- Commit só dos próprios arquivos (`git add <arquivos>`, nunca `git add -A`), um de cada vez. Antes, confira que não
  existe `.git/index.lock`: se existir, a outra conversa está fazendo commit.

## Git e publicação

- Commits com a identidade `Jean-François Laloux <jeanfrancois@laloux.me>`. Quem faz o `git push` é o Jean-François.
- Cada push publica o site no Cloudflare Pages (build `node publicacao/gerar.mjs`, pasta `publicar`).
- Mudança de DNS ou de configuração no Cloudflare: só com o OK dele.
- Contato público: contato@contasdopoder.com (Cloudflare Email Routing, chega na caixa dele).

## Como acrescentar

- **Estado com folha**: um módulo em `coleta/folhas_estaduais/` com `coletar()` (ver `comum.py`: `a_fazer`, `linha`,
  `gravar`), incluído em `ESTADOS` no `__init__.py`; em `dados/governadores/governadores.json`, `folha_nome` e
  `folha` do estado.
- **Capital (vereadores)**: `coleta/vereadores/<cidade>.py` com `comum.montar(...)`, incluído em `CIDADES`; a fonte
  vai na lista de fontes do `site/index.html` e no rodapé.
- **Correção**: um item em `site/dados/correcoes.json` (data, título, texto, `paginas` com os ids ou `governador/uf`).

## Armadilhas conhecidas

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
