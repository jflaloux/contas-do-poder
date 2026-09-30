# Contas do Poder

**Site: [contasdopoder.com](https://contasdopoder.com)**

Quanto ganha e quanto custa cada deputado federal, senador, ministro e o presidente, por mês, com números oficiais
da Câmara, do Senado e do Portal da Transparência. E também o salário de cada governador e vice (pela lei de cada
estado), a Câmara Municipal de cada cidade, cada vereador de seis capitais (São Paulo, Fortaleza, Goiânia, Manaus,
Natal e Recife) e o prefeito, o vice e os secretários de cinco capitais (São Paulo, Recife, Fortaleza, Vitória e
Porto Alegre).
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

## Ver o site no seu computador

```bash
python3 coletar.py site       # gera site/dados/ a partir da base
node publicacao/gerar.mjs     # monta publicar/, como o Cloudflare Pages
node publicacao/servir.mjs    # depois abra http://localhost:8000
```

O site é estático (HTML, CSS e JavaScript, sem instalar nada): `site/index.html`, `site/estilo.css`,
`site/app.js`, os dados em `site/dados/dados.json` e as fotos em `site/fotos/`. Dá para hospedar de graça em qualquer serviço de
site estático. Para os links de compartilhamento apontarem para o endereço certo, preencha
`<meta name="endereco-do-site">` no `index.html` quando o site tiver domínio.

## Pastas

| Pasta | O que tem |
|---|---|
| `site/` | O site. `site/fotos/` tem as fotos oficiais reduzidas (240×320, WebP, ~8 KB cada) |
| `coleta/` | Código dos robôs (`camara.py`, `senado.py`, `executivo.py`, `fotos.py`, `municipios.py`, `governadores.py`, `vereadores/`, `prefeituras/`), da base unificada (`padronizar.py`) e da conferência (`conferir.py`) |
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

## Governo federal (presidente, vice e ministros)

Robô `coleta/executivo.py`, com os arquivos de download do Portal da Transparência (CGU):

- **Quem**: cadastro mensal de servidores (cargos "Presidente da República", "Vice-Presidente da República" e
  "Ministro de Estado"). Só entra quem foi nomeado a partir de 01/01/2023.
- **Vai para o bolso**: remuneração mensal (salário já com o abate-teto, 13º, férias, outras remunerações
  eventuais e verbas indenizatórias) e **jetons** (conselhos de estatais e do Sistema S). O 13º aparece no
  Portal como adiantamento e, no fim do ano, inteiro; contamos uma vez só.
- **Gastos do cargo**: viagens a serviço (diárias + passagens + outros gastos − devoluções), no mês em que a
  viagem começou. Voos da FAB e do avião presidencial não têm custo publicado.
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

## Câmaras municipais (vereadores), passo 1

Robô `coleta/municipios.py`, para as 5.568 câmaras:

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

- Nome civil, gênero e partido: TSE (eleição de 2024); os nomes são casados entre as fontes com tolerância a
  abreviações e erros de digitação (`comum.semelhanca`).
- O CPF dos assessores não é guardado, e os descontos da folha (como empréstimos) não são lidos.
- SAPL de Fortaleza e de Natal: o robots.txt pede 60 s entre pedidos, então só pedimos a lista de mandatos e,
  em Fortaleza, no máximo 6 fotos por semana.
- Recife: em ago/2026 a folha traz também R$ 18.980 (o salário da legislatura passada) a vereadores e
  ex-vereadores daquela legislatura; não entram. A página da verba de alguns vereadores dá erro no site da
  Câmara: o site avisa e mostra a verba zerada nesse período.
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
  física (aluguel de imóvel) fica mascarado e o nome não aparece no site. Os 4 últimos meses são baixados de novo
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
as fotos. Uma cidade fora do ar não para as outras: o site usa o que já estava gravado.

| Cidade | Fonte | O que a folha dá |
|---|---|---|
| São Paulo | Portal de Dados Abertos, "Histórico de Remuneração dos Servidores Ativos" (CSV de ~21 MB por mês) | Remuneração do mês + "demais elementos" (13º, férias, auxílio-refeição, atrasados). Cedido: exceções 2 e 3 |
| Recife | Dados Abertos do Recife, "Servidores e salários" (CKAN, uma tabela por ano, filtrada pela função) | Proventos, férias e 13º ("natalina"). R$ 0 no mês = recebe de outro órgão |
| Fortaleza | Dados Abertos de Fortaleza, `relacao_AAAAMM.csv` (~24 MB por mês) | Só o total dos proventos: o que passa do normal da pessoa vira "outros". Menos de 30% do normal do cargo = recebe de outro órgão |
| Vitória | Dados Abertos de Vitória, conjunto "Pessoal" (API do portal, uma tabela por mês) | Só a remuneração bruta total. Quadro "cedido por outros órgãos" = recebe de outro órgão |
| Porto Alegre | Portal Transparência (Procempa), "Remuneração dos servidores": a pesquisa do mês e o CSV da pesquisa, como o botão do site | Remuneração básica, abate-teto, 13º (folha "natalina" de dezembro), férias, eventuais e jetons |

- **Vai para o bolso** = remuneração bruta da folha. Os acertos do mês da saída (acima do normal da pessoa, a partir
  de R$ 3 mil) ficam à parte e fora das médias. As prefeituras não publicam gastos por pessoa.
- **Pasta**: a folha diz o órgão de lotação, que nem sempre é a pasta. Siglas viram nomes por tabelas no código de
  cada cidade (conferidas nos sites das prefeituras e na imprensa); o que não se sabe fica como está. Em Fortaleza,
  os secretários regionais aparecem todos lotados na Secretaria de Governo (a Secretaria da Gestão Regional foi
  extinta em 2025): o site diz "secretário municipal, lotado na Secretaria Municipal de Governo".
- Vice que também é secretário (Recife, Fortaleza) aparece com um cargo só ("Vice-prefeito e secretário de ...").
- Nada de CPF: quando a fonte traz o CPF mascarado, ele não é guardado.
- **Belo Horizonte** publica a folha nominal, mas o portal bloqueia acessos automáticos (WAF): não tentamos
  contornar. **Curitiba** e as outras capitais ficam para depois.
- Saída: `site/dados/prefeituras.json`, que o site junta à lista de políticos (tipo `p`), com as notas de cada cidade.

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
As fotos do governador e do vice vêm do Wikimedia Commons (licença livre, com crédito).

**Para atualizar**: quando sair uma lei nova, acrescente uma linha em `subsidio`; quando mudar o governador, feche a
linha dele em `ocupantes` (`ate`) e abra outra (com `folha_nome`, o nome como aparece na folha, nos estados em que a
busca é pelo nome).

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
| PR | Portal da Transparência, "Remuneração" | Busca pelo nome e página de detalhes (20 meses) |
| RO | API do Portal da Transparência | Por cargo e mês, com as rubricas; o 13º numa folha à parte |
| RR | API do Portal da Transparência | Por nome e mês, com os lançamentos |
| SC | Dados abertos, "Remuneração dos servidores" | CSV mensal só com o bruto; o Estado só mantém os meses recentes |
| SP | Portal da Transparência, "Remuneração" | Arquivo do mês e série histórica (.rar, lida com `libarchive-c`) |

- Guardamos só o que a pessoa recebe (salário, 13º, férias, auxílios, outros, bruto) e o abate-teto. Nada de CPF
  (nem mascarado) e nada de descontos pessoais.
- No site: recebido = bruto menos o abate-teto. Quando dezembro traz o 13º inteiro e o adiantamento já foi pago no
  meio do ano, o adiantamento sai de dezembro (senão o 13º conta duas vezes). O mês da saída, com os acertos (férias
  não tiradas, 13º proporcional), é marcado e fica fora da média.
- Nos outros 16 estados, a folha nominal não abriu para o robô (bloqueio, painel Power BI, chave de acesso, portal
  fora do ar no período eleitoral).

## Compartilhamento e medição

- **Imagem para compartilhar**: no fim da página de cada parlamentar, o site mostra uma imagem 1080×1350 (4:5,
  aparece inteira no WhatsApp e no Telegram e serve para status e stories) com a foto, o custo dele por mês,
  a posição entre os colegas e a equipe. Botões: **Copiar imagem** (para colar em qualquer conversa),
  **Enviar imagem…** (abre o menu do celular: WhatsApp, Telegram...) e **Baixar imagem**. O texto e o link
  ficam ao lado. As fotos ficam no próprio site (`site/fotos/`) porque o site da Câmara não deixa outro
  endereço usar as fotos dele num canvas.
- **Prévia do link** (`site/og.png`, 1200×630) para WhatsApp e redes sociais.
- **Fotos do governo federal**: quem é deputado ou senador usa a foto oficial do Congresso. Os outros vêm do
  Wikimedia Commons (via Wikidata), só com licença livre e só retratos; o crédito fica em
  `site/fotos/creditos.json` e aparece no contracheque e na imagem. Quem não tem foto aparece com as iniciais.
- **Google Analytics** (`G-MK65PM0MCZ`). Eventos: `ver_parlamentar` (com a origem: busca, guia, estado,
  ranking, comparar, link ou navegação), `trocar_periodo`, `compartilhar` (whatsapp, copiar_imagem, enviar_imagem,
  baixar_imagem, copiar_texto, copiar_link), `abrir_compartilhar`, `comparar`, `ranking`, `ranking_completo`, `ver_estado` e `guia`.

## O que já foi conferido

- Cota do Senado: nossa soma bate **ao centavo** com o total oficial em 324 de 324 comparações (senador × ano).
- Cota da Câmara: 37 de 40 comparações da amostra batem ao centavo; as outras 3 diferem até 1,5%.
- Auxílio-moradia da Câmara em 2026: bate ao centavo com o total do site.

## Pendências conhecidas

Veja `metadados.json` → `pendencias`. As principais:

1. **Câmara:** desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) sumiram dos arquivos
   de dados abertos (cerca de R$ 4 milhões por mês). Completamos com o total mensal do site oficial.
2. **Senado:** o custo dos assessores é uma **estimativa** (liga a folha de pagamento à lotação atual de cada
   comissionado, pelo nome).
3. **Câmara:** ainda faltam o 13º, a ajuda de custo e as diárias dos deputados (no Senado já estão).
   Por isso, hoje o "ganha" dos deputados está um pouco subestimado.
4. **Governadores:** o mês a mês pela folha em 12 estados; nos outros, só o salário do cargo. Em AL, AP, GO, MA e RJ,
   o valor do cargo ainda é o da imprensa.
5. **Prefeituras:** Belo Horizonte (portal bloqueia robôs), Curitiba e as outras capitais ainda não foram feitas.
6. **Câmara Municipal do Recife:** a consulta da Verba Indenizatória está com erro no site da Câmara; os meses
   afetados ficam de fora até ela voltar (o robô tenta de novo toda semana).

## Fontes

- Câmara: [API de dados abertos](https://dadosabertos.camara.leg.br/swagger/api.html),
  [arquivos da cota](https://www.camara.leg.br/cotas/), páginas de cada deputado e
  [moradia](https://www.camara.leg.br/moradia/detalhamento).
- Senado: [dados abertos legislativos](https://legis.senado.leg.br/dadosabertos/docs/) e
  [administrativos](https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html).
- Governadores: leis e decretos legislativos das assembleias, diários oficiais, folhas de pagamento e tabelas
  oficiais dos estados (o link de cada valor está em `dados/governadores/governadores.json`).
- Prefeituras: [São Paulo](https://dados.prefeitura.sp.gov.br/dataset/remuneracao-servidores-prefeitura-de-sao-paulo),
  [Recife](https://dados.recife.pe.gov.br/dataset/servidores), [Fortaleza](https://dados.fortaleza.ce.gov.br/dataset/servidores),
  [Vitória](https://dadosabertos.vitoria.es.gov.br/) e
  [Porto Alegre](https://portaltransparenciapmpa.procempa.com.br/portalpmpa/fpRemuneracaoPesquisa.do?viaMenu=true).
- Renda de quem trabalha no Brasil ("ganha mais que X% dos brasileiros que trabalham"): microdados dos 4 trimestres
  mais recentes da [PNAD Contínua do IBGE](https://www.ibge.gov.br/estatisticas/sociais/trabalho/9173-pesquisa-nacional-por-amostra-de-domicilios-continua-trimestral.html?t=microdados)
  (rendimento mensal habitual de todos os trabalhos, pessoas ocupadas com renda, em salários mínimos de cada ano);
  o cálculo está em `coleta/renda.py` e o resultado em `dados/referencia/renda_trabalho.json`.

## Licença

- Código: MIT (arquivo `LICENSE`).
- Dados gerados (`dados/processados/` e `site/dados/`): CC BY 4.0, citando "Contas do Poder" e as fontes originais.
