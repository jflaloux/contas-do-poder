# Contas do Poder

**Site: [contasdopoder.com](https://contasdopoder.com)**

Quanto ganha e quanto custa cada deputado federal, senador, ministro e o presidente, por mês, com números oficiais
da Câmara, do Senado e do Portal da Transparência. Um projeto independente e sem fins lucrativos, que não é de nenhum
órgão do governo. E também, sempre pela fonte oficial de cada um:

- **Governadores e vices** dos 27 estados: o salário pela lei de cada estado e, onde a folha é pública, o que cada um
  recebe, mês a mês.
- **Deputados estaduais e distritais** das 27 Assembleias Legislativas (26 estados e o Distrito Federal): salário, verba
  do gabinete e equipe, onde a Assembleia publica.
- **Judiciário**: os ministros do STF, STJ, TST, STM e TSE, os conselheiros do CNJ e o procurador-geral da República,
  mês a mês desde jan/2025.
- **Capitais**: cada vereador de 13 capitais (São Paulo, Rio de Janeiro, Belo Horizonte, Fortaleza, Goiânia, Maceió,
  Manaus, Natal, Porto Alegre, Recife, São Luís, Aracaju e Boa Vista) e o prefeito, o vice e os secretários de nove (São Paulo,
  Recife, Fortaleza, Vitória, Porto Alegre, Salvador, Curitiba, Natal e Campo Grande), além do prefeito e do vice do
  Rio de Janeiro.
- **Interior do Ceará e da Paraíba**: vereadores, prefeito e vice de cada cidade, pela folha que o município manda ao
  Tribunal de Contas do estado.
- **Interior do Espírito Santo, de Pernambuco e do Rio de Janeiro**: quanto cada Câmara paga ao cargo de vereador e
  quantas pessoas estão nele (no Espírito Santo e em Pernambuco, também o prefeito e o vice), pelo que o município manda
  ao Tribunal de Contas, que nesses estados não publica o valor de cada pessoa.
- **Todas as 5.569 cidades**: o gasto da Câmara Municipal (Siconfi), a população, o número de vereadores e os
  vereadores eleitos em 2024 (TSE).
- O **Índice de Transparência**: a nota de cada fonte de cada estado, critério por critério.

Um projeto [Contas do Brasil](https://contasdobrasil.com), criado por [Jean-François Laloux](https://laloux.me)
([GitHub](https://github.com/jflaloux)). Projeto de código aberto (licença MIT): sugestões e correções são bem-vindas
nas issues.

Este repositório tem os robôs que coletam os dados oficiais, a base unificada e o site.

## Como rodar

```bash
pip3 install -r requirements.txt
python3 coletar.py tudo          # Câmara + Senado + governo federal + câmaras + prefeituras + governadores + fotos + site
python3 coletar.py conferir      # compara nossos números com os sites oficiais
```

A primeira coleta faz alguns milhares de consultas e leva uns 20–30 minutos. Tudo fica guardado em
`dados/cache/`, então as próximas execuções só baixam o que mudou. Para rodar em partes, use
`--tempo-max 150`: o robô para sozinho e continua de onde parou na próxima vez.

## Atualização automática

O robô do GitHub Actions (`.github/workflows/atualizar-dados.yml`) roda **toda terça-feira às 8h17**
(horário de Brasília). Também dá para rodar na hora: aba **Actions** → **Atualizar dados** → **Run workflow**.

1. Baixa os dados oficiais (reaproveitando os downloads da semana anterior).
2. Monta a base e o arquivo do site.
3. Confere com os sites oficiais e faz checagens de sanidade (`coletar.py conferir --max-alertas 8`).
4. Se tudo estiver certo, salva os números novos neste repositório, e o Cloudflare Pages publica o site.

Se uma fonte estiver fora do ar ou a conferência falhar, **nada é salvo**: o site anterior continua no ar
e o GitHub manda um e-mail. O relatório da conferência fica anexado em cada execução.

A legislatura atual termina em janeiro de 2027. A partir de fevereiro de 2027 o robô para com um aviso
até `coleta/config.py` ser atualizado para a nova legislatura.

### Duas rodadas: nos EUA e no Brasil

Vários portais de estados e capitais só abrem de dentro do Brasil, e o GitHub Actions roda nos EUA. Por isso há
duas rodadas: a do GitHub, toda semana, e a do Brasil, uma vez por mês (desde 03/10/2026; antes era semanal).

| Rodada | Onde | Quando | O que faz |
|---|---|---|---|
| Exterior | GitHub Actions | toda terça, 8h17 | Tudo o que abre de fora (`CONTAS_ONDE=exterior`), menos as fontes congeladas |
| Brasil | Um computador no Brasil (`rotina/semana-brasil.sh`, pelo launchd do macOS, que chama o script todo dia às 13h07) | uma vez por mês, a partir da terceira terça-feira (a primeira terça depois do dia 14), às 13h07; se o computador estiver desligado, no primeiro dia em que estiver ligado. Próximas: 20/10, 17/11 e 15/12/2026 | `pip install -r requirements.txt`; `python3 coletar.py brasil`: as fontes que só abrem do Brasil e as que falharam de fora, menos as congeladas e as que já estão em dia (o último mês fechado já está no site); refaz os arquivos do site a partir dos CSVs; commit só dos dados e push |

A rodada do Brasil é mensal porque quase todas as fontes que só abrem do Brasil publicam uma vez por mês: com a
terceira terça-feira, a folha do mês anterior já saiu na maioria delas, e o computador precisa estar ligado um dia por
mês. Uma fonte que falha de fora espera a rodada do Brasil seguinte (até um mês).

- **Fontes congeladas** (`CONGELADAS` em `coleta/onde.py`): a fonte parou de publicar o que o site mostra. O site fica
  com o último dado, a página de atualização diz "Congelada: dados até ..." com o motivo, e o robô só tenta de novo a
  cada 90 dias (se a fonte voltar, a situação avisa, e ela sai da lista à mão). Desde 03/10/2026: a folha do Pará (dados
  até mar/2026: a consulta pública não mostra mais quem tem mandato eletivo), a folha do Rio de Janeiro (dados até
  mar/2026: o governador em exercício é o presidente do Tribunal de Justiça, pago pelo Tribunal) e a Prefeitura de
  Campo Grande (dados até fev/2026: a consulta não traz a folha depois disso).
- **Folha de governador é complemento da lei**: o subsídio dos 27 governadores e vices vem da lei, e o site o mostra
  sempre; a folha só acrescenta 13º, férias e abate-teto. Folha de governador que quebrar e cujo conserto passar de
  cerca de 1 hora é congelada, e o site fica com o valor da lei.
- **Plano de queda** (`dados/referencia/plano-de-queda.json`): o que fazer quando quebra cada uma das 17 fontes de
  risco alto do raio-X (`dados/processados/raio-x-fontes.md`). A regra geral é a mesma: o robô que falha não apaga o
  último dado bom, e o conserto só vale se couber em cerca de 1 hora; passou disso, a fonte é congelada. O relatório de
  situação mostra o plano ao lado de cada fonte que falhar.
- **Tribunal de Contas como reserva das capitais que ele cobre** (`RESERVAS_TCE` em `coleta/situacao.py`): Câmara e
  Prefeitura de Fortaleza (TCE-CE, valor de cada pessoa), Câmara do Recife (TCE-PE) e Prefeitura de Vitória (TCE-ES),
  as duas pelo total pago ao cargo. Quando a coleta da fonte própria falha, ou quando o tribunal tem 2 meses ou mais à
  frente dela, a chave `reservas` de `site/dados/situacao.json` marca a reserva como ativa, e a página da cidade usa o
  arquivo do tribunal, com o aviso pronto (`aviso`: no TCE-PE e no TCE-ES, que o valor é o total pago ao cargo, não o
  salário de cada pessoa).

- **Quem roda o quê** (`coleta/onde.py`): a lista `SO_BRASIL` e o histórico de cada fonte. Cada rodada anota, por
  fonte, a última tentativa, o último sucesso, as falhas seguidas e o erro, num arquivo só seu
  (`dados/processados/coletas_exterior.json` e `coletas_brasil.json`, para as duas não brigarem no Git). Uma fonte que
  falha de fora passa sozinha para a rodada do Brasil seguinte; depois de 2 falhas de fora, o GitHub deixa de tentar (e tenta
  de novo uma vez por mês).
- **Situação das fontes** (`python3 coletar.py situacao`, no fim de cada rodada): `dados/processados/situacao.md`,
  com o último mês no site, a última coleta certa e onde, e o último erro de cada fonte. "falhando" = a última
  tentativa falhou; "atrasada" = 3 meses ou mais atrás do último mês fechado; "atrasada (fonte)" = o atraso é da própria
  fonte (Minas e São Paulo publicam a folha com meses de atraso, por exemplo). No GitHub, o relatório aparece no resumo
  de cada execução; na rodada do Brasil, as fontes com problema viram um aviso na Central de Notificações do macOS.
  Uma cidade ou um estado que não entrou no arquivo do site (a montagem falhou) também aparece como "falhando".
- **Resumo da rodada** (`dados/processados/rodada-resumo.json`, refeito junto com o relatório): o que quebrou desde a
  rodada anterior, o que voltou e o que continua com problema ("falhando" ou "atrasada"; o atraso da própria fonte não
  conta), mais o histórico das últimas 26 rodadas. A rodada é a semana que começa na terça: a do GitHub e a do Brasil
  são a mesma, e rodar de novo na mesma semana só atualiza a semana; a comparação é sempre com o fim da semana anterior.
  Aparece no começo do `situacao.md`, no aviso do Mac e, só com os ids e as datas, na chave `rodada` do
  `site/dados/situacao.json`. O histórico serve para o raio-X das fontes (`dados/processados/raio-x-fontes.md`: tipo
  de acesso, onde roda, problemas já vistos, tamanho, cobertura, risco e recomendação de cada fonte).
- **Frescor dos dados** (`site/dados/situacao.json`, refeito junto com o relatório): a versão pública, para o site. De
  cada fonte, o nome, o grupo, o link oficial, o último mês com dados no site, a data da última coleta certa e a
  situação em palavras neutras ("Em dia"; "Atraso da própria fonte", com o motivo de `ATRASOS_CONHECIDOS`; "A coleta
  falhou desde dd/mm/aaaa", pela primeira falha depois do último sucesso). Sem o erro técnico nem onde a coleta rodou.
- **Conflitos**: os CSVs de cada rodada são de fontes diferentes; os arquivos do site saem dos CSVs. Se as duas rodadas
  mexerem no mesmo arquivo do site, a segunda fica com a versão da outra e refaz os arquivos (`python3 coletar.py
  montar`, que só monta, sem coletar).
- **Commits feitos à mão**: se houver commits esperando o push, a rodada do Brasil faz o seu commit
  mas não envia nada (avisa). Se houver mudança sem commit nos arquivos de dados ou no código, ela não roda (avisa e
  tenta no dia seguinte).
- **Instalar a rodada do Brasil** (uma vez, num computador com macOS): `bash rotina/instalar-mac.sh` (cria o `.venv`, instala as dependências e o
  agendamento). Rodar na hora: `bash rotina/semana-brasil.sh --agora`. O registro de cada rodada fica em
  `~/Library/Logs/ContasDoPoder/`.

## Publicação (Cloudflare Pages)

Projeto do Cloudflare Pages conectado a este repositório, com o comando de build `node publicacao/gerar.mjs`
e `publicar` como pasta de saída. Cada mudança no repositório publica o site automaticamente.

**Endereços.** Cada político, estado e cidade tem o seu endereço: `contasdopoder.com/guilherme-boulos`,
`/governador/sp`, `/cidade/sao-paulo-sp` (o período vai em `?periodo=2025` ou `?periodo=mandato`). O endereço de
cada político fica guardado em `site/dados/enderecos.json` e não muda depois de criado (quem tem dois cargos fica
com o nome, e cada cargo com `/nome/ministro`, `/nome/deputado`); se mudar, o antigo redireciona para o novo. Os links
antigos, com `#` (`/#dep-220639`), continuam funcionando: o site leva para o endereço novo.

`publicacao/gerar.mjs` (sem dependências) copia `site/` para `publicar/` e cria uma página HTML pronta para cada
endereço, com título, descrição e prévia de link próprios e um resumo em texto, para o Google e para as prévias do
WhatsApp, que não rodam JavaScript. Também gera o `sitemap.xml` e o `_redirects`. Depois de carregar, a página
funciona como antes: o `app.js` desenha tudo e troca de página sem recarregar.

**Limites do Cloudflare Pages.** No fim, o `gerar.mjs` confere os limites do Pages
([limites](https://developers.cloudflare.com/pages/platform/limits/)): até 20.000 arquivos por site no plano Free
(100.000 nos pagos, desde 23/01/2026), até 2.000 redirecionamentos no `_redirects` e até 25 MiB por arquivo. Ele mostra
a contagem (em 02/10/2026: 13.789 arquivos, sendo 5.569 em `cidade/`, 2.960 páginas de políticos, 2.650 arquivos por
pessoa e 2.506 fotos; 811 redirecionamentos; o maior arquivo, `dados/assembleias.json`, com 2,8 MB), avisa a partir de
90% de cada limite e, acima dele, faz o build falhar, com a contagem por pasta: o Cloudflare recusaria a publicação, e o
site no ar continua o anterior. Num plano pago, basta pôr `LIMITE_ARQUIVOS=100000` nas variáveis do projeto. Por isso,
o que tem milhares de pessoas (como os vereadores do interior) entra na página da cidade, sem página nem arquivo por
pessoa.

Para a primeira visita ser rápida no celular, o `gerar.mjs` também divide os dados: `publicar/dados/indice/` tem
`dados.json`, `camaras.json` e `assembleias.json` sem a série mês a mês (`t`) e sem o detalhe dos gastos (`dt`) de cada
pessoa, que vão para `publicar/dados/pessoa/<id>.json` (com o nome de cada tipo de gasto e de cada fornecedor) e só são
baixados ao abrir a página daquela pessoa; por isso a lista `meta.tipos` das câmaras e das Assembleias, com milhares de
fornecedores, também fica fora da versão leve (ao abrir o site, os dados vão de cerca de 1,3 MB para cerca de 420 KB
comprimidos, já com os deputados estaduais). Os arquivos inteiros continuam em `publicar/dados/`, para quem reutiliza os
dados. Governadores e vices vêm de `governadores.json` e viram pessoas (ver "Governadores"): a lista em
`publicar/dados/indice/governadores-pessoas.json` e o mês a mês de cada um, também, em `publicar/dados/pessoa/<id>.json`.
Cada página pronta já traz o topo do contracheque (nome, custo por mês e de onde ele vem) e pede ao navegador
para baixar os dados junto com o `app.js` (`<link rel="preload">`). Sem o `gerar.mjs`, o `app.js` lê os arquivos
inteiros de `site/dados/`.

Para a página não pular enquanto carrega: o texto pronto fica na tela até o `app.js` ter a versão completa (aí uma
troca pela outra); os números do topo da página inicial já vêm no HTML; enquanto a fonte Barlow não chega, o site usa
uma fonte do sistema ajustada às medidas dela (`Barlow Reserva` no `estilo.css`); e cada gráfico é desenhado antes da
primeira pintura (`aoRedimensionar` no `app.js`). A lista das 5.569 cidades (`municipios.json`) só é baixada nas páginas que
mostram câmaras municipais (a inicial e a de cada cidade) ou quando a pessoa toca no campo de busca.

**Página de cidade (desempenho).** O gráfico de pontos (`graficoPontos`, onde cada colega é um ponto) desenha todos os pontos
num único `<path>` (um círculo por subcaminho, no mesmo sentido: onde se sobrepõem, a mancha fica de uma cor só), e não um
`<circle>` por pessoa: nas 2.376 cidades de 10 a 50 mil habitantes eram milhares de elementos. O texto alternativo
(`aria-label`), a dica ao passar o ponteiro e o clique continuam iguais. O parágrafo em destaque ("Por habitante, a Câmara
custa mais/menos que X% das outras cidades...") já vem no HTML (`destaqueCidade`, no `gerar.mjs`, com o mesmo texto do
`secCidade`): é o maior bloco de texto da página, e, se só chegasse com o `app.js` (que espera ~600 KB de dados), o LCP
passaria da primeira pintura para o fim do carregamento. O teste do site confere que o texto pronto e o do `app.js` são
iguais. Medida no celular simulado (1,6 Mbps, 150 ms, CPU 4x): cidade pequena, LCP de 4,8 s para 0,8 s, nós do DOM de 3.158 para
800 e TBT de 29 para 19 ms; cidade média, LCP de 4,8 s para 0,84 s (a capital já era 0,84 s).

## Ver o site no seu computador

```bash
python3 coletar.py site       # gera site/dados/ a partir da base
node publicacao/gerar.mjs     # monta publicar/, como o Cloudflare Pages
node publicacao/servir.mjs    # depois abra http://localhost:8000
```

O servidor local (`servir.mjs`) imita o Cloudflare Pages: endereços sem `.html`, redirecionamentos e compressão gzip do texto
(os dados em JSON ficam ~5 vezes menores, como no site de verdade).

O site é estático (HTML, CSS e JavaScript, sem instalar nada): `site/index.html`, `site/estilo.css`,
`site/app.js`, os dados em `site/dados/dados.json` e as fotos em `site/fotos/`. Dá para hospedar de graça em qualquer serviço de
site estático. Para os links de compartilhamento apontarem para o endereço certo, preencha
`<meta name="endereco-do-site">` no `index.html` quando o site tiver domínio.

### Testes do site (`publicacao/testes/`)

```bash
node publicacao/gerar.mjs                       # os testes leem publicar/
node publicacao/testes/rodar.mjs                # sobe o servidor local numa porta própria e roda tudo
```

Abre 91 tipos de página (a inicial; deputado federal, senador, ministro, ministro que também é deputado, vereador,
prefeitura, deputado estadual, governador (com e sem viagens) e pessoa do Judiciário; cidade de capital, do interior e pequena; estado; os
tribunais; `/judiciario`, `/indice`, `/dados-abertos`, `/correcoes`, `/atualizacao`, `/sobre`; e um endereço que não existe) no
Chrome, no celular (390 px, tema claro) e no computador (1280 px, tema escuro), e confere: **funcional** (sem erro no
console, sem exceção, sem arquivo que falta, título, um só `h1`, o "Carregando…" fora, sem rolagem horizontal, sem cookies
próprios (a página `/sobre` diz que o site não usa) e o que
cada página precisa mostrar), **CLS** (até 0,1), **axe-core** (nenhuma violação de acessibilidade, contraste incluído) e o
**Google Analytics só em produção** (ver "Compartilhamento e medição").
O LCP e o tempo de cada página saem no relatório, sem valer como falha. Os pedidos a sites de fora (as fontes do
Google) são bloqueados: o teste não precisa de internet e, fora da produção, o site nem pede o Google Analytics. Termina com código 1 se algo
falhar. Leva uns 5 minutos (as páginas de pessoa esperam o desenho da imagem de compartilhamento, que sem as fontes do
Google demora ~6 s).

- `--rapido`: o modo para o meio do trabalho, uma página de cada tipo em 2 perfis (uns 3 min). `--mudou`: o rápido mais as páginas dos
  assuntos que o seu `git diff` toca (a tabela `GRUPOS`, no `rodar.mjs`: o diff do código do site, sem contar o próprio teste, casa com
  um assunto e entram as páginas dele; assunto novo no site = uma linha na tabela). **A suíte completa (`--completo`, sem `--rapido`)
  continua sendo a que vale antes do commit.** A suíte completa leva ~50 min (mais de 90 tipos de página em 4 perfis).
- `node publicacao/testes/regras.mjs`: as regras de cálculo com casos inventados e a concordância entre o HTML pronto do `gerar.mjs` e a página
  do `app.js`. Parte 1 (só Node, precisa do build): em todas as páginas de deputado, senador e "tudo junto" (771), o valor do topo do HTML pronto
  é o da regra do pagamento único, feita à parte com os números de `dados.json`, e a tabela `UNICOS` é a mesma nos dois códigos. Parte 2
  (Chrome): um build à parte (`GERAR_SAIDA` e `GERAR_DADOS` do `gerar.mjs`, `PUBLICAR_DIR` do `servir.mjs`; não toca em `publicar/`) com
  deputados e um senador inventados (2 e 3 meses, pagamento único com e sem o mês na fonte, devolução com valor negativo, ano inteiro) e um
  "tudo junto" de verdade; em cada um, o HTML pronto, o topo da página, o fim da lista, o ranking (ou "não entra", com menos de 3 meses) e o
  Comparar dizem o mesmo número, que é o da conta, e a nota diz "paga de uma vez no período" quando a fonte não traz o mês. Rode depois de
  mexer na regra, no `resumo()` do `app.js` ou na prévia do `gerar.mjs`.
- `--completo`: os 4 perfis (celular e computador, claro e escuro) em vez de 2.
- `--paginas=atualizacao,indice`: só essas (os nomes estão em `PAGINAS`, no `rodar.mjs`).
- `--url=http://localhost:8000`: usa um servidor que já está rodando (`node publicacao/servir.mjs`).
- `--capturas=/tmp/capturas`: guarda uma imagem de cada página e perfil.
- `--analytics` / `--sem-analytics`: a conferência do Google Analytics roda no fim (só no servidor local); com `--paginas`
  ela só roda se pedida.

**Não rode o build e os testes ao mesmo tempo:** o `gerar.mjs` apaga e refaz `publicar/`, de onde o servidor local lê. Se
isso acontecer, os testes percebem (o servidor devolve 503 enquanto `publicar/` está vazia), param com um aviso e não
seguem falhando página por página; é só esperar o build e rodar de novo.

**Sem instalar nada no projeto.** Não há `package.json` na raiz nem em outra pasta: o Cloudflare Pages só roda
`node publicacao/gerar.mjs`, que não muda, e nada de `publicacao/testes/` entra em `publicar/`. Os testes usam só o Node
(22 ou mais novo) e o Chrome que já estiver no computador (ou o executável indicado na variável `CHROME`), pelo
protocolo DevTools (`cdp.mjs`). A única peça de fora é o **axe-core** (versão 4.10.2): sem ele, o teste roda o resto e
avisa que o axe não rodou. Para ter o axe, rode uma vez `node publicacao/testes/rodar.mjs --baixar-axe`: ele baixa o
arquivo `axe.min.js` (~0,5 MB, do cdnjs) para `~/.cache/contas-do-poder/` e só o grava se o SHA-256 bater com o do
`rodar.mjs` (`AXE_SHA256`, do arquivo 4.10.2 baixado em 02/10/2026); o arquivo fica fora do repositório. Quem já tem o
axe aponta `AXE_JS` para o `axe.min.js`. Para trocar de versão, mude `AXE_VERSAO` e `AXE_SHA256` (o teste mostra o
SHA-256 da baixa nova).

Lighthouse (desempenho no celular), à parte, com o servidor local rodando:
`npx lighthouse http://localhost:8000/judiciario --form-factor=mobile --only-categories=performance --view`
(o `npx` baixa o Lighthouse na hora; a nota varia de uma rodada para outra e, no servidor local, não mede a internet).

## Pastas

| Pasta | O que tem |
|---|---|
| `site/` | O site. `site/fotos/` tem as fotos oficiais reduzidas (240×320, WebP, ~8 KB cada) |
| `publicacao/` | `gerar.mjs` (monta `publicar/`), `servir.mjs` (servidor local) e `testes/` (testes do site) |
| `coleta/` | Código dos robôs (`camara.py`, `senado.py`, `executivo.py`, `fotos.py`, `fotos_tse.py`, `municipios.py`, `governadores.py`, `vereadores/`, `prefeituras/`), da base unificada (`padronizar.py`) e da conferência (`conferir.py`) |
| `dados/governadores/` | O salário de cada governador e vice, com a fonte de cada valor (mantido à mão), e em `folha/` o mês a mês pela folha de cada estado |
| `dados/municipios/` | Cidades, custo das câmaras, vereadores eleitos e, por capital, as linhas das folhas da Câmara e da Prefeitura |
| `dados/portal_transparencia/` | Linhas do presidente, do vice e dos ministros tiradas dos arquivos do Portal (vai para o Git, para o robô só baixar os meses novos) |
| `dados/cache/` | Arquivos baixados. Pode apagar a qualquer momento (não vai para o Git) |
| `dados/brutos/` | Dados de cada fonte, já limpos |
| `dados/processados/` | Base usada pelo site |
| `dados/referencia/` | Tabelas fixas (limites da cota por estado; nome conhecido e sexo dos ministros em `executivo.csv`) |

## A base (`dados/processados/`)

- `politicos.json` — um registro por político: nome, cargo, partido, estado, foto, se está em exercício, link oficial.
- `lancamentos.csv.gz` — (compactado) uma linha por **político · ano · mês · grupo · categoria · descrição · valor · fonte · rateado**.
  A coluna `fonte` é um código; o endereço completo está em `metadados.json` → `fontes_por_lancamento`.
  `rateado=True` marca os valores que a fonte só informa por ano e que dividimos pelos meses (veja abaixo).
- `equipe.csv` — quantas pessoas trabalharam no gabinete em cada mês.
- `resumo.json` — totais prontos: por ano, na legislatura e média mensal, separados em "ganha" e "custa".
- `metadados.json` — data da coleta, categorias, salário mínimo de cada ano, fontes e **pendências conhecidas**.
- `conferencia.md` — resultado da última conferência com os sites oficiais.

### Como o dinheiro é dividido

- **Vai para o bolso** (grupo `ganha`): salário, 13º, auxílios e ajuda de custo.
- **Gastos do mandato** (grupo `custa`): o que o parlamentar gasta com dinheiro público no próprio mandato:
  cota parlamentar (passagens, combustível, alimentação, escritório, divulgação...), diárias e outros gastos.
- **Custo dele** = vai para o bolso + gastos do mandato.
- **Equipe do gabinete** (grupo `equipe`): salários das pessoas que trabalham no gabinete. É dinheiro que vai
  para outras pessoas, por isso fica separado, com o número de pessoas (`equipe.csv`) e a média por pessoa.
  Na Câmara contamos os secretários parlamentares de cada mês; no Senado, os comissionados encontrados na
  folha de pagamento (estimativa).

### Tudo por mês

Para dar para comparar, o site mostra tudo **por mês**:

- Cada média usa os seus próprios meses (com salário, com despesas, com equipe), para uma licença não distorcer a conta.
- Alguns valores só são informados **por ano**: o auxílio-moradia da Câmara e as passagens, correios e outros
  gastos do Senado. Dividimos o total do ano igualmente pelos meses em que o parlamentar recebeu salário
  naquele ano. O total do ano continua exato; o valor de cada mês é uma aproximação (marcado com ≈ no site).
- A cota por tipo (passagens, aluguel de carros, combustível...) aparece como média por mês: o total de cada
  tipo no período dividido pelos mesmos meses da cota no contracheque, com a parte (%) de cada tipo.
  Exemplo: cota de R$ 38.920 por mês, dos quais R$ 12.798 (33%) com aluguel de carros.
- O 13º salário (e, no Judiciário, as férias) é pago de uma vez ou em parcelas, mas na lista "item por item, por mês" todo
  valor é a média por mês do período: o total do período dividido pelos meses do período com pagamento (`mg`; num ano
  inteiro, o 13º do ano ÷ 12; no ano em curso ou num mandato que começou no meio do ano, ÷ os meses que há). Por isso a
  linha se chama "13º salário (média por mês)" e traz embaixo a conta ("R$ 46.366 de 13º pagos em 2025, divididos pelos 12
  meses com pagamento do período") e quando o órgão paga (Câmara: junho e dezembro; Senado e governo federal: o que os
  dados mostram, junho e fim do ano; os outros: "nos meses que o órgão define"). O texto está em `explicaMedia`, no `app.js`;
  o teste do site confere a linha num deputado que recebeu 13º.
- **Pagamento único (ajuda de custo de deputado e senador):** a ajuda de custo é paga de uma vez (na posse, por exemplo; nos
  dados, 1 a 3 salários por ano), e não todo mês. Dividida pelos meses do período, pesaria muito mais em quem teve poucos meses
  (Tiago Dimas, 5 meses em 2025: R$ 46.366 ÷ 5 = R$ 9.273 por mês, contra ÷ 12 de quem teve o ano inteiro) e faria quem entrou no
  meio do ano parecer mais caro: antes, o 1º do ranking de 2025 era um deputado com 5 meses e a ajuda da posse. Por isso a
  categoria `ajuda_de_custo` de `d` e `s` (`UNICOS` e `unicosDe`, no `app.js`; o `gerar.mjs` repete a conta na prévia de cada
  página) **sai do "por mês"** (`resumo`: `gm`, `tm`) e, daí, da mediana, da posição, do selo ▲/▼, do ranking, do "Comparar" e
  do "salários mínimos por mês". Ela aparece à parte: uma linha no topo do contracheque ("Fora desta média: ajuda de custo de
  R$ 46.366, paga de uma vez em set/2025. Contando com ela, seriam R$ 104.990 por mês.") e um bloco "Pago de uma vez, fora
  da média por mês" depois do custo por mês, com o total do período e a conta ("dividido pelos 5 meses, somaria R$ 9.273 por
  mês"). O mês vem do campo `aj` de cada pessoa em `dados.json` (o mês de cada pagamento, como a folha registra: `{"2023": [[202302,
  39293]], "leg": [...]}`; `mesesDoUnico`, no `app.js`): "paga de uma vez em fev/2023"; vários pagamentos, "paga em fev/2023 e jul/2023" (ou
  "paga em N pagamentos", acima de 3); **sem `aj` na pessoa ou no período, o mês é omitido ("paga de uma vez no período"), nunca estimado** (o
  site estimava pelo mês a mês e errava: Lafayette de Andrada, fev/2023, aparecia como dezembro). O mês a mês e o "Custo total no período" continuam como a fonte
  mostra (somam a ajuda). Quem foi ministro e parlamentar ("tudo junto"): só a parte do mandato sai; a ajuda de custo de
  ministro (valores pequenos e mensais, ou uma posse) a fonte não separa e fica como está (em 2025, 1 ministro com 3 meses ou
  mais passa de 0,7 salário). Deputados estaduais e vereadores: sem categoria de pagamento único nos dados (em 2025, só 3 casos
  em cada grupo com `auxilios` ou `outros_rendimentos` acima de 0,7 salário e menos de 12 meses, que podem ser férias ou
  indenização): ficam como estão. Se o `dados` separar uma categoria como "paga de uma vez" em outro grupo, é só pôr a chave em
  `UNICOS` (nos dois arquivos).

## Governo federal (presidente, vice e ministros)

Robô `coleta/executivo.py`, com os arquivos de download do Portal da Transparência (CGU):

- **Quem**: cadastro mensal de servidores (cargos "Presidente da República", "Vice-Presidente da República" e
  "Ministro de Estado"). Só entra quem foi nomeado a partir de 01/01/2023.
- **Vai para o bolso**: remuneração mensal (salário já com o abate-teto, 13º, férias, outras remunerações
  eventuais e verbas indenizatórias) e **jetons** (conselhos de estatais e do Sistema S). O 13º aparece no
  Portal como adiantamento e, no fim do ano, inteiro; contamos uma vez só.
- **Gastos do cargo**: viagens a serviço (diárias + passagens + outros gastos − devoluções), no mês em que a
  viagem começou. As viagens são casadas pelo nome e pelo CPF mascarado que o próprio Portal publica (para não
  confundir homônimos); é o único CPF mascarado guardado no projeto, e só de agentes públicos. Voos da FAB e do avião presidencial não têm custo publicado.
- **Ministro que é deputado ou senador licenciado** (ligação pelo nome civil): nos meses no cargo, entra o
  salário pago pela Câmara ou pelo Senado. As duas páginas têm link uma para a outra.
- **Depois de sair**: quem deixa o cargo pode receber por até 6 meses ("quarentena") e continua no cadastro.
  Esses meses não contam como meses no cargo; o valor fica registrado à parte (`quarentena` em `politicos.json`).
- **Educação com o Portal**: no máximo um download a cada 30 s. Se o Portal pedir verificação humana, o robô
  para de baixar (não tenta contornar) e usa o que já tem; continua na semana seguinte.
- O Portal publica os salários com uns 2 meses de atraso. O arquivo de dezembro de 2024 veio sem os salários.

### Quem tem dois cargos

Ministro que é deputado ou senador tem três páginas, com uma escolha no topo: **Tudo junto**, o cargo no
governo e o cargo no Congresso. O "tudo junto" (`jun-...` em `dados.json`) soma os dois sem contar nada duas
vezes: entra tudo do Congresso (salário, cota, equipe) e, do governo, só o que vem do Portal (jetons,
viagens, outros pagamentos), porque o salário dos meses como ministro já foi pago pelo Congresso. A faixa
embaixo do gráfico mês a mês mostra o cargo de cada mês. Nos rankings, cada cargo aparece no seu grupo.
Cada cargo separado só tem o que a pessoa recebeu naquele cargo: o salário que o Congresso pagou nos meses como
ministro fica só na página de ministro (sai da página de deputado/senador, em `coleta/site.py`). Assim
ministro + parlamentar = tudo junto. Cada opção mostra o custo dele por mês, e o quadro "Como a conta fecha" põe
as três visões lado a lado em totais do período, com os meses de cada cargo.

## Bens declarados na candidatura (TSE)

Robô `coleta/bens.py` (`python3 coletar.py bens`, na rodada do GitHub): os bens que quem está no cargo declarou à
Justiça Eleitoral ao se candidatar, pelo [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br/dataset/candidatos-2022)
(arquivos `bem_candidato_<ano>` e `consulta_cand_<ano>`, licença CC BY, com o crédito, como nas fotos). Eleições
ordinárias de 2022 (deputados federais e estaduais, senadores eleitos em 2022, governadores e vices), 2018 (senadores
eleitos em 2018: o ano e o papel, titular ou suplente, vêm do mandato no Senado) e 2024 (prefeitos, vices e vereadores
das capitais e das cidades do interior que o site mostra com os nomes: CE, PB, ES e PE). Nada de 2026.

- **Ligação com a pessoa**: o mesmo critério das fotos do TSE: o nome civil exatamente igual ao de um único candidato
  do mesmo cargo e lugar (UF; em 2024, também a cidade) ou, sem ele, o nome de urna exatamente igual ao de um único
  candidato. Nos governadores, o nome civil vem do arquivo curado (`civil` ou `folha_nome`). Homônimo ou dúvida fica sem.
- **O que se guarda** (`dados/bens/declaracoes.csv`): o ano, o total, o número de itens e o total por tipo (imóveis,
  veículos, aplicações e depósitos, participações em empresas, outros), pelo código do tipo de bem que o TSE usa; o
  número da candidatura (SQ) e o lugar, para o link da página do candidato no DivulgaCandContas
  (`#/candidato/{REGIÃO}/{UF}/{código da eleição}/{SQ}/{ano}/{UE}`; região sem acento, como CENTROOESTE; UE = a UF em
  2018 e 2022, o código TSE do município em 2024; conferido num navegador em 03/10/2026 com um senador de 2018, um
  deputado federal de GO de 2022 e um vereador de Porto Alegre de 2024). Nunca a descrição de
  cada bem (endereços, contas, nomes de terceiros) nem o CPF: a coluna de CPF do arquivo de candidatos não é lida. Os
  únicos números de 11 dígitos no arquivo são SQs de candidatura. Quem foi ligado a uma candidatura sem bens no arquivo do TSE entra
  com 0 itens. `dados/bens/resumo.json`: quantos no cargo, com declaração e sem, por grupo e motivo.
- **No site, só a partir de 26/10/2026** (regra eleitoral): a etapa `site` só grava `site/dados/bens.json` (quem tem
  página) e `site/dados/bens-interior/<uf>.json` (pela cidade e pelo nome) a partir dessa data. Neutro: sem ranking,
  sem comparação entre pessoas e sem "evolução" entre eleições; autodeclarado na candidatura, em geral pelo valor de
  aquisição, não de mercado.

## Deputados federais e senadores: presença e projetos

Robô `coleta/atividade.py` (`python3 coletar.py atividade`, na rodada do GitHub), só com os dados abertos oficiais da
Câmara e do Senado, desde o início da legislatura (01/02/2023). Sem nota e sem ranking: os números de cada pessoa, com a
fonte. Saída: `site/dados/atividade.json` (por pessoa, `dep-<id>` e `sen-<código>`) e `dados/atividade/` (cada dia de
presença da Câmara, cada voto do Senado só com a situação, e os totais por pessoa, em CSV).

- **Presença na Câmara**: o serviço "ListarPresencasDia" dos dados abertos da Câmara
  (`www.camara.leg.br/SitCamaraWS/sessoesreunioes.asmx`), um pedido por dia com sessão deliberativa no Plenário (os
  dias saem do arquivo anual de eventos; os dias de sessão preparatória, posse e eleição da Mesa, também contam). Para cada deputado em exercício no dia: presença, ausência justificada (com
  o motivo: missão autorizada, licença para tratamento de saúde, decisão da Mesa...) ou ausência. É a conta por dia que
  a Câmara usa. Leva ~10 s por dia: o que já foi lido fica em `dados/atividade/camara-presenca-AAAA.csv`, e a cada
  rodada só os dias novos e os dos últimos 45 dias (a justificativa pode entrar depois) são pedidos de novo. O serviço
  identifica o deputado pela carteira parlamentar; o id dos dados abertos vem da matrícula do serviço "ObterDeputados"
  (é o mesmo número) ou, para quem saiu, do nome e da UF (`dados/atividade/camara-carteiras.csv`, com o jeito de cada
  ligação).
- **Presença no Senado**: os dados abertos do Senado não trazem a presença por sessão. Trazem, em cada votação nominal
  do Plenário (`/dadosabertos/votacao`), a situação de cada um dos 81 senadores em exercício: votou, presente sem
  registrar voto, presidindo, ausente com motivo registrado (atividade parlamentar, missão, licença...) ou não
  compareceu. Por isso, no Senado a conta é por votação nominal, não por dia: não comparar com a Câmara. O sentido do
  voto (sim, não) não é guardado.
- **Projetos**: os que podem virar norma, apresentados desde 01/02/2023: projeto de lei (PL), de lei complementar
  (PLP), proposta de emenda à Constituição (PEC), projeto de decreto legislativo (PDL) e projeto de resolução (PRC na
  Câmara, PRS no Senado). Requerimentos, indicações, emendas e pareceres ficam de fora. Na Câmara, pelos arquivos anuais
  de proposições e de autores (`dadosabertos.camara.leg.br/arquivos/`); no Senado, por `/dadosabertos/processo?codigoParlamentarAutor=`.
  Primeiro autor e coautores contam à parte. Na Câmara, quem só apoia (as assinaturas que a PEC precisa) não conta como
  coautor; no Senado, a PEC lista como autores todos os que assinaram.
- **Virou norma**: a situação "Transformado em Norma Jurídica" da própria Casa (lei, lei complementar, emenda
  constitucional, decreto legislativo ou resolução). Conta só o projeto que virou norma ele mesmo: quando vários
  tramitam juntos, a norma fica com o projeto principal.
- **Homenagem ou data** (regra da ementa, `EMENTA_HOMENAGEM` em `coleta/atividade.py`, a mesma nas duas Casas): projeto
  que dá nome a bem público (rodovia, ponte, aeroporto...), institui data comemorativa (dia, semana, mês, campanha de
  mês com cor, feriado, inclusão em calendário oficial ou turístico), inscreve nome no Livro dos Heróis e Heroínas da
  Pátria, confere título honorífico (capital nacional, patrono, símbolo), institui prêmio, medalha ou diploma, reconhece
  utilidade pública ou declara patrimônio ou manifestação cultural. Os demais ficam em "os demais projetos". Conferida
  com o tema "Homenagens e Datas Comemorativas" que a própria Câmara dá às proposições (projetos de 2023 a out/2026):
  dos 1.776 com esse tema, a regra marca 1.489 (84%); dos 1.559 que a regra marca, 1.489 (96%) têm o tema. A diferença
  vem sobretudo de selos, campanhas e símbolos que a Câmara põe no tema e a regra deixa de fora, e de projetos que
  ainda não têm tema.
- **Conferência** (03/10/2026, 5 deputados e 5 senadores): ver a seção "O que já foi conferido".

## Câmaras municipais (vereadores), passo 1

Robô `coleta/municipios.py`, para as 5.569 câmaras:

- **Custo da Câmara**: Declaração de Contas Anuais (Siconfi, Tesouro Nacional), função "01 - Legislativa" menos
  "01.032 - Controle Externo" (tribunal de contas do município, só em SP e no Rio), despesas liquidadas. Uma
  consulta por cidade; os resultados ficam em `dados/municipios/camaras_custo.csv` (vai para o Git) e o robô só
  consulta as que faltam. Cidade que não entregou é tentada de novo depois de 30 dias; sem o ano mais recente,
  vale o anterior.
- **Vereadores eleitos em 2024**: arquivo de candidatos do TSE (código do TSE ligado ao do IBGE pelo nome da
  cidade; 13 nomes escritos diferente estão numa tabela no código). Suplentes que assumiram depois ainda não
  aparecem.
- **Teto do salário do vereador**: Constituição, art. 29, VI (20% a 75% do salário do deputado estadual, que é
  no máximo 75% do federal), pela população.
- **Salário médio da cidade**: o salário médio mensal do pessoal assalariado das empresas e outras organizações
  formais (inclui órgãos públicos), em reais, do Cadastro Central de Empresas do IBGE (tabela 9509 do SIDRA, ano mais
  recente: 2024), para pôr ao lado do teto do vereador. Uma consulta só para os 5.570 municípios do IBGE
  (`dados/municipios/salario_medio.csv`; a conta do IBGE inclui Brasília e Fernando de Noronha, que não têm Câmara
  Municipal e não estão no `municipios.json`, e ainda não tem Boa Esperança do Norte (MT), instalada em 2025), de
  novo a cada 30 dias. No `municipios.json` é o 9º campo de cada cidade.
  No site, a comparação com o salário médio (quanto acima, e o "ganha mais que X% dos brasileiros que trabalham") só
  aparece onde há o salário de verdade do vereador (as capitais com vereador por vereador). Nas outras cidades, o teto e
  o salário médio ficam lado a lado, sem comparação: o teto é só o máximo, e o salário fixado pela Câmara pode ser menor.
- **Valor suspeito**: custo por habitante abaixo de 30% da mediana das cidades do mesmo tamanho (46 cidades).
  Provavelmente parte do gasto foi informada em outra função; a cidade aparece com aviso e fica fora das
  comparações.
- O salário de cada vereador ainda não tem fonte nacional. Próximos passos: capitais (um robô por câmara) e os
  estados cujo tribunal de contas publica a folha.

## Vereadores das capitais, passo 2

Robô `coleta/vereadores/` (`python3 coletar.py vereadores`; `vereadores_sp` é o nome antigo e faz o mesmo). Um
arquivo por cidade (`sp.py`, `fortaleza.py`, `goiania.py`, `manaus.py`, `natal.py`, `recife.py`): `coletar()` baixa
os dados abertos da Câmara e grava em `dados/municipios/<cidade>/` (vai para o Git); `montar()` entrega tudo no
formato comum (`comum.py`), e o robô junta as cidades em `site/dados/camaras.json`. Uma cidade que falhar não
derruba as outras: o site segue com o que já estava gravado. Vereador só se compara com vereador da mesma cidade
(o grupo do ranking é o tipo mais o código IBGE, como `v2611606`). O que cada Câmara publica é diferente:

| Cidade | Quem estava no cargo | Vai para o bolso | Verba do gabinete | Equipe |
|---|---|---|---|---|
| São Paulo | SPLegis (gabinetes, com datas) | subsídio, pelos dias no cargo | nota por nota (SisGV) | pessoas e cargos |
| Fortaleza | folha mensal (API da Câmara) + SAPL | subsídio do mês, pela folha | SDP, nota por nota | não ligada ao gabinete |
| Goiânia | folha mensal (NúcleoGov) | folha bruta (subsídio + 1/3, 13º, férias) | CEAP, por tipo | pessoas, cargos e custo |
| Manaus | folha mensal + SAPL | subsídio, pela folha | CEAP, nota por nota | pessoas, cargos e custo |
| Natal | lista mensal da cota (29 por mês) + SAPL | subsídio fixado (R$ 26 mil) | cota, nota por nota | não publicada |
| Recife | folha mensal (CSV) + e-Processo | folha bruta (subsídio, 13º, 1/3 de férias) | Verba Indenizatória, por tipo | pessoas, cargos e custo |
| Aracaju | folha mensal (planilha; o PDF quando a planilha vem vazia) | valor bruto da folha | VAEP em PDF de imagem: ainda fora | lotação genérica ("gabinete de vereador"): não ligada ao gabinete |
| Boa Vista | quadro mensal da verba de cada vereador (PDF) | subsídio fixado (R$ 20.864,78, Resolução 253/2023) | verba indenizatória, por tipo (o total é o "total pago" do quadro) | não publicada |

- Nome civil, gênero e partido: TSE (eleição de 2024); os nomes são casados entre as fontes com tolerância a
  abreviações e erros de digitação (`comum.semelhanca`).
- O CPF dos assessores não é guardado, e os descontos da folha (como empréstimos) não são lidos.
- Teresina e João Pessoa: as Câmaras mudaram de endereço (teresina.pi.leg.br e joaopessoa.pb.leg.br). Os endereços
  antigos não respondem, e o robô tratava a falta de robots.txt como proibição (RFC 9309): não há proibição, os robôs
  ficam a fazer com os endereços novos. Palmas e Curitiba publicam em sistemas em JavaScript (NúcleoGov e prodata; Betha Cloud), ainda a fazer.
- SAPL de Fortaleza e de Natal: o robots.txt pede 60 s entre pedidos, então só pedimos a lista de mandatos e,
  em Fortaleza, no máximo 6 fotos por semana.
- Fotos: as da Câmara Municipal; quem está no cargo sem foto da Câmara recebe a foto da candidatura de 2024 no TSE
  (`coleta/fotos_tse.py`: Portal de Dados Abertos do TSE, licença Creative Commons Atribuição), quando o nome civil (ou,
  sem ele, o nome de urna) é exatamente o de um único candidato a vereador da cidade. O crédito fica em `site/fotos/creditos.json`.
- Recife: em ago/2026 a folha traz também R$ 18.980 (o salário da legislatura passada) a vereadores e
  ex-vereadores daquela legislatura; não entram. A página da verba de alguns vereadores dá erro no site da
  Câmara: o site avisa e mostra a verba zerada nesse período. Quando a página de um ano ou de um vereador dá erro, o
  robô mantém as linhas que já tinha gravado (em 02/10/2026 a Câmara deu erro para todos, o arquivo da verba ficou vazio
  e a cidade saiu do site por algumas horas; corrigido no mesmo dia).
- Goiânia: a folha mensal paga um terço a mais que o subsídio, sem nome para essa parcela; mostramos o subsídio
  como salário e o terço como "outros pagamentos".

### São Paulo

Cada vereador da capital tem página própria
(`#ver-3550308-{código}`), como os deputados: contracheque, mês a mês, detalhe dos gastos, equipe, colegas e
ranking, comparar e imagem para compartilhar. A página da cidade (`#cid-3550308`) lista os 55, com link, e também a Prefeitura.

- **Quem ocupa cada gabinete** (titulares e suplentes, com datas): SPLegis, `OcupacaoGabineteJSON`. Partido do
  mandato: `VereadoresCMSPJSON`. Nome de urna, nome completo e gênero: TSE (guardado em
  `dados/municipios/sp/candidatos_tse.csv`, só eleitos e suplentes, sem CPF). Quem ficou menos de 15 dias no
  cargo e já saiu não ganha página.
- **Vai para o bolso**: o subsídio, igual para todos (R$ 24.754,79 em jan/2025; R$ 26.080,98 desde fev/2025),
  proporcional aos dias no cargo. A Câmara só mostra o contracheque com CPF: 13º e descontos ficam de fora.
- **Gastos do mandato**: a verba do gabinete (Auxílio-Encargos Gerais de Gabinete), nota por nota, do SisGV
  (`ObterDebitoVereadorJSON`, SOAP), e o crédito mensal (`ObterCreditoVereadorJSON`); o saldo que sobra em
  dezembro volta para a Câmara. Tipos de despesa com nomes curtos e os 8 maiores fornecedores; CPF de pessoa
  física (aluguel de imóvel) não é guardado, nem mascarado, e o nome não aparece no site. Os 4 últimos meses são baixados de novo
  toda semana, porque ainda recebem notas. O último mês é o último fechado.
- **Equipe**: pessoas e cargos de cada gabinete, pela lista de funcionários da Câmara (retrato do mês mais
  recente). O custo da equipe não é publicado sem CPF.
- **Fotos**: oficiais, do site da Câmara (que declara o banco de imagens livre para uso), com crédito.
- Saída: `dados/municipios/sp/*.csv` (vai para o Git) e `site/dados/camaras.json`, que o site junta à lista de
  políticos ao abrir (se o arquivo faltar, o site segue sem os vereadores). Conferência: 55 no cargo e verba
  usada dentro do crédito do ano. Em 2025, a verba usada de cada um confere com o crédito menos o saldo devolvido
  em dezembro (57 de 59 vereadores com diferença de até R$ 2; os outros 2, menos de R$ 500).

## Prefeituras das capitais

Robôs em `coleta/prefeituras/` (`python3 coletar.py prefeituras`; `prefeitura_sp` é o nome antigo): prefeito, vice e
secretários municipais (e os subprefeitos, em São Paulo), mês a mês desde jan/2025, pela folha de pagamento que cada
Prefeitura publica com o nome de cada servidor. Cada cidade é um módulo com `coletar()` (baixa a folha e guarda só
as linhas desses cargos em `dados/municipios/<cidade>/prefeitura_remuneracao.csv`, que vai para o Git) e `montar()`
(transforma em linhas comuns: mês, cargo, nome, pasta, salário, 13º, outros, bruto, "cedido"). O `comum.py` faz o
resto para todas: junta a mesma pessoa escrita de jeitos diferentes, acha o nome de urna e o partido do prefeito e
do vice (TSE), liga quem também é vereador da cidade à página de vereador, separa os acertos do mês da saída e busca
as fotos (Wikimedia Commons; para quem sobrar, a foto da candidatura de 2024 no TSE, quando o nome civil é exatamente o de
um único candidato a prefeito, vice ou vereador da cidade). Uma cidade fora do ar não para as outras: o site usa o que já estava gravado.

| Cidade | Fonte | O que a folha dá |
|---|---|---|
| São Paulo | Portal de Dados Abertos, "Histórico de Remuneração dos Servidores Ativos" (CSV de ~21 MB por mês; exceção ao robots.txt, ver "Robôs e robots.txt") | Remuneração do mês + "demais elementos" (13º, férias, auxílio-refeição, atrasados). Cedido: exceções 2 e 3 |
| Recife | Dados Abertos do Recife, "Servidores e salários" (um CSV de ~85 MB por ano, lido aos poucos e filtrado pela função) | Proventos, férias e 13º ("natalina"). R$ 0 no mês = recebe de outro órgão |
| Fortaleza | Dados Abertos de Fortaleza, `relacao_AAAAMM.csv` (~24 MB por mês) | Só o total dos proventos: o que passa do normal da pessoa vira "outros". Menos de 30% do normal do cargo = recebe de outro órgão |
| Vitória | Dados Abertos de Vitória, conjunto "Pessoal" (API do portal, uma tabela por mês) | Só a remuneração bruta total. Quadro "cedido por outros órgãos" = recebe de outro órgão |
| Porto Alegre | Portal Transparência (Procempa), "Remuneração dos servidores": a pesquisa do mês e o CSV da pesquisa, como o botão do site | Remuneração básica, abate-teto, 13º (folha "natalina" de dezembro), férias, eventuais e jetons |
| Salvador | Portal da Transparência, "Remunerações": a API pública da página (lista do mês filtrada pelo cargo e o detalhe de cada pessoa) | Remuneração básica, 13º, férias e abate-teto (verbas indenizatórias à parte, fora do bruto). Vínculo "regime especial outra esfera" = recebe de outro órgão |
| Curitiba | Portal da Transparência, "Remuneração dos Servidores": o CSV do mês inteiro, como o botão "Exportar para CSV" | Só o total bruto do mês: o que passa do normal da pessoa vira "outros". Só entra quem tem o cargo "secretário" na lista (o secretário de carreira que recebe pelo cargo de origem não aparece como secretário). Remuneração zero = recebe de outro órgão |
| Natal | Natal Transparente, "Servidores - Folha de Pagamento": a pesquisa por cargo e o contracheque de cada pessoa | Subsídio ou cargo em comissão, 13º, férias, rescisão e o "jeton indenizatório" mensal (Lei 7.274/2021). Sem contracheque no mês = recebe de outro órgão |
| Campo Grande | SIG Transparência, "Consultar Remuneração dos Servidores": a pesquisa por cargo e mês, com o botão "Download JSON" | Só a remuneração bruta do mês. De jan a mai/2025 o cargo vem vazio na consulta: os dados começam em jun/2025 |
| Rio de Janeiro | "Consultar Remuneração do Servidor": a base mensal em CSV (`contrachequedoc.rio.gov.br/repositorio/ArquivoTCAAAAMM.csv`, ~21 MB) | Bruto por tipo de folha (normal, 13º, suplementos, rescisão) e abate-teto. O arquivo não diz o cargo: só entram o prefeito e o vice, pelo nome (eleitos de 2024) |

- **Vai para o bolso** = remuneração bruta da folha. Os acertos do mês da saída (acima do normal da pessoa, a partir
  de R$ 3 mil) ficam à parte e fora das médias. As prefeituras não publicam gastos por pessoa.
- **Pasta**: a folha diz o órgão de lotação, que nem sempre é a pasta. Siglas viram nomes por tabelas no código de
  cada cidade (conferidas nos sites das prefeituras e na imprensa); o que não se sabe fica como está. Em Fortaleza,
  os secretários regionais aparecem todos lotados na Secretaria de Governo (a Secretaria da Gestão Regional foi
  extinta em 2025): o site diz "secretário municipal, lotado na Secretaria Municipal de Governo".
- Vice que também é secretário (Recife, Fortaleza) aparece com um cargo só ("Vice-prefeito e secretário de ...").
- Nada de CPF: quando a fonte traz o CPF mascarado, ele não é guardado.
- **Belo Horizonte** publica a folha nominal, mas o portal bloqueia acessos automáticos (WAF): não tentamos
  contornar. **João Pessoa** também (Incapsula). **Macapá**: a folha nominal fica num portal de
  terceiro (Portal CR2, feito em Bubble), sem arquivo para baixar; fica para depois.
- Saída: `site/dados/prefeituras.json`, que o site junta à lista de políticos (tipo `p`), com as notas de cada cidade.

## Deputados estaduais

Robôs em `coleta/assembleias/` (`python3 coletar.py assembleias`), um por Assembleia, no mesmo formato dos vereadores
das capitais (`vereadores/comum.montar`, com `id_prefixo` "est", `k` "e" e o cargo "Deputado/Deputada estadual"):
salário, verba com fornecedores, mês a mês desde jan/2025. Saída: `site/dados/assembleias.json` (como o
`camaras.json`, com `meta.estados` no lugar de `meta.cidades`; id `est-<código IBGE da UF>-<número>`).

| Estado | Fonte | O que entra |
|---|---|---|
| Minas Gerais | Dados abertos da ALMG (`dadosabertos.almg.gov.br/ws/`; exceção ao robots.txt, ver "Robôs e robots.txt"): deputados em exercício e que saíram, e a verba indenizatória de cada deputado e mês | Subsídio da lei (Lei 24.266/2022); verba indenizatória nota a nota (emitente, CNPJ, documento, valor reembolsado). Quem está no cargo: a situação na ALMG (em exercício; para quem saiu, a data da renúncia ou do fim da suplência). O site vai até o último mês em que 80% dos deputados já prestaram contas |
| Rio de Janeiro | DOCIGP, o portal da verba da Alerj (exceção ao robots.txt): o orçamento mensal de cada gabinete e os lançamentos publicados; a página "Quem são" do site da Alerj | Subsídio da lei (Lei 11.074/2025), desde fev/2025; lançamentos de débito um a um (centro de custo, fornecedor, CNPJ, documento), sem o saldo que passa de mês, os créditos e a devolução do saldo. Quem está no cargo e o partido de hoje: a página "Quem são" (70); desde quando: os meses com orçamento. O site vai até o último mês em que 80% dos gabinetes já foram publicados |
| São Paulo | Dados abertos da Alesp: `deputados.xml` e `despesas_gabinetes_AAAA.xml` | Subsídio da lei (Leis 17.617/2023 e 18.384/2025); verba de gabinete por mês, tipo e fornecedor (a Alesp soma as notas do mesmo fornecedor no mês) |
| Bahia | Transparência da ALBA: a lista de deputados e a planilha mensal da verba (botão Excel) | Subsídio da lei (Lei 14.532/2023), desde fev/2025; verba indenizatória processo por processo, por categoria (o fornecedor só está na página de cada processo, ainda fora) |
| Pernambuco | Portal da Transparência da Alepe: a lista de dados abertos e o que a página usa (prestações da verba e as notas de cada uma) | Subsídio da lei (Lei 18.138/2023); verba indenizatória nota a nota (rubrica, CNPJ, empresa, valor). As notas chegam aos poucos (no máximo 400 prestações por vez) |
| Ceará | Portal da Transparência da Alece: CSV mensal da folha de pagamento (categoria "DEPUTADOS") e CSV mensal da VDP | Salário e 13º da folha (remuneração bruta menos abate-teto; sem descontos pessoais); Verba de Desempenho Parlamentar empenho por empenho, com credor e CNPJ. Quem esteve no cargo: quem está na folha do mês; hoje, a página de deputados da Alece (o licenciado continua na folha e a página o marca) |
| Paraíba | Portal da Transparência da ALPB: a planilha ODS dos eletivos da folha de cada mês | Subsídio da folha e a VIAP paga na folha (só o total do mês, sem fornecedores; as notas saem num arquivo por deputado). Jul/2025 sem planilha: vale o subsídio da lei. Quem está no cargo: a planilha do mês; quem recebeu só parte do subsídio no último mês, depois de um mês inteiro, saiu nesse mês |
| Rondônia | Portal da Transparência da ALE-RO: a página da verba indenizatória por gabinete e mês | Subsídio da lei (Lei 5.530/2023); verba nota a nota (prestador, CNPJ, classe), mais os reembolsos de saúde (só o valor). Quem esteve no cargo: os meses com prestação; hoje, a lista de deputados do site da ALE-RO (a lista de gabinetes da página da verba guarda o gabinete do suplente depois que o titular volta) |
| Goiás | Portal da Transparência da Alego: o que a página usa (meses publicados, deputados com prestação no mês e a prestação de cada um) | Subsídio da lei (Lei 17.253/2011, redação da Lei 21.780/2023); verba indenizatória nota a nota (valor indenizado, fornecedor, CNPJ). Quem esteve no cargo: deputados com prestação no mês; hoje, a página "Deputados em Exercício" do site da Alego menos quem tem afastamento em aberto (licença, falecimento) em "Deputados fora do exercício", com a data. O titular sem afastamento publicado conta como no cargo nos meses sem prestação |
| Santa Catarina | Portal da Transparência da Alesc: CSV anual dos gastos dos gabinetes; a lista de deputados do site da Alesc para quem está no cargo hoje (a do Portal da Transparência é a da folha do mês e traz também o titular licenciado que continua recebendo: o subsídio dele continua) | Subsídio da lei (Lei 18.642/2023); diárias, passagens, telefone, veículos, aluguel e reembolsos do gabinete (sem CNPJ; nas diárias e passagens, sem o nome da pessoa) |
| Mato Grosso do Sul | Portal da Transparência da Alems: CSV anual da CEAP | Subsídio da lei (Lei 6.016/2022); CEAP nota a nota, com CNPJ e comprovante. Sem lista de deputados aberta: quem está no cargo sai dos meses com notas. Partido: o da candidatura de 2026 no TSE |
| Tocantins | Portal da Transparência da Aleto: a pesquisa da Verba Indenizatória (CODAP), que devolve um PDF por deputado e mês | Subsídio da lei (Lei 4.073/2022); CODAP nota a nota (emitente, CNPJ, valor), lida do PDF. O PDF não tem a categoria: ela sai do nome do emitente (posto, hotel, escritório de advocacia...). O total do mês é o valor ressarcido do PDF. A folha tem hCaptcha e não entra. Quem está no cargo: a lista de deputados da página |
| Sergipe | Portal da Transparência da Alese: o PDF mensal da folha de pagamento e o PDF mensal do ressarcimento dos deputados | Rendimentos da folha (subsídio, "outras verbas", 13º, auxílio; sem descontos nem líquido); ressarcimento por deputado e categoria (sem fornecedor), no mês da competência; equipe do gabinete (pessoas lotadas e soma dos rendimentos, sem nomes). Quem está no cargo: quem está na folha |
| Espírito Santo | Portal da Transparência da Ales (só abre do Brasil: entra na rodada do Brasil): o que a página das cotas parlamentares usa, por gabinete e mês | Subsídio da lei (Lei 11.766/2022), desde fev/2025; cota por rubrica (diárias, passagens, divulgação, consultorias, aluguel), sem fornecedor. Quem está no cargo: os meses em que a página tem a tabela do gabinete (o titular licenciado fica sem tabela) |
| Rio Grande do Sul | Portal da Transparência da ALRS (só abre do Brasil: entra na rodada do Brasil): o que as páginas "Gastos | Cotas" e "Remuneração de Servidores e Parlamentares" usam | Folha de cada deputado (remuneração bruta, parcelas indenizatórias, terço de férias, 13º; sem descontos), pela busca do nome completo do TSE; cota por gabinete, mês e rubrica (sem fornecedor). Quem está no cargo: os meses na folha (o titular licenciado sai da folha, mas o gabinete continua na lista de cotas e a cota fica no nome dele); hoje, a lista de deputados do site da ALRS |
| Amapá | Portal da Transparência da Alap (só abre do Brasil: entra na rodada do Brasil): o que as páginas da CEAP e da consulta remuneratória de deputados usam | Folha de cada deputado (subsídio, GFE, auxílio-alimentação; sem descontos); CEAP por gabinete e mês, nota a nota (CNPJ, empresa, nota, valor). Quem está no cargo: os gabinetes da CEAP do mês (e, para quem não tem gabinete, os meses na folha); hoje, a lista de parlamentares da página inicial da Alap |
| Distrito Federal | Dados abertos da CLDF (CKAN; só abre do Brasil: entra na rodada do Brasil): o CSV mensal do quadro demonstrativo de pessoal; o quadro mensal consolidado da verba indenizatória (PDF) | Folha de cada deputado (subsídio, 13º, auxílios, acertos; sem descontos); verba por deputado, mês e categoria (sem fornecedor); equipe do gabinete (pessoas lotadas no gabinete e a soma dos rendimentos, sem nomes). Quem está no cargo: quem está na folha do mês. Fev/2026: o arquivo publicado é cópia do de jun/2025, e vale o subsídio da lei (Decreto Legislativo 2.383/2022) |
| Amazonas | Portal da Transparência da Aleam (só abre do Brasil: entra na rodada do Brasil): o CSV do botão "Exportar para CSV" da página da cota parlamentar, por deputado e mês | Subsídio da lei (Lei 4.729/2018, ratificado pela Lei 8.161/2026); CEAP nota a nota (beneficiário, CNPJ, verba, valor reembolsado). A consulta de vencimentos nominal não devolve resultado. Quem está no cargo: os meses com resumo da CEAP |
| Maranhão | Portal da Transparência da Alema (só abre do Brasil: entra na rodada do Brasil): a consulta de verbas por competência e a página de cada deputado no mês | Subsídio da lei (Lei 11.876/2023); CEAP por deputado, mês e inciso (sem fornecedor), pelo valor ressarcido (o que passa dos limites aparece à parte). Quem está no cargo: os meses em que o deputado aparece na consulta. O site vai até o último mês em que 80% dos deputados já prestaram contas |
| Paraná | Portal da Transparência da Alep: o que as páginas "Parlamentares" e "Comissionados" usam e a exportação da "Consulta de despesa" (pagamentos do SIAFIC) | Folha de cada deputado (subsídio, 1/3 de férias, vantagens transitórias, benefícios, menos o redutor; sem descontos); verba de ressarcimento pelos pagamentos ao próprio deputado, por natureza e mês do pagamento (sem fornecedor: as notas estão na consulta com reCAPTCHA, que não é lida); equipe: comissionados lotados em cada gabinete (sem custo). Quem está no cargo: os gabinetes com comissionados no mês (o titular licenciado continua na folha) |
| Rio Grande do Norte | Lista de deputados do sistema legislativo da ALRN (Transparência Legislativa) e a página de deputados | Subsídio da lei (Lei 11.315/2022). Verba e folha não entram: a API do Portal da Transparência exige autenticação e não é usada. Quem está no cargo: a lista atual (24), desde jan/2025; partido: a filiação em vigor na ALRN |
| Piauí | Portal da Transparência da Alepi: as consultas da verba indenizatória e da remuneração | Folha de cada deputado pela busca do nome (subsídio, gratificação, férias, 13º; sem previdência e IR); verba indenizatória nota a nota, por subcota (o fornecedor só está no PDF de cada nota). Quem está no cargo: os meses com notas da verba (o licenciado continua na folha). O site vai até o último mês com a verba de 80% dos deputados |
| Pará | Portal da Transparência da Alepa: o JSON do painel da verba indenizatória e o que as páginas "Remuneração de Pessoal", "Relação de Pessoal" e "Verba de Gabinete" usam | Folha de cada deputado pela matrícula (remuneração, férias, 13º adiantado, pecúnia, menos o redutor; sem descontos); verba indenizatória e indenização de transporte por mês (sem fornecedor; o imposto retido volta para o valor do auxílio); equipe: assessores e total pago por gabinete, desde abr/2026. Quem está no cargo: os meses com verba ou gabinete (o licenciado continua na folha) |
| Acre | Portal da Transparência da Aleac: a lista de servidores (cargo "Deputado estadual"); a página Deputados do site da Aleac | Subsídio da lei (Lei 4.136/2023), proporcional aos dias no cargo. A consulta da folha não traz valores e a verba não é publicada por deputado. Quem está no cargo: admissão e exoneração na lista de servidores (a lista não mostra licenças: até 09/03/2026, 25 deputados para 24 vagas) |
| Alagoas | Portal da Transparência da ALE-AL (só abre do Brasil: entra na rodada do Brasil): a relação nominal da folha, letra por letra, e o detalhe de cada deputado | Folha de cada deputado (subsídio, vantagens, indenizações e vantagens eventuais, menos o abate-teto; sem descontos). A VIAP sai em formulário escaneado, com o total corrigido à mão, e fica de fora. Quem está no cargo: quem está na folha do mês com subsídio (em ago e set/2026, 28 subsídios para 27 cadeiras; a ALE-AL não publica a lista de quem está em exercício, e o sistema legislativo marca como ativos também deputados que já saíram) |
| Roraima | Portal da Transparência da ALE-RR: o que as páginas da verba indenizatória e de gestão de pessoal usam (arquivos por pasta) | Folha (total de proventos e 13º) de jan a set/2025; depois, o subsídio da lei (Lei 1.789/2023). Verba por deputado e item desde set/2025 (sem fornecedor; o que passou da cota entra negativo). Equipe: pessoas no setor "GAB DEP" de cada mês (sem custo): comissionados, cedidos por outros órgãos e o gabinete regional (em ago/2026, 1.918 pessoas nos 25 gabinetes, mediana de 80; é o que a planilha de servidores mostra). Quem está no cargo: a folha e os meses com a verba |
| Mato Grosso | Portal da Transparência da ALMT (Elotech): o que a página de servidores usa | Folha de cada deputado (subsídio, auxílio saúde, 13º; sem descontos); equipe lotada no gabinete ("GAB DEP"), com a soma dos vencimentos. Verba não publicada por deputado. Quem está no cargo: admissão e exoneração de cada matrícula, sem os meses sem subsídio (o titular licenciado) |

- Nome civil, gênero e eleito/suplente: arquivo de candidatos de 2022 do TSE (`consulta_cand_2022.zip`, ~4 MB, no
  cache). O nome parlamentar é casado com o nome de urna (igual, compatível ou, por último, o único eleito com as
  mesmas palavras, sem títulos como "Dr." ou "Cel.").
- As 27 Assembleias têm robô desde 02/10/2026. O que cada uma publica (verba, folha, equipe, subsídio, barreiras) está
  em `dados/referencia/assembleias.json`; onde falta uma parte, o motivo está na tabela acima. Sem folha aberta, vale o
  subsídio da lei (como em SP e MG); a verba não entra em 4 (RN, AC, AL e MT).
- Deputado licenciado (secretário de Estado, por exemplo) costuma continuar na folha da Assembleia (PR, PI, PA, CE, SC):
  estar na folha não é estar no cargo, e o robô usa outro sinal (gabinete com comissionados, notas da verba).
- Quem está no cargo hoje: onde a Assembleia publica no próprio site a lista de quem está em exercício (CE, SC, RO, RS,
  AP, GO), ela decide (`em_exercicio.csv` na pasta do estado, refeito a cada coleta; `assembleias/comum.aplicar_hoje`).
  A folha e a verba continuam dizendo desde quando e quanto. Fora da lista: o período fecha no último mês com dados (ou
  na data que a Assembleia publica, em GO); se a pessoa continua recebendo (o licenciado na folha do CE e de SC), o
  período segue e só o "no cargo" muda (`fora_hoje`). Na lista e sem dados nos últimos meses: continua no cargo.
- CPF solto em texto (nome de fornecedor MEI, histórico do pagamento) sai depois de cada coleta
  (`vereadores/comum.limpar_cpfs`, também para as capitais).
- No site, o deputado estadual é o tipo `a` (Assembleia): o `app.js` e o `gerar.mjs` trocam o `k` "e" do arquivo, que no
  site é o governo federal. A página de cada um é a mesma do vereador (salário, verba do gabinete mês a mês, para onde
  foi o dinheiro, equipe onde a Assembleia publica, as notas e as fontes de `meta.estados[uf]`), e ele só se compara com
  os colegas da mesma Assembleia. O endereço é o do `site/dados/enderecos.json`; enquanto não houver nome lá, o próprio
  id (`/est-35-300607`), com página pronta para o Google e o WhatsApp. Quando o nome entrar, o id vai para `antigos`
  (vira redirecionamento), para os links já compartilhados continuarem valendo. A página do estado
  (`/governador/sp#assembleia`) tem a seção "Assembleia Legislativa": o salário, o custo típico, a verba usada, o
  último mês com dados, a lista de quem está no cargo e de quem saiu, como a Assembleia publica, e o ranking dos
  deputados do estado; estado ainda sem os dados mostra só o aviso e o link para o Índice. Na busca, no ranking
  ("Deputados estaduais", um estado de cada vez), no guia, em "Ver por estado" e nos números da abertura, também.
  Partido em branco na fonte (MS e outros, onde vem da candidatura de 2026) aparece só com a sigla do estado, sem
  "sem partido".
- Fotos: primeiro a foto da candidatura de 2022 no TSE (Portal de Dados Abertos do TSE, licença Creative Commons Atribuição,
  `foto_cand2022_<UF>_div.zip`, lido por pedaços: só as fotos que faltam), quando o nome civil do deputado é exatamente o de
  um eleito ou suplente da UF; depois, para quem sobrar, o Wikimedia Commons, pelas mesmas regras do governo federal (no
  máximo 40 buscas por vez).

## Governadores

Robô `coleta/governadores.py` (`python3 coletar.py governadores`). Não há fonte nacional: o salário (subsídio) do
governador e do vice é fixado por lei em cada estado, e cada Estado publica a folha do seu jeito. A base é um arquivo
mantido à mão, `dados/governadores/governadores.json`, montado estado por estado, com o link de cada valor:

- `subsidio`: uma linha por valor (cargo `gov`, `vice` ou `sec`, mês em que passou a valer, valor bruto, norma,
  link e **confiança**: `lei`, `folha` = conferido na folha do Estado, `tabela` = tabela oficial de remuneração,
  `calculado` = conta nossa a partir da lei, `imprensa` = só a imprensa).
- `ocupantes`: quem foi governador, vice ou governador em exercício desde 2023, com datas, partido e observações
  (em 2026, 11 governadores deixaram o cargo para disputar a eleição; o Rio e Roraima têm governadores interinos).
- `folha`: se a folha nominal do Estado abriu para o nosso robô (`aberta`, `painel` Power BI, `token`, `bloqueada`,
  `suspensa` pelo período eleitoral) e o que ela mostrou; `recebe`: quem recebe outra coisa no lugar do subsídio
  (a governadora de Pernambuco recebe como procuradora do Estado).
- `notas`: o que precisa ser explicado.

O robô confere o arquivo (27 estados, um governador no cargo por estado, valores e datas plausíveis, link em cada
valor; se algo estiver errado, a etapa falha), escolhe o valor em vigor e gera `site/dados/governadores.json`.
As fotos do governador e do vice vêm da candidatura de 2022 no TSE (Portal de Dados Abertos do TSE, licença Creative
Commons Atribuição; nome civil ou de urna exato, entre os candidatos a governador, vice, senador e deputado da UF) ou,
sem ela, do Wikimedia Commons (licença livre, com crédito).

**Para atualizar**: quando sair uma lei nova, acrescente uma linha em `subsidio`; quando mudar o governador, feche a
linha dele em `ocupantes` (`ate`) e abra outra (com `folha_nome`, o nome como aparece na folha, nos estados em que a
busca é pelo nome).

No site, a página do estado (`/governador/sp`, `secGovernador` no `site/app.js`) começa pelo governador: o salário, de
onde vem o valor e a comparação com os outros 26 (a posição, a mediana e um gráfico em que cada ponto é um estado; tocar
num ponto abre aquele estado). Depois vêm o vice e o secretário de Estado, num bloco próprio (o salário deles sai da
mesma lei e a folha traz os dois, mas a página é do governador), o mês a mês da folha (governador ou vice), a história
dos valores, a Assembleia Legislativa e, no fim, a lista dos 27 governadores.

Cada governador e vice desde 2023 tem também a sua página (`/tarcisio-de-freitas`, pelo endereço de
`site/dados/enderecos.json`; quem foi vice e virou governador tem uma página só), no formato das da Prefeitura: o que
vai para o bolso, mês a mês, desde jan/2025. O `publicacao/gerar.mjs` monta essas pessoas (`pessoasGovernadores`, com
`k: "g"`) a partir de `e.oc` e `e.m`: onde a folha do Estado abre, o que ela pagou (o salário é o recebido menos o 13º,
as férias, os auxílios e os outros pagamentos; onde a folha não separa as partes, o mês fica num item só); o mês da
saída, com os acertos, fica fora das médias e do mês a mês, como na página do estado. No Amapá, em Mato Grosso e no
Tocantins (sem folha), é o salário oficial do cargo (`e.h`) pelos dias no cargo, marcado como "não é o que foi pago" e
fora das comparações. A posição compara com os outros governadores (ou vices) no mesmo período; quem teve os dois
cargos num ano fica fora da comparação daquele ano. Quem governa em exercício sem aparecer na folha (Ricardo Couto, no
Rio, pago pelo Tribunal de Justiça) tem a página com as notas do estado e sem valores. Na página do estado, o nome do
governador, do vice e de quem governou desde 2023 leva à página de cada um.

### Governadores mês a mês (folhas dos estados)

Robôs em `coleta/folhas_estaduais/`, um por estado, rodados pela etapa `governadores`: o que o governador, o vice e
quem governou interinamente receberam em cada mês desde jan/2025, pela folha de pagamento com o nome de cada servidor.
Cada estado grava `dados/governadores/folha/<uf>.csv` (vai para o Git; só os meses que faltam e os últimos de novo).

| UF | Fonte | Como |
|---|---|---|
| AC | Portal de Transparência, "Servidores" | Busca pelo nome e detalhamento de cada folha (normal, adiantamento do 13º, rescisão), com as rubricas |
| DF | Portal da Transparência do DF | API por nome e mês (subsídio, benefícios, verbas eventuais, reposições) |
| ES | Dados abertos, "Portal da Transparência - Pessoal" | CSV mensal de 85-195 MB, uma linha por rubrica, lido aos poucos |
| MG | Dados abertos, "Remuneração dos servidores ativos" | CSV mensal de ~130 MB (dois leiautes), com 13º, férias, jetons e abate-teto |
| PB | Dados abertos (API da Codata) | Por órgão e mês: parte fixa e parte variável |
| PE | Dados abertos, "Remuneração de servidores" | CSV mensal; a governadora é achada pelo nome (recebe como procuradora) |
| PR | Portal da Transparência, "Remuneração" | Busca pelo nome e página de detalhes (20 meses; exceção ao robots.txt) |
| RO | API do Portal da Transparência | Por cargo e mês, com as rubricas; o 13º numa folha à parte |
| RR | API do Portal da Transparência | Por nome e mês, com os lançamentos. Em 02 e 03/10/2026 a API respondeu 504 por mais de um dia (a coleta falhou; o site manteve o último dado); voltou no dia 03 |
| SC | Dados abertos, "Remuneração dos servidores" | CSV mensal só com o bruto; o Estado só mantém os meses recentes |
| SP | Portal da Transparência, "Remuneração" | Arquivo do mês e série histórica (.rar, lida com `libarchive-c`) |

- Guardamos só o que a pessoa recebe (salário, 13º, férias, auxílios, outros, bruto) e o abate-teto. Nada de CPF
  (nem mascarado) e nada de descontos pessoais.
- No site: recebido = bruto menos o abate-teto. Quando dezembro traz o 13º inteiro e o adiantamento já foi pago no
  meio do ano, o adiantamento sai de dezembro (senão o 13º conta duas vezes). O mês da saída, com os acertos (férias
  não tiradas, 13º proporcional), é marcado e fica fora da média.
- Nos outros 16 estados, a folha nominal não abriu para o robô (bloqueio, painel Power BI, chave de acesso, portal
  fora do ar no período eleitoral).

### Governador em exercício pago pelo órgão de origem (`coleta/governadores_tribunal.py`)

No Rio de Janeiro, desde 23/03/2026 o governador em exercício é o presidente do Tribunal de Justiça, Ricardo Couto de
Castro, que continua recebendo pelo Tribunal, onde é desembargador, e não o subsídio de governador. O que ele recebe
vem da folha do TJ-RJ copiada pelo [DadosJusBr](https://dadosjusbr.org) (licença CC BY 4.0, a planilha que o tribunal
manda ao Painel de Remuneração dos Magistrados do CNJ), com o mesmo leitor e as mesmas partes do Judiciário (descontos
nunca; diárias à parte). Só os meses no governo: `dados/governadores/outro_orgao/rj.csv` e, no site, `e.ot` do estado
em `governadores.json` (com a fonte de cada mês e os meses que faltam no DadosJusBr: mar/2026). A folha do Estado do Rio
segue congelada até mar/2026 (Cláudio Castro). Roda na etapa `governadores`, no GitHub.

No site (`otDe` e `blocoTJ`, no `app.js`; `gerar.mjs` para o texto da página pronta): a página do estado e a da pessoa (Ricardo Couto)
mostram o bloco "Recebe pelo Tribunal de Justiça, onde é desembargador", com um cartão por mês no governo (abr a ago/2026): o
recebido bruto em destaque, as parcelas que tiveram valor (subsídio, vantagens, 13º, férias, indenizações), as diárias à parte
(fora do recebido), o link do pacote do DadosJusBr de cada mês, o crédito (CC BY 4.0) e os meses sem a folha do tribunal. Regras:
nunca chamar isso de "salário de governador" e não pôr esse valor no lugar do subsídio da lei (`e.v`, R$ 21.868,14, que ele não
recebe: continua na comparação entre os 27 estados, rotulado "Subsídio do cargo de governador" e com a frase de que o governador
em exercício não o recebe; o "ganha mais que X%" some nesse caso). Na página dele não há "Nenhum pagamento na folha" nem "Folha até
mar/2026" (ele não está na folha do Estado): o topo diz que não recebe o subsídio e o que recebeu no último mês. Os meses de Cláudio
Castro continuam vindo da folha do Estado. O teste confere o texto, que o recebido é a soma das partes (sem as diárias) e que
outro estado não tem o bloco.

### Viagens dos governadores e vices (`coleta/viagens_governadores/`)

Os "gastos do cargo" dos governadores, como nos ministros: as viagens a serviço (diárias e passagens), onde o Estado
publica por pessoa. O levantamento dos 27 estados está em `dados/referencia/viagens_governadores.json`; os robôs
começam pelos que publicam com o nome, em formato aberto. Cada um grava `dados/governadores/viagens/<uf>.csv` (vai para
o Git), uma linha por viagem: datas, nome e cargo como a fonte escreve, destino, diárias, passagens, outros, devoluções e
a fonte. Nada de CPF (as respostas que o trazem mascarado não são lidas nesse campo) nem o texto livre do motivo.
Se a fonte trouxer bem menos viagens do que já estava gravado (nenhuma, ou menos de 90%), ou, em MG, o arquivo de
favorecidos vier sem os nomes, a coleta falha e o arquivo e o mês lido ficam como estavam (`comum.gravar`).

| Estado | Fonte | O que entra |
|---|---|---|
| AM | Portal da Transparência, "Diárias e Passagens" (o serviço do SCDP que a página usa, por órgão e mês; só abre do Brasil) | Diárias e passagens por solicitação; voos da Casa Militar aparecem com valor zero (o custo do avião oficial não é publicado) |
| MG | Dados abertos, conjunto "viagens" (CKAN; trechos do SCDP, ~42 MB) | Diárias e passagens por documento de viagem, somando os trechos; trechos aéreos sem valor de passagem são, em geral, no avião oficial |
| PB | API de dados abertos, `/remuneracao/diarias` (só do Brasil) | Diárias por empenho, valor pago; as passagens são empenhadas a agências, sem o nome do passageiro |
| SE | Portal da Transparência, relatório de diárias (Casa Civil e Gabinete do Vice; só do Brasil) | Diárias por viagem, valor pago; as passagens não são publicadas por pessoa |
| SP | Portal da Transparência, gastos individualizados com diárias e passagens aéreas | Diárias e passagens item por item; os itens da mesma pessoa no mesmo dia são uma viagem; seguro-viagem em "outros" |

- No site (`site/dados/governadores.json`), em cada estado com robô: `e.vg = [[aaaamm, índice em e.oc, diárias,
  passagens, outros, devoluções, número de viagens], ...]` e `e.vgf = {"u", "nota", "desde", "ate"}`. O mês é o do
  início da viagem; a viagem é da pessoa no cargo que ela ocupava naquele dia (quem foi vice e depois governador tem as
  duas partes). `ate` é o último mês lido na última coleta que deu certo (`dados/governadores/viagens/lidos.json`).
- Os nomes procurados são os do arquivo curado (`folha_nome`, `civil`) e, onde a fonte escreve o nome inteiro, os de
  `NOMES_FONTE` (`coleta/viagens_governadores/__init__.py`): ao mudar o governador, acrescentar o nome novo.
- `python3 -m coleta.viagens_governadores [UF ...]` coleta e anexa ao `governadores.json`; `--so-anexar` só anexa ao
  arquivo que existe, sem refazer o resto. Na rodada semanal, `coletar.py governadores` (e a rodada do Brasil) coleta e
  monta junto com a folha.

## Índice de Transparência dos estados

`python3 coletar.py indice` (também roda no `tudo`) gera `site/dados/indice_transparencia.json`: para cada Estado, uma
nota de 0 a 1 para a pergunta "dá para saber, pela fonte oficial de cada Estado, quanto ganham e quanto custam os seus
políticos?", no molde do [Índice de Transparência do DadosJusBr](https://dadosjusbr.org/indice). Há quatro blocos,
um para cada fonte, com as mesmas duas dimensões:

- **Governo do Estado** (a folha do governador e do vice): nome, cargo, quem está no cargo hoje, partes do pagamento
  (subsídio, 13º, férias, auxílios, abate-teto), histórico de 12 meses e a lei do salário.
- **Assembleia Legislativa** (cada deputado estadual): salário (folha ou só a lei), verba do gabinete por deputado, verba
  nota a nota (fornecedor e CNPJ), equipe do gabinete, histórico de 12 meses e a lei do subsídio.
- **Prefeitura da capital** (prefeito, vice e secretários): os critérios do governo, com "secretários" no lugar da lei.
- **Câmara Municipal da capital** (cada vereador): os critérios da Assembleia. No DF, que não tem prefeitura nem
  vereadores, esses dois blocos não se aplicam.
- **Completude** (o que a fonte mostra) e **facilidade** (como dá para obter: formato aberto; acesso — arquivo ou API
  documentada 1, API da página 0,75, só páginas ou botão de exportar que depende da sessão 0,5, só formulários 0,25,
  só clicando 0 —; sem barreiras como CAPTCHA, login ou CPF; aberto a robôs e a quem está fora do Brasil).
- Cada dimensão é a média dos seus critérios; o índice do bloco é a média harmônica das duas; o índice do Estado é a
  média dos blocos que se aplicam, com peso igual. Estado com algum bloco a conferir (critério `null`) fica sem índice
  geral e ganha um "índice parcial" (a média dos blocos que já têm nota).

As notas, com a prova de cada uma, ficam em `dados/indice/governadores.json`, `assembleias.json`, `prefeituras.json` e
`camaras.json` (mantidas à mão: o que a fonte mostra e o que o robô consegue; "abre de fora do Brasil" foi conferido de
um servidor nos EUA, e o resto, do Brasil, por um computador e um navegador comuns). As capitais sem robô foram levantadas em
01/10/2026. A nota da lei do governador vem de `dados/governadores/governadores.json`. A folha do Mato Grosso pede
CAPTCHA: foi conferida à mão (o CAPTCHA resolvido por uma pessoa), e o robô não lê essa consulta. Desde 03/10/2026 os
27 estados têm índice geral: os dois últimos blocos a conferir, as prefeituras de Maceió e de Cuiabá, foram fechados
buscando na folha de cada uma os nomes do prefeito e de secretários publicados no site oficial da prefeitura. Em Maceió
não há filtro por cargo, e cada busca pelo nome leva de 3 a 5 minutos (o prefeito é Rodrigo Cunha desde 05/04/2026, e o
cargo de vice ficou vago); em Cuiabá, os secretários vêm com o cargo "COMISSÃO GDA", o mesmo dos outros comissionados, e
só a folha da verba indenizatória de agentes políticos e secretários os separa. Os blocos atrás de CAPTCHA (Câmara de
Belo Horizonte, prefeitura de São Luís) foram conferidos à mão, com o CAPTCHA resolvido por uma pessoa; o robô não lê
essas consultas. O
índice mede o acesso aos dados dessas quatro fontes, não a transparência do Estado como um todo, e é uma nota da
fonte, não de quem está no cargo. A passagem da página para os 4 blocos está em `TAREFA-SITE-indice-4-blocos.txt`.

A página `/indice` lê `site/dados/indice_transparencia.json` (`secIndice` no `site/app.js`; a versão em HTML para o
Google e as prévias de link sai do `publicacao/gerar.mjs`). Ela mostra os estados do maior índice geral para o menor e,
em cada um, o índice de cada bloco com a completude e a facilidade em barras. Estado com algum bloco a conferir fica fora
da ordem, numa lista à parte ("Com algum bloco a conferir"), com o índice parcial marcado como parcial (e quantos blocos
já têm nota). A posição usa o índice com as duas casas que a página mostra: dois estados com o mesmo número dividem a
posição e aparecem em ordem alfabética. Ao abrir um estado, cada bloco com os seus critérios (nota, prova, link quando
há e como a nota é dada; os nomes e o "como pontua" vêm de `meta.blocos`, não do `app.js`), o link da fonte oficial e,
no bloco do governo, a página do governador; no bloco da Assembleia, nos estados que já estão em `assembleias.json`, o link
para a seção "Assembleia Legislativa" da página do estado (`/governador/sp#assembleia`), onde a lista dos deputados
estaduais está; nos blocos da capital, o nome da cidade ("Prefeitura do Recife", "Câmara Municipal do Recife") e, quando
ela já está em `prefeituras.json` ou `camaras.json`, o link para a página da cidade. A página diz que cada bloco tem
responsáveis diferentes e que a nota é da fonte, não de quem está no cargo. O método (`meta.como`) fica na própria página. O arquivo leva os valores com 6 casas: o site arredonda
só na hora de mostrar. Há link para o índice no cabeçalho do site, na lista dos
governadores e na página de cada estado (`/indice#indice-sp` abre o estado).

## Tribunais de Contas: vereadores, prefeitos e vices do interior

Os municípios mandam a folha e as despesas ao Tribunal de Contas do estado; alguns tribunais abrem esses dados para
todos os municípios de uma vez. Um robô por tribunal cobriria todas as câmaras e prefeituras do estado, em vez de um
robô por Câmara. O levantamento dos 26 tribunais que fiscalizam municípios (o DF não tem municípios) está em
`dados/referencia/tribunais.json` (01/10/2026):

- **Folha nominal com valor de cada pessoa, câmaras incluídas:** Paraíba (TCE-PB, CSV por município e ano, desde 2013)
  e Ceará (TCE-CE, API documentada com cada item da folha). Também, com ressalvas: Maranhão (valor por pessoa, sem
  nome), Pará (TCM-PA, Power BI, só o mês corrente) e Goiás (TCM-GO, só com token da API).
- **Valor por cargo (total da câmara ÷ número de vereadores):** Espírito Santo (CSV), Pernambuco (Tome Conta) e Rio de
  Janeiro (por situação funcional). Robôs desde 03/10/2026: ver "Valor por cargo", abaixo.
- **Só despesas (empenhos com credor e CNPJ):** São Paulo, Paraná, Rio Grande do Sul (só do Brasil), Tocantins, Rio
  Grande do Norte e, em parte, Acre e Roraima.
- **Nada aberto ou atrás de barreira:** Amazonas, Amapá, Rondônia, Alagoas, Sergipe, Mato Grosso, Mato Grosso do Sul,
  Santa Catarina (bloqueio de robôs), Minas Gerais (reCAPTCHA na API), Bahia (TCM-BA, reCAPTCHA) e Piauí (sem valores).

Robô `coleta/tce/` (`python3 coletar.py tce`; um estado só, em partes: `python3 -m coleta.tce ce 150`; só os arquivos do
site: `python3 -m coleta.tce site`), para os 223 municípios da Paraíba e os 184 do Ceará, mês a mês desde janeiro de 2025:

- **O que guarda**: só os vereadores (pagos pela Câmara), o prefeito, o vice e, na Paraíba, os secretários municipais:
  uma linha por pessoa, órgão e mês, com o valor bruto e, onde a fonte separa, as partes (salário, 13º, férias, outros),
  em `dados/municipios_tce/<uf>/<ano>.csv` (vai para o Git). `fontes.csv` diz, para cada cidade, órgão e mês, quantas
  linhas a folha tinha no Tribunal (0 = o município ainda não tinha mandado) e o endereço da fonte. Nunca o CPF (nem
  mascarado, nem cifrado), nem os descontos, nem o líquido. O robô lê só os meses que faltam, os que vieram vazios e os
  2 últimos de novo.
- **Paraíba (TCE-PB)**: o arquivo do estado no Portal de Dados Abertos ("Servidores", um ZIP por ano, ~70 MB em 2026,
  atualizado todo dia), baixado só quando muda (ETag); o ano que não mudou não é lido de novo. Valor bruto do mês, sem as
  rubricas (não separa 13º e férias), no formato brasileiro sem zeros à direita ("9.300" é R$ 9.300,00). Vereador:
  unidade gestora da Câmara e cargo de vereador, escrito de muitos jeitos (assessores de vereador ficam de fora); prefeito
  e vice pelo cargo; secretário só quando o cargo diz "secretário municipal" ou "secretário de" uma pasta (adjunto,
  executivo e escolar ficam de fora; a lista de cada cidade pode estar incompleta). Dezembro de 2025 não está nos
  arquivos do Tribunal (o de 2025 vai até novembro). O link de cada cidade é o arquivo dela no portal.
- **Ceará (TCE-CE)**: API de Dados Abertos do SIM (sem login nem chave; até 1.000 registros por pedido). Por município e
  mês, a folha da Câmara e a do gabinete do prefeito (cada item pago, com o CPF cifrado e o vínculo), ligadas ao
  cadastro (nome e cargo) pelo CPF cifrado só na memória, durante a leitura. Vereador: cargo eletivo (vínculo "L") na
  folha da Câmara ou cargo de vereador no cadastro; o tipo de cargo 58 sozinho não basta (há câmaras que o usam para
  funcionários) e conselheiro tutelar fica de fora. Bruto = soma dos itens pagos, com o 13º separado. O nome vem do
  cadastro, com até 40 letras. Secretários ficam de fora: o valor deles está na folha de cada secretaria, com milhares de
  pessoas, e a API não filtra por pessoa. Ritmo: 2 pedidos por vez, com pausa, até 250 tarefas por rodada; o robô para
  quando 5 municípios seguidos dão erro (em 02/10/2026, depois de ~3 horas da primeira leitura com 3 pedidos por vez, os
  endereços do TCE-CE pararam de responder por ~12 minutos).
- **Partido**: o da eleição de 2024 (TSE, o arquivo de candidatos do passo 1), só quando o nome da folha é o de um único
  candidato da cidade (igual, ou só com outra grafia: Souza/Sousa, sem o "de"); homônimos ficam sem partido. Sem fotos
  nesta etapa.
- **Site**: um arquivo por estado, `site/dados/interior/pb.json` e `ce.json` (~700 KB cada, ~100 KB com gzip), com a
  série mensal de cada pessoa, quem está no cargo (está na folha do último mês da cidade) e o partido; formato em
  `TAREFA-SITE-interior.txt`. `coleta/situacao.py` lê o `ultimo_mes` de cada um (`tce/pb`, `tce/ce`).
- **Na página da cidade** (`vereadoresInterior` e `secPrefeituraInterior` no `site/app.js`): sem página nem arquivo
  por pessoa (são milhares, e o Cloudflare Pages tem limite de arquivos). O arquivo do estado só é baixado ao abrir uma
  cidade dele; o `gerar.mjs` põe a lista dos estados com arquivo numa `<meta name="dados-interior">` de cada página. No
  lugar dos eleitos do TSE e do teto sozinho: o valor típico de um vereador (a mediana, entre os vereadores na folha do
  último mês, da mediana dos meses com valor nos últimos 12 de cada um, porque um mês sozinho pode ter 13º, férias ou
  atrasados), o teto da Constituição, o salário médio da cidade (IBGE) e o "ganha mais que X%"; depois, cada vereador
  numa linha (cargo, partido quando casou com o TSE, "passa do teto" quando o valor típico passa, o valor típico e a
  série mês a mês em colunas pequenas), quem passou pela Câmara no período, a tabela de todos os meses e as notas (meses
  sem folha, folha sem vereadores). Na seção "Prefeitura", o prefeito e o vice (ou a frase de que não aparecem na folha
  do último mês) e, na Paraíba, os secretários. A capital com dados próprios (Fortaleza) usa os dela; João Pessoa usa
  estes. O valor típico também entra no texto da página pronta, no texto para compartilhar e na imagem da cidade.
- **Ago/2026**: Paraíba, 2.200 vereadores em 222 das 223 câmaras (valor mediano R$ 6.950), 218 prefeitos, 211 vices e
  1.446 secretários em 188 cidades; Ceará, 2.238 vereadores em 182 das 184 câmaras (mediano R$ 10.400), 178 prefeitos e
  167 vices. Em algumas cidades o prefeito não aparece na folha. O número de vereadores de um mês pode passar o de
  cadeiras (suplente que assumiu no meio do mês, licenciado que continua na folha).
- **Onde roda**: as duas fontes abrem de fora do Brasil (conferido em 02/10/2026) e rodam no GitHub Actions.
- **Conferido** (02/10/2026): 3 vereadores e 1 prefeito por estado batem com o arquivo da cidade no TCE-PB (ago/2026) e
  com a API do TCE-CE lida à parte (jul/2026).
- A prova de 01/10/2026 (resumo de ago/2026 por município, sem nomes) continua em
  `dados/referencia/tce_pb_vereadores_202608.csv`.

### Valor por cargo: Espírito Santo, Pernambuco e Rio de Janeiro

Nesses três estados o Tribunal publica, para cada Câmara ou Prefeitura e cada mês, o total pago a um cargo (ou a uma
situação funcional) e quantas pessoas estavam nele, e não o valor de cada pessoa. Dá para saber quanto a Câmara pagou
ao cargo de vereador e a média por pessoa, mas não quanto cada vereador recebeu: o presidente da Câmara, quem entrou ou
saiu no meio do mês e quem recebeu 13º ou férias ficam somados aos outros. Quando o cargo tem uma pessoa só (prefeito,
vice), o total é o valor dela. Robôs `coleta/tce/es.py`, `pe.py` e `rj.py`, com a parte comum em `coleta/tce/cargo.py`
(no mesmo `python3 coletar.py tce`; um estado só: `python3 -m coleta.tce pe 150`), mês a mês desde janeiro de 2025:

- **O que guarda**, em `dados/municipios_tce/<uf>/` (vai para o Git): `cargos.csv`, uma linha por cidade, órgão, mês e
  papel (vereador, prefeito ou vice), com o cargo como a fonte escreve, a quantidade de pessoas, o total bruto (antes
  dos descontos) e, onde a fonte separa, a parte indenizatória, o 13º e as férias; `nomes.csv`, quem estava no cargo
  (só o nome e o cargo; ES: todos os meses; PE: o último mês de cada cidade e os meses em que o papel tem mais de um
  cargo; RJ: a fonte não tem nomes); `fontes.csv`, como na Paraíba e no Ceará. Nunca o CPF: ES e PE mostram o CPF
  mascarado, que não é lido.
- **Espírito Santo (TCE-ES, 78 municípios)**: dois arquivos do conjunto "Área temática: pessoal" no Portal de Dados
  Abertos do estado (CKAN, achados pela página do conjunto, com os 10 s de pausa que o robots.txt pede), atualizados
  todo dia: "Vantagens e descontos" (ZIP por semestre, ~10 a 30 MB: o valor somado por unidade, mês, cargo, vínculo e
  verba, sem nomes) e "Vínculo" (CSV por trimestre, ~200 MB: cada pessoa com vínculo em cada mês). Do primeiro sai o
  total (as vantagens do vínculo "Cargo político derivado de mandato eletivo"), do segundo a quantidade e os nomes (o
  vínculo "Eletivo"). Cada arquivo só é baixado quando muda (ETag; o armazenamento responde 304), e só um extrato pequeno
  fica no cache. O CSV de vantagens tem o cargo sem aspas, às vezes com ";" ou quebra de linha dentro (o robô monta cada
  registro pelas 4 primeiras e as 5 últimas colunas). Cada município classifica as verbas do seu jeito (a Câmara de
  Vitória lança o subsídio como "Outros adicionais"): o total é a soma de todas as vantagens; 13º, férias e a parte
  indenizatória (auxílio-alimentação e outras) ficam separados quando a verba diz. Em três cidades o prefeito está no
  vínculo eletivo e o arquivo de vantagens não tem valor para o cargo (entra sem valor).
- **Pernambuco (TCE-PE, 184 municípios)**: o Tome Conta (`tomeconta.tce.pe.gov.br/dados/`, "Servidores"), com o que
  cada município manda ao Tribunal pelo Sagres: por unidade e mês, cada cargo com a quantidade e o total das vantagens
  (o robô faz o mesmo pedido que a página, `PessoalFolhaPagamento!paginaVisualizarAjax`, com todos os cargos numa
  página), e a lista de nomes de cada cargo (página de detalhes, sem valor por pessoa). A lista das câmaras e
  prefeituras vem da API de Dados Abertos do TCE-PE (`UnidadesJurisdicionadas`). O robots.txt não proíbe nada; um
  pedido por vez, com pausa, até 2.000 pedidos por rodada (a semana normal pede ~1.000; a primeira leitura, desde
  jan/2025, levou ~3 horas e ~10.000 pedidos, em 03/10/2026). O servidor do Tome
  Conta não manda o certificado intermediário: `util.ca_com_intermediario` completa a cadeia com o intermediário que o
  próprio certificado indica, conferido com as raízes do certifi (a verificação nunca é desligada). Na página de
  detalhes, com a "data de atualização" da unidade preenchida a lista volta vazia: o robô manda esse campo vazio. O
  presidente da Câmara costuma aparecer como VEREADOR e de novo como PRESIDENTE: a quantidade do papel é a de nomes
  diferentes. Muitos municípios põem códigos no nome do cargo ("PREFEITO EX1", "PREFEITO - P0216", "PPREFEITO",
  "CV VEREADOR"): `cargo._letras` tira os códigos antes de reconhecer o cargo. Não separa 13º nem férias.
- **Rio de Janeiro (TCE-RJ, 91 municípios; a capital tem o próprio Tribunal de Contas do Município)**: a "Situação
  Funcional" da API do Portal de Dados Abertos (`dados.tcerj.tc.br/api/v1/situacao_funcional`, uma consulta por ano):
  por unidade e mês, cada situação funcional com a quantidade e a remuneração somada, sem nomes. Vereadores: "Agente
  Político" na unidade da Câmara; em uns 2 de cada 3 municípios a quantidade é a das cadeiras, nos outros passa um pouco
  ou fica diferente. Prefeito e vice ficam de fora: na Prefeitura, "Agente Político" junta o prefeito, o vice e os
  secretários.
- **Valor típico por pessoa** (`vm`): a mediana do total dividido pela quantidade, entre os últimos 12 meses, só nos
  meses em que a quantidade é a esperada (as cadeiras eleitas em 2024, para vereadores; 1, para prefeito e vice) e sem
  13º nem férias (onde a fonte separa; onde não separa, sem dezembro), com pelo menos 3 meses assim. Sem isso, o site
  mostra só o total e a quantidade. No Espírito Santo também sem a parte indenizatória (`vmr`), que é o que se compara
  com o teto da Constituição. Para vereadores é uma média, e não o salário de um vereador.
- **Site**: um arquivo por estado em `site/dados/interior-cargo/<uf>.json` (outra pasta, porque o formato é outro;
  os campos estão em `CAMPOS`, em `cargo.py`), com, por cidade, as cadeiras, a série mensal de quantidade e total de
  cada papel, o valor típico e os nomes do último mês (com o partido de 2024 quando o nome casa com um único candidato
  da cidade). `coleta/situacao.py` lê o `ultimo_mes` de cada um (`tce/es`, `tce/pe`, `tce/rj`).
- **Ago/2026**: Espírito Santo, 893 pessoas no cargo de vereador nas 78 câmaras (63 com tantas pessoas quanto
  cadeiras), valor típico por vereador mediano de R$ 8.002 (67 câmaras com o valor típico), 75 prefeitos e 66 vices com
  valor; Pernambuco, 2.000 pessoas no cargo de vereador em 174 das 176 câmaras com a folha de agosto (163 com tantas
  pessoas quanto cadeiras), mediano de R$ 11.062 (168 câmaras), prefeito em 151 e vice em 145 das 159 prefeituras com
  a folha de agosto; Rio de Janeiro, 1.042 agentes políticos em 79 das 91 câmaras (as outras ainda não tinham mandado
  o mês), mediano de R$ 10.021 (73 câmaras).
- **Conferido** (03/10/2026): ES, Vitória, Colatina e Afonso Cláudio (ago/2026) contra o arquivo de vantagens e o de
  vínculo baixados de novo; PE, Abreu e Lima e Afogados da Ingazeira contra a página do Tome Conta; RJ, contra a
  consulta da API por município.
- **Onde roda**: as três fontes abriam de fora do Brasil no levantamento de 01/10/2026; rodam no GitHub Actions e, se
  falharem de fora, a rodada do Brasil seguinte (mensal) as pega.

## Judiciário

`python3 coletar.py judiciario` (também no `tudo`) grava em `dados/judiciario/<orgao>/` o pagamento, mês a mês desde
jan/2025, dos ministros do STF, do STJ, do TST, do STM e do TSE, dos conselheiros do CNJ e do Procurador-Geral da
República, e escreve `site/dados/judiciario.json` (126 páginas, 103 pessoas no cargo em 02/10/2026). Só as partes
brutas, como cada fonte separa: subsídio, vantagens pessoais, abono de permanência, indenizações (com o nome de cada
parcela, quando a fonte dá), vantagens eventuais, férias, 13º e outras; as diárias ficam à parte. Nunca descontos,
líquido ou CPF. Quem está no cargo vem de `dados/judiciario/composicao.json` (mantido à mão e conferido com a folha); o
cargo de presidente, vice e corregedor sai da lotação de cada mês na folha (um mês sem folha publicada no meio não
interrompe a função) ou, onde a folha não mostra, como no STJ (a lotação é sempre a do gabinete do ministro), de
`funcoes` no mesmo arquivo, pela página oficial do órgão; o levantamento das fontes está em
`dados/referencia/judiciario.json`, com a amostra conferida de jul/2026 em `dados/referencia/judiciario_amostra.csv`.

| Órgão | Fonte | Desde | Observação |
|---|---|---|---|
| STJ | API da página de transparência | jan/2025 | nome de cada parcela desde mai/2026 |
| TST | arquivo mensal (CSV) | jan/2025 | jan/2026 não publicado |
| CNJ | página da folha | jan/2025 | só quem o CNJ paga; nov/2025 vazio na página |
| PGR | planilhas do MPF (ODS) | jan/2025 | o total soma as verbas indenizatórias, que o arquivo deixa de fora |
| STF | DadosJusBr, cópia do arquivo oficial | jan/2025 | a consulta do STF proíbe robôs no robots.txt |
| STM | DadosJusBr (Painel do CNJ) | jan/2025 | a consulta proíbe robôs e só abre do Brasil |
| TSE | DadosJusBr (Painel do CNJ) | fev/2025 | o site do TSE responde 403 a robôs |

O [DadosJusBr](https://dadosjusbr.org) (Transparência Brasil) coleta a folha oficial do sistema de Justiça todo mês
(licença CC BY 4.0, com crédito). Do STF, os valores saem da cópia do arquivo oficial que ele guarda, e não do pacote
padronizado: em dez/2025 o arquivo do STF repete cada coluna e cada linha, e o pacote daquele mês ficou com as colunas
trocadas. Em jul/2026, para dois ministros, a coluna "Férias" do STF traz um valor que os totais do próprio arquivo
subtraem; aqui ele entra com sinal negativo. Onde há fonte oficial aberta (STJ, TST, CNJ e MPF), ela vale: cada número
tem o link do arquivo oficial do mês, e o DadosJusBr não dá esse link.

Reserva: se o robô oficial do STJ ou do PGR falhar, os meses que ele ainda não leu vêm do DadosJusBr
(`dadosjusbr.reserva`), marcados em `fontes.csv` pelo endereço do pacote; o `meta.orgaos` do site passa a dizer "oficial e
DadosJusBr", com uma nota que lista esses meses, e a situação da fonte mostra a falha. Quando a fonte oficial volta, ela relê
esses meses. Conferido em 03/10/2026: no STJ (jun/2026), 32 de 33 ministros com o mesmo valor (um com R$ 55 de diferença nas
indenizações); no PGR (ago/2026), igual. TST e CNJ ficam sem reserva: o pacote do DadosJusBr não bate com a fonte oficial
(no TST, metade dos ministros com valores diferentes e a folha suplementar à parte; no CNJ, gratificações que a página do
CNJ não mostra).

Quem está no TSE vindo do STF ou do STJ, e quem integra o CNJ vindo de um tribunal, recebe o salário no tribunal de
origem: cada página mostra só o que aquele órgão paga, as páginas da mesma pessoa se ligam ("rel") e nada é somado duas
vezes. Parcelas que os tribunais classificam como indenizatórias (por exemplo PVTAC e GECJAO, arts. 3º e 5º, b, da
Resolução Conjunta CNJ/CNMP nº 14/2026, conferida no texto publicado pelo CNMP em 04/10/2026) não entram no cálculo do
abate-teto na própria folha; por isso o total do mês pode passar do subsídio de ministro do STF (R$ 46.366,19 desde
fev/2025). Os rótulos das folhas citam a norma de outro jeito: no MPF, a PVTAC vem como "RES. 14/2016/STF/CNMP"; no
STM, como "RES. 391/2026". As sete fontes abrem de fora do Brasil (conferido em 02/10/2026).
Desembargadores e juízes não entram: seriam milhares de páginas (o limite do Cloudflare Pages no plano gratuito é de
20.000 arquivos).

No site: uma página por pessoa e órgão (`k: "t"`; `/alexandre-de-moraes`, `/carmen-lucia-ministra-tse`), como a de um
deputado, e `/judiciario` com os 7 órgãos (quem está no cargo, o último mês e a média desde jan/2025, quem saiu e, no
CNJ, quem integra o conselho pago pelo próprio tribunal). O total do mês é o bruto, antes do abate-teto; as diárias
ficam à parte, fora do total, como na fonte. A seção "Contracheque de cada mês" abre cada mês com as partes como a fonte
separa ("—" quando ela não separa), o nome de cada parcela quando a fonte dá, a nota do mês (\*) e o link do arquivo
daquele mês. A posição e a mediana comparam só dentro do mesmo órgão, e não no CNJ nem no TSE: lá, quem vem de um
tribunal recebe só a diferença ou a gratificação, e os valores não são comparáveis entre si. Para não passar do limite
de arquivos, não há arquivo por pessoa: o `gerar.mjs` grava a lista leve em `dados/indice/judiciario.json` (sem o mês a
mês, com o último mês de cada um) e o app baixa o `judiciario.json` inteiro ao abrir uma página do Judiciário.

## Robôs e robots.txt

Todo pedido dos robôs passa por `coleta.util._sessao()` (`SessaoEducada`), que lê o robots.txt de cada site antes do
primeiro pedido: o que ele proíbe não é aberto (erro `BloqueadoRobots`, e o estado ou a cidade segue com o que já estava
gravado), e o `Crawl-delay` é respeitado. As APIs da Wikimedia ficam de fora (têm regras próprias para robôs). Quem cria
um robô novo deve usar essa sessão, e não `requests` direto.

**Exceções.** O robots.txt é uma convenção, não lei. Dados que a Lei de Acesso à Informação manda publicar e abrir para
"acesso automatizado por sistemas externos" (Lei 12.527/2011, art. 8º, § 3º, III), como a remuneração de agentes
públicos, são lidos mesmo quando o robots.txt de um órgão proíbe. Cada exceção está em `EXCECOES_ROBOTS`
(`coleta/util.py`), com o motivo e uma pausa entre os pedidos; o robô se identifica ("ContasDoPoder", com o endereço
do site), lê só o que falta (o que já foi lido fica no Git) e para se o órgão pedir ou bloquear. Hoje:

| Site | O que o robots.txt proíbe | O que lemos | Pausa |
|---|---|---|---|
| Câmara dos Deputados | `/deputados/*/*` (desde 18/09/2026) | Remuneração, contracheque detalhado e pessoal de gabinete de cada deputado | 0,25 s |
| Prefeitura de São Paulo (dados abertos) | todo o portal (`Disallow: /`) | Folha de pagamento mensal (CSV) | 10 s |
| Paraná (Portal da Transparência) | `/pte` | Remuneração do governador e do vice | 2 s |
| Assembleia de Minas Gerais (dados abertos) | todo o serviço (`Disallow: /`) | Deputados e verba indenizatória de cada deputado e mês (API `/ws/`, feita para acesso automatizado) | 1 s |
| Assembleia do Rio de Janeiro (DOCIGP) | todo o portal (`Disallow: /`) | Orçamento mensal e lançamentos publicados da verba de cada gabinete | 0,5 s |

Os portais CKAN (ES, MG, PE, SC, Recife e Fortaleza) proíbem só a API (`/api/`): os arquivos são achados pela página
do conjunto de dados (`coleta.util.recursos_ckan`), com os 10 s de pausa que pedem.

**Câmara.** O que as páginas de cada deputado mostram fica em `dados/camara/` (no Git): `remuneracao.csv` (salário da
folha normal), `remuneracao_detalhe.csv` (o contracheque de cada mês: 13º, férias, acertos, abate-teto, diárias,
auxílios, verbas indenizatórias, somando todas as folhas do mês; nunca imposto de renda, previdência ou líquido) e
`pessoal.csv` (quantas pessoas no gabinete, sem nomes). A verba de gabinete vem da página principal do deputado, que o
robots.txt permite. Os contracheques são lidos do mais recente para o mais antigo, no máximo 6.000 por semana; só
entram no site os meses em que todos os deputados já têm o seu (o site avisa desde quando). Os auxílios do contracheque
não entram de novo (são o auxílio-moradia, que vem da página de moradia). Se a Câmara bloquear, o robô usa o que está
em `dados/camara/` e, para os meses seguintes, o subsídio do Decreto Legislativo 172/2022 nos meses em exercício.

## Identidade visual

Faixas em azul-petróleo escuro (`#0f2b3c`: cabeçalho, abertura, topo do contracheque, rodapé e fundo da imagem para
compartilhar) e, nos dados, sempre as mesmas cores: verde-água para o que vai para o bolso, âmbar para os gastos do
mandato e azul-acinzentado para a equipe do gabinete (nas barras, nos gráficos, no índice e na imagem). O logo é uma
rosca com essas duas partes da conta (bolso e gastos), ao lado do nome: em duas linhas no celular, numa linha só no
computador e na imagem para compartilhar. Letras: Barlow Condensed nos
títulos e números e Barlow no texto, hospedadas no próprio site (`site/fontes/`: woff2 só de latin e latin-ext, pesos
400, 600 e 700 da Barlow e 600 e 700 da Barlow Condensed, `font-display: swap`, preload das usadas na primeira tela,
cache de 1 ano em `_headers`; licença SIL OFL 1.1 em `site/fontes/OFL.txt`, "The Barlow Project Authors"; o site não pede
nada ao Google Fonts). Mudou um arquivo de letra? Mude também o nome, por causa do cache. Tema claro e escuro em
`site/estilo.css` (variáveis no começo do arquivo); o ícone (`site/favicon.svg`) e a prévia do link (`site/og.png`)
seguem o mesmo desenho.

O retângulo escuro do topo do contracheque (`resumoTopo`, no `app.js`; `.conta__resumo--duas`, no `estilo.css`; a prévia pronta do
`gerar.mjs` segue a mesma estrutura) foi desenhado em 03/10/2026, entre duas propostas que o Jean-François viu em captura (uma coluna
e duas colunas; ficou a de duas). Ordem: a identidade (foto, nome e, na mesma linha do cargo, a etiqueta "No cargo" e o link da fonte
oficial, "Página oficial", "Folha de pagamento" ou "Fonte do salário"); o período; o **número** (custo por mês, ou "recebe por mês")
com a **divisão** que o explica logo embaixo (a barra e as duas partes, bolso e gastos, que são a legenda da barra); o **contexto**
("Comparado com os colegas", "Equivale a N salários mínimos por mês", o selo "vs. mediana" e a posição em faixa, "212º de 554 ·
custa mais que 61% dos deputados em 2025", com a régua); e, no pé, a **nota** da ajuda de custo paga de uma vez, ligada ao número por
um asterisco. A partir de 980 px, o número e a divisão ficam à esquerda e o contexto à direita, separado por um fio; abaixo disso (e no
celular), uma coluna só, nessa ordem. Sem a posição (CNJ, TSE, grupos com menos de 5, quem só tem o valor da lei), o contexto traz só os
salários mínimos (e o selo, se houver mediana). Os "salários mínimos por mês" do topo (do custo total) e "Vai para o bolso: N salários
mínimos por mês" (coluna da esquerda do cartão claro) são duas contas, cada uma com o seu rótulo. O teste confere, em toda página de
pessoa, que o número e a divisão estão juntos, que a divisão não leva nada do contexto, a ordem, o asterisco, o link na linha do cargo e,
no computador, que o contexto começa na altura do número, fica à direita, não deixa canto vazio embaixo do número, e que a nota fica no
pé; as larguras 980 e 1080 px têm página própria no teste (cada tipo de pessoa em uma delas).

A lista das seções da página (Contracheque, Mês a mês, Equipe, Gastos, Presença e projetos, Ranking...; `navSecoes`, no
`app.js`, `#secoes-caixa` no `index.html`) fica numa linha só em qualquer largura. Os rótulos são curtos para caber na coluna
do computador (1.048 px) em todo tipo de página, a partir de 1080 px (o do deputado é o mais longo: 10 botões). Se não couber
(tela menor), rola para o lado: a borda esmaece, e com mouse aparece uma
seta (‹ ›) no lado onde há mais (`data-mais="esq dir"` na caixa, atualizado no scroll, no resize e quando as letras carregam;
as setas não entram na ordem do teclado, que já rola a lista ao focar um botão). O teste confere, em toda página com a lista,
que os botões têm o mesmo topo e que, se a lista rola, a caixa avisa; a página do Tiago Dimas é aberta a 900 px, onde o menu
do deputado não cabe. Se acrescentar uma seção ou alongar um rótulo, conferir a largura de 1080 px (antes de deixar rolar).

## Compartilhamento e medição

- **Imagem para compartilhar**: cada político, governador e Câmara Municipal (com o gasto informado) tem uma imagem
  1080×1350 (4:5, aparece inteira no WhatsApp e no Telegram e serve para status e stories), com a foto, o valor
  principal, a posição entre os colegas e o endereço da própria página (quem recebe a imagem não consegue clicar, mas
  consegue digitar). O convite para compartilhar ("Compartilhe este contracheque", com a prévia da imagem) vem depois dos
  números principais, para a pessoa ler primeiro, e antes dos detalhes: no político, entre o contracheque e o mês a mês.
  No governador e na cidade, a mesma seção do fim da página do político ("Mande a imagem para quem você quiser"), com a
  imagem grande e o texto; a Câmara sem o gasto informado não tem imagem e mostra só o texto, no fim do cartão. No celular, o botão quadrado **Compartilhar**, fixo no canto
  de baixo da tela, aparece depois que a pessoa passa pelos números principais (e some enquanto o convite está na tela).
  Os dois abrem primeiro uma janela com a imagem, para a pessoa ver o que vai mandar, com **Enviar imagem…** (o menu do aparelho:
  WhatsApp, Telegram...; no iPhone vai só a imagem, porque com texto junto o WhatsApp do iPhone nem sempre manda os
  dois), **Copiar imagem** (para colar no WhatsApp Web) e **Baixar imagem**. O texto com o link fica em "Prefere mandar
  em texto?"; no fim da página do político (a seção "Resumo para compartilhar"), a imagem e o texto aparecem juntos.
  Na seção "Mande a imagem para quem você quiser" (e na janela), tocar na imagem a amplia do tamanho da tela.
  A imagem é feita logo depois que a página aparece, para o toque não esperar. Quando ela tem pouca informação
  (uma Câmara pequena, um prefeito), o espaço que sobra antes do rodapé é dividido entre os blocos. As fotos ficam no próprio site
  (`site/fotos/`) porque o site da Câmara não deixa outro endereço usar as fotos dele num canvas.
- **Prévia do link** (`site/og.png`, 1200×630) para WhatsApp e redes sociais.
- **Fotos do governo federal**: quem é deputado ou senador usa a foto oficial do Congresso. Os outros vêm do
  Wikimedia Commons (via Wikidata), só com licença livre e só retratos; o crédito fica em
  `site/fotos/creditos.json` e aparece no contracheque e na imagem. Quem o Wikidata não resolve pode ter a foto
  escolhida à mão em `dados/referencia/fotos_governo.json` (o arquivo do Commons e, se preciso, o corte do retrato;
  o crédito diz "recortada"). Nada com licença ND nem com licença duvidosa (foto do gov.br marcada como livre, "PD-USGov"
  em foto brasileira). Quem não tem foto aparece com as iniciais. No crédito (contracheque e imagem), "via Wikimedia
  Commons" só quando a foto vem de lá; a da candidatura (vereadores e deputados estaduais) vem do Portal de Dados
  Abertos do TSE.
- **Fotos de quem ainda não tem** (`coleta/fotos_faltam.py`, em 03/10/2026; `python3 -m coleta.fotos_faltam lista`
  mostra quem falta): Judiciário, governo federal, governadores, deputados estaduais, vereadores e prefeituras. Primeiro o
  Wikidata: item de um ser humano brasileiro, com foto, cujo nome é o curto ou o civil da pessoa e com o cargo ou a
  profissão do grupo (juiz, jurista, ministro, político...); dois itens assim (homônimos) = sem foto. A licença é conferida
  no Commons (CC BY, CC BY-SA, CC0, domínio público e a predefinição "Attribution", uso livre com crédito; nunca ND); foto
  mais larga que alta sai do centro, com "recortada" no crédito, e as fotos novas foram conferidas a olho (as de grupo
  em que não dá para saber quem é a pessoa ficam em `RECUSADAS`). Depois, o TSE: a candidatura de 2024 (vereador,
  prefeito, vice) ou de 2022 (de governador a deputado), quando o nome civil é exatamente o de um único candidato do
  lugar. Nos arquivos do site, só `f` e `fc` mudam (`preencher()`).
- **Google Analytics só em produção** (desde 03/10/2026): o `<head>` do `index.html` só carrega o gtag quando o endereço
  é `contasdopoder.com` (com ou sem `www`). Em `localhost`, nas prévias do Cloudflare Pages (`*.pages.dev`) e nos testes o
  gtag nem existe: nenhuma visita e nenhum evento (nem o `velocidade`, que nem começa a medir) vão para o Analytics. Em
  produção nada muda: mesma tag, mesma configuração, mesmos eventos. `publicacao/testes/rodar.mjs` confere os dois lados
  (o gtag carrega em `contasdopoder.com` e `www.contasdopoder.com` e em mais nenhum nome, e nenhuma página testada pede o
  Google Analytics). Visitas de `localhost` que chegaram antes dessa data ficam nos relatórios com o nome de host
  `localhost`: dá para filtrar.
- **Google Analytics** (`G-MK65PM0MCZ`). Eventos: `ver_parlamentar` (com a origem: busca, busca_topo, guia, estado,
  ranking, comparar, link ou navegação), `trocar_periodo`, `compartilhar` (método: enviar_imagem, copiar_imagem,
  baixar_imagem, whatsapp, copiar_texto ou copiar_link; `conteudo`: parlamentar, governador ou cidade; `onde`: topo,
  depois_contracheque, flutuante, secao ou fim; depois_numeros até 01/10/2026), `abrir_compartilhar` (abriu a janela da imagem, com
  `onde` e `conteudo`), `comparar`, `ranking`, `ranking_completo`, `ver_estado` e `guia` (ao abrir, com a origem: botao ou
  busca_topo, quando a pessoa escolhe o estado na busca do cabeçalho).
  Busca e listas: `abrir_busca` (a lupa do cabeçalho fixo, com a página em que a pessoa estava; quem escolhe um nome por
  ali chega com a origem `busca_topo`) e `abrir_lista` (listas que começam fechadas: `ministros`, `governadores`,
  `vice_governadores`, `cidades` com a UF, `secretarios`, `subprefeitos` e `sairam_prefeitura`).
  Também, no "Encontrou um erro?": `abrir_fonte` com `onde: erro` (clique num link da fonte), `abrir_reportar_erro`
  (abriu "A fonte mostra outro valor?") e `reportar_erro` (clique no e-mail); e `ver_correcoes`.
  Índice de Transparência: `ver_indice` (abriu `/indice`, com a origem: link ou navegação) e `abrir_indice` (abriu um
  estado no índice, com a `uf` e, desde 01/10/2026, a `situacao`: `completo`, se o estado está no ranking, ou `parcial`,
  se está na lista dos que têm algum bloco a conferir; todos os blocos do estado abrem juntos).
  Deputados estaduais (sem evento novo): `ver_parlamentar` e `compartilhar` com `casa: deputado estadual` e, na
  origem, `assembleia` (a lista da página do estado); `ranking` com `casa: assembleia_<UF>`; `abrir_lista` com
  `assembleia_<UF>` e `assembleia_sairam_<UF>`; `guia` com `etapa: assembleia_<UF>`.
  Números da abertura (desde 02/10/2026): cada um leva ao seu grupo e manda `abrir_numero` com o `grupo`
  (`deputados_senadores`, `governo`, `governadores`, `judiciario`, `deputados_estaduais`, `vereadores`, `prefeituras` e,
  desde 03/10/2026, `atualizacao`: o 8º quadro, "último mês dos dados · atualizado em DD/MM", que leva a `/atualizacao`;
  a data é a mais recente entre os arquivos de dados e a `situacao.json`, posta pelo `gerar.mjs` em
  `<meta name="dados-atualizados">`, e é a mesma do "Gerado em" do rodapé):
  o ranking já no grupo (deputados estaduais do estado escolhido ou de SP; vereadores e prefeituras de SP), a lista do
  governo aberta, os 27 governadores ou a página `/judiciario`. Na página inicial, o Judiciário mostra os presidentes
  dos tribunais e o PGR e, apagados, os outros ministros do STF (`abrir_lista` com `judiciario_stf`).
  Judiciário (desde 02/10/2026): `ver_judiciario` (abriu `/judiciario`, com a origem); `ver_parlamentar`, `trocar_periodo`
  e `compartilhar` com `casa: judiciario`; `abrir_detalhe` com `categoria: mes_judiciario` (abriu um mês do contracheque);
  `abrir_lista` com `judiciario_sairam_<SIGLA>`. No evento `velocidade`, `pagina` pode ser `judiciario`.
  Dados abertos (desde 02/10/2026): `ver_dados_abertos` (abriu `/dados-abertos`, com a origem) e `baixar_dados` (clicou
  num arquivo da página, com o `arquivo`); os links para o GitHub e o Internet Archive saem como `abrir_github` e
  `abrir_fonte` com `onde: dados-abertos`. No evento `velocidade`, `pagina` pode ser `dados_abertos`.
  Atualização dos dados (desde 02/10/2026): `ver_atualizacao` (abriu `/atualizacao`, com a origem), `baixar_dados` com
  `situacao.json` e `abrir_fonte` com `onde: atualizacao` (clicou no link de uma fonte). No evento `velocidade`,
  `pagina` pode ser `atualizacao`.
  Sobre e privacidade (desde 03/10/2026): `ver_sobre` (abriu `/sobre`, com a origem); o link da extensão de desativação do
  Google Analytics sai como `abrir_fonte` com `onde: sobre` (ou o id da seção). No evento `velocidade`, `pagina` pode ser `sobre`.
  Interior da Paraíba e do Ceará (desde 02/10/2026, sem evento novo): `abrir_lista` com `interior_sairam_<UF>`
  (vereadores que passaram pela Câmara), `interior_secretarios_<UF>` e `interior_sairam_prefeitura_<UF>`.
  Governadores e vices como pessoas (desde 02/10/2026, sem evento novo): `ver_parlamentar`, `trocar_periodo` e
  `compartilhar` com `casa: governador`; na origem, `governador` (o link da página do estado para a da pessoa); e
  `ver_governador` com a origem `pessoa_governador` (o link da página da pessoa para a do estado).
  Viagens do governador e do vice (desde 03/10/2026): a seção "Viagens" da página da pessoa (`secViagensG`, só nos estados
  com `e.vgf`: AM, MG, PB, SE e SP) lê `e.vg`/`e.vgf` de `governadores.json` (nenhum arquivo novo); diárias e passagens
  ficam à parte do que vai para o bolso, só dentro do mesmo estado (sem comparação nem ranking entre estados), e o
  `abrir_detalhe` com `categoria: viagens_governador` conta a abertura da tabela mês a mês. Quem não tem viagem na
  fonte mostra "a fonte não mostra viagem"; as colunas de passagens e de outros só aparecem onde a fonte as tem.
- **Velocidade nos aparelhos de quem visita** (desde 01/10/2026): o evento `velocidade`, um por visita, enviado quando a
  pessoa sai da página ou troca de aba pela primeira vez. Leva os três números que o Google usa para dizer se um site é
  rápido (Core Web Vitals), medidos pelo próprio navegador: `lcp_ms` (quando o maior bloco de texto ou imagem da primeira
  página apareceu; bom até 2.500 ms, ruim acima de 4.000), `cls` (quanto a primeira página pulou enquanto carregava; bom
  até 0,1, ruim acima de 0,25) e `inp_ms` (quanto o site demorou para responder a um toque, clique ou tecla, no pior caso
  da visita; bom até 200 ms, ruim acima de 500). Cada um vem com a faixa (`lcp_faixa`, `cls_faixa`, `inp_faixa`: `bom`,
  `melhorar` ou `ruim`), e `pagina` diz o tipo da primeira página (`inicio`, `politico`, `governador`, `cidade`,
  `indice` ou `correcoes`). LCP e CLS param de contar quando a pessoa vai para outra página do site; o INP vale para a
  visita inteira. O navegador que não mede um dos números (o Safari não mede todos) só não manda aquele, e a página
  aberta em segundo plano não manda nada. O código fica no começo do `site/app.js` (`VEL`).
  Para ver no Google Analytics, é preciso registrar os parâmetros uma vez (Administrador > Definições personalizadas):
  `pagina`, `lcp_faixa`, `cls_faixa` e `inp_faixa` como dimensões personalizadas (escopo: evento); `lcp_ms` e `inp_ms`
  como métricas personalizadas em milissegundos e `cls` como métrica padrão. O Analytics mostra soma e média dos números,
  não percentis: o jeito de ler é contar os eventos por faixa (por exemplo, numa exploração com o evento `velocidade`,
  as linhas por `pagina` e as colunas por `lcp_faixa`). O Google considera o site bom quando 75% das visitas estão em
  `bom` nos três. A `situacao` do `abrir_indice` também precisa ser registrada como dimensão para aparecer nos relatórios.

## Erros e correções

- No fim de cada página (político, governador, cidade), o bloco **"Encontrou um erro?"** leva primeiro às fontes
  oficiais daquela página (página oficial do político, lei e folha do governador, Siconfi para a cidade). Se a fonte
  mostra o mesmo valor, quem corrige é o órgão (ouvidoria ou LAI). Só se a fonte mostra outro valor ("A fonte mostra
  outro valor?", que abre ao toque) aparece o e-mail para contato@contasdopoder.com, já com o endereço da página.
- O que for corrigido entra, à mão, em `site/dados/correcoes.json` e aparece em
  [contasdopoder.com/correcoes](https://contasdopoder.com/correcoes): a data, o que estava errado, o que mudou e as
  páginas afetadas (`paginas`: o id do político, como `dep-204558`, ou `governador/al`). `publicacao/gerar.mjs` monta
  a página pronta.

## O que já foi conferido

- Cota do Senado: nossa soma bate **ao centavo** com o total oficial em 324 de 324 comparações (senador × ano).
- Cota da Câmara: 37 de 40 comparações da amostra batem ao centavo; as outras 3 diferem até 1,5%.
- Auxílio-moradia da Câmara em 2026: bate ao centavo com o total do site.
- Presença e projetos (03/10/2026; deputados Laura Carneiro, Zucco, André Fufuca, Marcelo Nilo e Augusto Puppio;
  senadores Alan Rick, Paulo Paim, Renan Filho, Augusta Brito e Damares Alves): a presença na Câmara bate dia a dia com
  o serviço oficial por deputado (`ListarPresencasParlamentar`); as votações do Senado batem ano a ano com a consulta por
  senador; primeiro autor e normas batem com a API da Câmara (autores e situação de cada proposição) e, no Senado, com
  o serviço de autorias do senador e a norma gerada no detalhe de cada processo.

## Pendências conhecidas

Veja `metadados.json` → `pendencias`. As principais:

1. **Câmara:** desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) sumiram dos arquivos
   de dados abertos (cerca de R$ 4 milhões por mês). Completamos com o total mensal do site oficial.
2. **Senado:** o custo dos assessores é uma **estimativa** (liga a folha de pagamento à lotação atual de cada
   comissionado, pelo nome).
3. **Câmara:** o 13º, as férias, os acertos, as diárias e a ajuda de custo dos deputados vêm do contracheque
   detalhado de cada mês, lido aos poucos (ver "Robôs e robots.txt"); enquanto a leitura não chega ao começo da
   legislatura, os meses mais antigos ficam sem eles (o site diz desde quando entram).
4. **Governadores:** o mês a mês pela folha em 24 estados. Faltam o Amapá e o Mato Grosso (a consulta pede CAPTCHA,
   que não contornamos) e o Tocantins (o portal só funciona clicando na página). No Pará, a consulta pública deixou de
   mostrar a governadora e o vice a partir de abril de 2026.
5. **Prefeituras:** Belo Horizonte e João Pessoa (portais bloqueiam robôs), Macapá (portal de
   terceiro) e as outras capitais ainda não foram feitas. No Rio, só prefeito e vice (a folha não diz o cargo).
6. **Câmara Municipal do Recife:** a consulta da Verba Indenizatória está com erro no site da Câmara; os meses
   afetados ficam de fora até ela voltar (o robô tenta de novo toda semana).

## Fontes

- Câmara: [API de dados abertos](https://dadosabertos.camara.leg.br/swagger/api.html),
  [arquivos da cota](https://www.camara.leg.br/cotas/), página principal de cada deputado (verba de gabinete),
  [moradia](https://www.camara.leg.br/moradia/detalhamento), as páginas de remuneração, de contracheque detalhado e
  de pessoal de gabinete de cada deputado e o
  [Decreto Legislativo 172/2022](https://www2.camara.leg.br/legin/fed/decleg/2022/decretolegislativo-172-21-dezembro-2022-793529-publicacaooriginal-166604-pl.html)
  (subsídio).
- Câmara, presença e projetos: [serviço de presença por dia](https://www.camara.leg.br/SitCamaraWS/sessoesreunioes.asmx)
  e [arquivos anuais de eventos, proposições, autores e temas](https://dadosabertos.camara.leg.br/swagger/api.html#staticfile).
- Senado: [dados abertos legislativos](https://legis.senado.leg.br/dadosabertos/docs/) (inclui as votações nominais e
  os processos de cada autor) e [administrativos](https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html).
- Governadores: leis e decretos legislativos das assembleias, diários oficiais, folhas de pagamento e tabelas
  oficiais dos estados (o link de cada valor está em `dados/governadores/governadores.json`).
- Prefeituras: [São Paulo](https://dados.prefeitura.sp.gov.br/dataset/remuneracao-servidores-prefeitura-de-sao-paulo),
  [Recife](https://dados.recife.pe.gov.br/dataset/servidores), [Fortaleza](https://dados.fortaleza.ce.gov.br/dataset/servidores),
  [Vitória](https://dadosabertos.vitoria.es.gov.br/),
  [Porto Alegre](https://portaltransparenciapmpa.procempa.com.br/portalpmpa/fpRemuneracaoPesquisa.do?viaMenu=true),
  [Salvador](https://transparencia.salvador.ba.gov.br/#/RemuneracaoDadosFuncionais),
  [Curitiba](https://www.transparencia.curitiba.pr.gov.br/meta4/servidores.aspx?quadro=),
  [Natal](https://www2.natal.rn.gov.br/transparencia/servidores.php) e
  [Rio de Janeiro](https://transparencia.prefeitura.rio/servidor-municipal/remuneracao/).
- Renda de quem trabalha no Brasil ("ganha mais que X% dos brasileiros que trabalham"): microdados dos 4 trimestres
  mais recentes da [PNAD Contínua do IBGE](https://www.ibge.gov.br/estatisticas/sociais/trabalho/9173-pesquisa-nacional-por-amostra-de-domicilios-continua-trimestral.html?t=microdados)
  (rendimento mensal habitual de todos os trabalhos, pessoas ocupadas com renda, em salários mínimos de cada ano);
  o cálculo está em `coleta/renda.py` e o resultado em `dados/referencia/renda_trabalho.json`.

## Cópias públicas e preservação

Os dados não dependem do site: a página `/dados-abertos` diz onde estão as cópias e lista cada arquivo de
`site/dados/` com o tamanho e a impressão digital (SHA-256), para qualquer cópia poder ser conferida
(`sha256sum dados.json`); mostra também como refazer tudo do zero (clonar, `python3 coletar.py tudo`,
`node publicacao/gerar.mjs`). O `gerar.mjs` grava a lista em `publicar/dados/manifesto.json` (`COPIAS` e
`DESCRICAO_ARQ`, no próprio `gerar.mjs`: uma cópia nova é uma linha em `COPIAS`). O rodapé de todas as páginas leva
para lá.

Cópias fora do repositório (a fazer uma vez, pelo dono da conta):

1. **Zenodo** (CERN): feito em 02/10/2026. Cada versão (release) publicada no GitHub vira uma cópia permanente, com
   DOI: uma por mês. `COPIAS` usa o DOI de todas as versões (10.5281/zenodo.23109646), que leva sempre à versão mais
   nova; a versão `2026-10` tem o DOI 10.5281/zenodo.23109647.
2. **Software Heritage**: feito em 02/10/2026 (primeira cópia). `COPIAS` usa o endereço sem data
   (`archive.softwareheritage.org/browse/origin/?origin_url=https://github.com/jflaloux/contas-do-poder`), que mostra
   a cópia mais nova; o Zenodo também manda cada versão para lá.
3. **Espelho no Codeberg**: feito em 02/10/2026 (https://codeberg.org/jflaloux/contas-do-poder). Cada `git push` manda
   a versão para o GitHub e para o Codeberg ao mesmo tempo; não é um espelho que se atualiza sozinho (o Codeberg
   desativou os espelhos que puxam sozinhos, pull mirror, e no GitLab isso é recurso pago). Está em `COPIAS`.
4. **Internet Archive**: "Save Page Now" (web.archive.org/save) nas páginas principais.
5. **Contas**: verificação em duas etapas no GitHub, no Cloudflare e no registro do domínio; bloqueio de transferência
   do domínio ligado.

## Sobre e privacidade (`/sobre`)

Texto curto, em linguagem neutra, para quem quer saber o que é o site, que dados das pessoas ele mostra, o que o Google
Analytics mede, como não ser medido e como pedir correção ou retirada. O texto está em `site/sobre.json` (uma fonte só):
o `app.js` o lê (`secSobre`) e o `gerar.mjs` faz com ele a página pronta em HTML (`publicar/sobre.html`); dentro do texto
só existe `[texto](endereço)`, para links. Está no rodapé de todas as páginas e em `/dados-abertos`. O que a página afirma
e onde conferir: sem cookies próprios (nenhum `document.cookie` nem armazenamento no `app.js`; o teste `rodar.mjs` confere
que o site não cria cookies; os do Google Analytics só existem em `contasdopoder.com`), medição só em produção
(`index.html`), CPF e fornecedor pessoa física como no `CLAUDE.md`, letras do próprio site (`site/fontes/`, nada pedido ao Google; o teste confere que o site não pede nada de fora) e
hospedagem no Cloudflare Pages. A base legal escrita é o legítimo interesse (LGPD, art. 7º, IX). Quem é o controlador aparece como
"Contas do Poder (contato@contasdopoder.com)": se o nome do responsável entrar, é só mudar o `sobre.json`. Mudou algo
dessa lista (um serviço novo, um cookie, outro dado coletado)? Atualize o `sobre.json` junto, com a data. O texto é simples e deve ser revisto por quem responde pelo site antes de cada mudança publicada.

## Para a imprensa (`/imprensa`)

Página curta e neutra para quem vai citar os dados (pedido do revisor externo, aprovado em 04/10/2026): o que é o site, o método em poucas
linhas com os links de `/sobre`, `/atualizacao`, `/correcoes` e `/dados-abertos`, a licença CC BY 4.0 e o modelo de citação ("Contas do Poder
(contasdopoder.com), a partir de <fonte oficial>, consultado em <data>."), o contato, que o site descreve o que as fontes mostram, sem juízo, e que
erros são corrigidos e registrados. Sem o nome de ninguém e sem link para o usuário do GitHub: o código é apontado por `/dados-abertos`. Mesmo
mecanismo da `/sobre`: o texto está em `site/imprensa.json` (mesmo formato; `secSobre(IM, "imprensa")` no `app.js`, e o `gerar.mjs` faz `publicar/imprensa.html`),
o endereço `imprensa` está em `RESERVADOS` (`coleta/enderecos.py`), a página está no rodapé de todas as páginas e na `/sobre`, e custa 2 arquivos no
Cloudflare Pages. O `regras.mjs` confere o HTML pronto (links, licença, citação, sem nome e sem GitHub) e o `rodar.mjs` abre a página.

### Textos do site que dependem dos dados (`data-dado`)

Contagens e coberturas escritas à mão envelhecem (o Judiciário continuou "fora das páginas do site" e a Paraíba e o Ceará, os "únicos" do interior, muito depois
de isso deixar de ser verdade). No `site/index.html`, o que vem dos dados é `<span data-dado="chave">valor de reserva</span>`: o `gerar.mjs`
(`VALORES_DADO`) troca o valor de reserva pelo que `site/dados/` diz (número de câmaras e de vereadores, as capitais com vereador por vereador e com
Prefeitura, quantos estados têm a folha mês a mês e quais ficam de fora, os estados do interior "por cargo"), e o valor de reserva vale quando o
`site/` é aberto sem o build. O número de câmaras da seção de vereadores do `app.js` vem do arquivo das cidades. Os textos de `DESCRICAO_ARQ`
(`/dados-abertos`) que citam contagem usam os dados também. O que não dá para gerar (a razão de cada estado ficar sem folha, o que cada capital publica) fica
escrito à mão, e o `regras.mjs` falha se os dados mudarem de um jeito que o texto fixo não prevê (por exemplo, outro estado entrar em `interior/`). Assunto novo com
número no texto: um `<span data-dado>` e uma linha em `VALORES_DADO`, e o teste. A pendência da verba que uma Câmara não deixa ler (`<li id="pendencia-verba">`, "O que ainda falta") também vem dos dados: `verba-fora`, calculado
pelo `gerar.mjs` com o `verba_fora` de cada cidade em `camaras.json` (hoje Maceió e Recife, 2025 e 2026), e o `<li>` sai do HTML quando nenhuma cidade tem. O teste confere a
cobertura que existe DE VERDADE (nenhum vereador dessas cidades tem despesa `c` nos anos de fora; e nenhuma cidade com `verba_nome` e sem despesa fica sem a pendência),
e não o limite legal da verba (`verba_mes`, que existe mesmo sem despesas: a pendência do Recife saiu por engano em 04/10/2026 por isso). A frequência de atualização escrita nos textos
(`/imprensa`, `/sobre`, `/atualizacao`, `/dados-abertos`, notas das páginas de estado e do índice) segue a de verdade: as fontes que abrem de fora do Brasil, toda semana (GitHub, terça);
as que só abrem do Brasil, uma vez por mês; a fonte congelada, a cada três meses; na dúvida, "a cada rodada de atualização"

## Presença e projetos na página do deputado federal e do senador

Um bloco "Presença e projetos" (`secAtividade`, no `app.js`), lido de `site/dados/atividade.json` (um arquivo; o `gerar.mjs` o põe
em `<link rel="preload">` só nas páginas de deputado e senador; a página de "tudo junto" de quem foi ministro usa o registro
do mandato). Regras do bloco: "X de Y", sem porcentagem, sem cor, sem ranking, sem média do grupo e sem somar os tipos num total
de projetos. A **presença da Câmara** é por dia com sessão deliberativa no Plenário e a do **Senado**, por votação nominal
(o Senado não publica a presença por sessão nos dados abertos): nunca aparecem lado a lado nem se comparam, e o texto de cada
casa diz qual é a conta ("em que estava no mandato": suplente e ex-ministro têm poucos dias). Os **projetos** (PL, PLP, PEC, PDL e
projeto de resolução, desde 01/02/2023) vão em tabela por tipo, separando "homenagens e datas" dos "demais", cada grupo com os que
viraram norma; a lista dos que viraram norma tem o link de cada um e a marca "homenagem ou data" em texto. Uma nota diz a regra de
"homenagem ou data" (vem do `meta.regra_homenagem`), que a norma fica com o projeto principal e, no Senado, que a PEC lista como
autores todos os que assinaram. No celular a tabela vira um bloco por tipo (`.tabela-projetos`), sem rolagem para o lado. Se o `atividade.json` não carregar (404, rede ou formato errado), a seção diz "Não foi possível carregar a presença e os projetos agora" com um botão "Tentar de novo" e **para de pedir** (`ATIV.falhou`; "carregando" e "falhou" são coisas diferentes: antes, a promessa resolvia com null, a seção se recriava e pedia de novo, em ciclo, e a página podia travar). Os bens declarados (`BENS.falhou`) somem em silêncio no mesmo caso. Os testes simulam o arquivo ausente (404) e quebrado, e limitam quantas vezes o arquivo é pedido. O teste
do site confere um deputado (Laura Carneiro) e um senador (Alan Rick): os textos de cada casa, que não há "%" e que a conta de uma
casa não aparece na outra.

## Interior do ES, de PE e do RJ na página da cidade (valor por cargo)

Nesses três estados o Tribunal de Contas só publica o **total pago a um cargo** e **quantas pessoas** estavam nele, não o
valor de cada pessoa (`site/dados/interior-cargo/<uf>.json`, outro formato que o de `interior/`, da Paraíba e do Ceará: não
misturar as pastas). A página da cidade diz o que isso é: "em média, o total pago ao cargo dividido por N pessoas", nunca "o
vereador recebe". Por isso, para essa média: sem o selo "passa do teto", sem "ganha mais que X%", sem comparação com cidades
de outro tipo e sem página nem arquivo por pessoa (o app só baixa o arquivo do estado da cidade aberta; a lista dos estados
vai em `<meta name="dados-interior-cargo">`, posta pelo `gerar.mjs`; o Cloudflare não ganha nenhum arquivo além dos 3 do
dados). No `app.js`: `vereadoresCargo` (a Câmara: a média por vereador, o total do último mês e quantas pessoas, quem está
no cargo no ES e em PE, o teto só como referência, a tabela mês a mês com o 13º, as férias e a parte indenizatória no ES)
e `secPrefeituraCargo` (prefeito e vice no ES e em PE: com uma pessoa só no cargo, o total é o valor dela). No RJ a fonte diz
"agente político" e não tem nomes (continua a lista dos eleitos do TSE). Cidade sem o valor típico (`vm`), como Cariacica
(23 pessoas para 19 cadeiras), mostra só o total e a quantidade. Recife (`camaras.json`) e Vitória (`prefeituras.json`, só
o prefeito) usam os dados próprios. O texto da página pronta e o de compartilhar dizem "em média" e o tribunal. O teste do site
tem uma cidade de cada estado (Vitória, Cariacica, Abreu e Lima, Águas Belas e Laje do Muriaé) e falha se aparecer "passa do
teto" ou "ganha mais que" nelas.

## Atualização dos dados (`/atualizacao`)

A página mostra, para cada uma das fontes do site, até que mês vão os dados (`Dados até`), o dia da última coleta que
deu certo e a situação: em dia, atraso da própria fonte (com o motivo), atrasada ou coleta que falhou. Lê
`site/dados/situacao.json`, a versão pública de `dados/processados/situacao.json` (feita pelo agente dos dados no fim de
cada rodada, sem erro técnico nem caminho de arquivo); a frase de cada situação vem pronta do arquivo. O `gerar.mjs`
faz a mesma página em HTML (`publicar/atualizacao.html`) e o `app.js` a redesenha (`secAtualizacao`). Ligada ao rodapé
de todas as páginas e a `/dados-abertos`. O endereço é fixo: o nome `atualizacao` tem de estar em
`RESERVADOS` de `coleta/enderecos.py` (os nomes de página que nenhuma pessoa pode ter). Custo no Cloudflare Pages: 2 arquivos
(`atualizacao.html` e `dados/situacao.json`).

Nas páginas das Assembleias (`secAssembleia`), quando os deputados no cargo são em número diferente das cadeiras, uma
nota diz só o que a fonte mostra (`notaCadeiras`): Goiás (uma vaga aberta desde 26/09/2026) e Alagoas (a folha paga mais
subsídios do que há cadeiras) têm texto próprio, que some quando os números voltam a bater.

### O que mudou nesta rodada (chave `rodada` do `situacao.json`)

No topo de `/atualizacao`, logo abaixo da data da lista (`blocoRodada`, no `app.js`; o `gerar.mjs` faz o mesmo na página pronta), um
bloco resume a rodada semanal (a que começa na terça) comparada com a anterior, pela chave `rodada` do arquivo (`semana`,
`anterior`, `quebrou`, `voltou`, `continua`, com ids de `fontes`): "Rodada de 06/10/2026, comparada com a de 29/09/2026:" e três
itens ("2 fontes passaram a ter problema (...)", "1 voltou (...)", "nenhuma continua com problema"), cada nome com link para a
linha da fonte na lista (id `fonte-<id>` nas tabelas dos grupos; na lista "não estão em dia" a fonte se repete, então sem id). Sem
nenhuma mudança: "Rodada de ...: nenhuma mudança desde a de ...". Sem a chave ou com `anterior` nulo (a primeira rodada, o caso do
arquivo de 03/10/2026), o bloco não aparece. O atraso da própria fonte e as fontes congeladas não contam como problema, e a nota
embaixo diz isso. O teste liga uma rodada de mentira na resposta do arquivo (nomes de fontes reais) e confere o texto, que os links
levam à linha e que o arquivo real, sem rodada anterior, não mostra o bloco.

### Bens declarados à Justiça Eleitoral (`bens.json` e `bens-interior/<uf>.json`)

Um bloco "Bens declarados à Justiça Eleitoral" (`secBens`, na página da pessoa, e `secBensInterior`, na página da cidade do interior;
`app.js`) mostra o que a pessoa declarou ao TSE ao se candidatar (2018, 2022 ou 2024, conforme o mandato). **Os arquivos só existem a
partir de 26/10/2026** (regra eleitoral; o `dados` não os grava antes): o `gerar.mjs` põe `<meta name="dados-bens" content="br ce pb ...">`
com o que existe (`br` = `bens.json`, e as UFs de `bens-interior/`), e **sem os arquivos nada aparece, nem título nem aviso**, e o app nem
pede o arquivo (hoje é assim). Com eles: na página de quem tem registro (dep-, sen-, gov-, est-, ver-, pre-), o bloco fica à parte, depois
de "Comparar" e antes de "Compartilhar", sem botão no menu das seções; o `gerar.mjs` põe `bens.json` no preload só nessas páginas. Na
cidade do interior (CE, PB, ES, PE; o arquivo do estado só é baixado ao abrir uma cidade dele), uma lista de quem está no cargo e tem
declaração, prefeito e vice primeiro e os vereadores em ordem alfabética (nunca por valor), ligada pelo nome civil (ou o de urna, se não há
civil) como está nos arquivos da cidade. Texto: "Na candidatura de 2022, declarou ao TSE bens que somam R$ 366.907,22, em 5 itens: imóveis
...; veículos ...", só os tipos com valor; sem itens e sem total, "não declarou bens à Justiça Eleitoral"; sempre o aviso ("Declaração feita
pela própria pessoa ao se candidatar. Os valores são os informados por ela, em geral o valor de compra, e não o valor de mercado de hoje; a
Justiça Eleitoral não confere esses valores."), o link "Ver a declaração no TSE" (montado do modelo `meta.link` com `meta.regiao`,
`meta.eleicao` e o `ue` e o `sq` do registro; o formato do DivulgaCandContas é o que vier no arquivo) e o crédito (`meta.credito`). Regras: sem
ranking, "mais rico", média, comparação nem evolução; fora da imagem de compartilhar e dos números de destaque; nunca somado aos salários nem aos
gastos; só tipo e valor (sem descrição dos bens nem CPF); quem não deu para ligar a uma candidatura fica sem o bloco. Custo no Cloudflare
Pages: 5 arquivos novos (`bens.json` e 4 de `bens-interior/`, ~85 a 220 KB cada), de 14.192 para 14.197 de 20.000. O teste simula os arquivos
(a `<meta>` entra na página e a resposta do pedido é feita no próprio teste, com pessoas e nomes de verdade e valores de mentira; `simularBens`,
no `rodar.mjs`): confere o texto, o link, a ordem, "não declarou", a ausência de juízo, a página sem registro e a página sem os arquivos.

### Fontes congeladas e reserva pelo Tribunal de Contas (do `situacao.json`)

Dois usos do mesmo arquivo (`site/dados/situacao.json`), sem arquivo novo:

- **Congelada** (`situacao: "congelada"`): a fonte parou de publicar o que o site mostra (hoje, a folha do Pará e a do Rio de
  Janeiro, até mar/2026, e a Prefeitura de Campo Grande, até fev/2026). Em `/atualizacao` a situação tem a etiqueta cinza
  (`etiqueta--fora`, sem a cor de alerta: é um estado conhecido, não uma falha) e entra no "Como ler". Nas páginas afetadas
  (governador e vice do PA e do RJ, a página do estado e a Prefeitura de Campo Grande, na seção e na página da pessoa) uma linha diz
  "Folha até mar/2026: a fonte parou de publicar. O site mostra o último dado publicado (ver Atualização dos dados)" (`linhaCongelada`).
  O `gerar.mjs` põe a lista em `<meta name="fontes-congeladas" content="folhas/PA:202603 ...">` (id da fonte e último mês), e
  o `app.js` a lê dali: não pede o `situacao.json` à toa. A linha some sozinha quando a fonte deixa de estar congelada.
- **Reserva pelo Tribunal de Contas** (`reservas`, no mesmo arquivo): quando a coleta da fonte própria de uma capital falha ou
  fica atrás do tribunal, `ativa: true` faz a página da cidade usar o arquivo do tribunal no lugar da fonte própria, com um
  aviso (`avisoReserva`: "Dados do TCE-CE", o motivo, "vão até <mês>" e o link do tribunal). Hoje: Fortaleza (Câmara e Prefeitura,
  `interior/ce.json`, valor por pessoa), Câmara do Recife (`interior-cargo/pe.json`) e Prefeitura de Vitória
  (`interior-cargo/es.json`), as duas últimas com valor por cargo: "em média", sem "passa do teto" nem "ganha mais que", e
  nunca valor por pessoa e por cargo na mesma conta. O `situacao.json` só é lido nas cidades de
  `<meta name="reservas-tce">` (os códigos, postos pelo `gerar.mjs`) e o arquivo do tribunal só é baixado com a reserva ativa.
  Hoje todas estão com `ativa: false`; o teste liga uma por vez com dados simulados (`simularReservas`, no `rodar.mjs`, que
  responde o pedido do arquivo sem mexer em `site/dados/`; a Câmara do Recife ganha um vereador de mentira) e confere o
  aviso, o texto de cada tipo e o que não pode aparecer. Também confere que as páginas afetadas dizem "Folha até..." e que a
  de São Paulo (fonte em dia) não diz.

## Licença

- Código: MIT (arquivo `LICENSE`).
- Dados gerados (`dados/processados/` e `site/dados/`): CC BY 4.0, citando "Contas do Poder" e as fontes originais.
