# Contas do Poder

**Site: [contasdopoder.com](https://contasdopoder.com)**

Quanto ganha e quanto custa cada deputado federal, senador, ministro e o presidente, por mês, com números oficiais
da Câmara, do Senado e do Portal da Transparência. E também o salário de cada governador e vice (pela lei de cada
estado), a Câmara Municipal de cada cidade, cada vereador de treze capitais (São Paulo, Rio de Janeiro, Belo Horizonte, Fortaleza,
Goiânia, Maceió, Manaus, Natal, Porto Alegre, Recife, São Luís, Aracaju e Boa Vista) e o prefeito, o vice e os secretários de nove capitais (São Paulo, Recife, Fortaleza, Vitória,
Porto Alegre, Salvador, Curitiba, Natal e Campo Grande), além do prefeito e do vice do Rio de Janeiro, e os deputados estaduais de
São Paulo, Minas Gerais, Rio de Janeiro, Bahia, Pernambuco, Ceará, Paraíba, Goiás, Santa Catarina, Mato Grosso do Sul,
Rondônia, Tocantins, Sergipe, Espírito Santo, Rio Grande do Sul e Amapá.
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

Para a primeira visita ser rápida no celular, o `gerar.mjs` também divide os dados: `publicar/dados/indice/` tem
`dados.json`, `camaras.json` e `assembleias.json` sem a série mês a mês (`t`) e sem o detalhe dos gastos (`dt`) de cada
pessoa, que vão para `publicar/dados/pessoa/<id>.json` (com o nome de cada tipo de gasto e de cada fornecedor) e só são
baixados ao abrir a página daquela pessoa; por isso a lista `meta.tipos` das câmaras e das Assembleias, com milhares de
fornecedores, também fica fora da versão leve (ao abrir o site, os dados vão de cerca de 1,3 MB para cerca de 420 KB
comprimidos, já com os deputados estaduais). Os arquivos inteiros continuam em `publicar/dados/`, para quem reutiliza os
dados. Cada página pronta já traz o topo do contracheque (nome, custo por mês e de onde ele vem) e pede ao navegador
para baixar os dados junto com o `app.js` (`<link rel="preload">`). Sem o `gerar.mjs`, o `app.js` lê os arquivos
inteiros de `site/dados/`.

Para a página não pular enquanto carrega: o texto pronto fica na tela até o `app.js` ter a versão completa (aí uma
troca pela outra); os números do topo da página inicial já vêm no HTML; enquanto a fonte Barlow não chega, o site usa
uma fonte do sistema ajustada às medidas dela (`Barlow Reserva` no `estilo.css`); e cada gráfico é desenhado antes da
primeira pintura (`aoRedimensionar` no `app.js`). A lista das 5.570 cidades (`municipios.json`) só é baixada nas páginas que
mostram câmaras municipais (a inicial e a de cada cidade) ou quando a pessoa toca no campo de busca.

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
- **Salário médio da cidade**: o salário médio mensal do pessoal assalariado das empresas e outras organizações
  formais (inclui órgãos públicos), em reais, do Cadastro Central de Empresas do IBGE (tabela 9509 do SIDRA, ano mais
  recente: 2024), para pôr ao lado do teto do vereador. Uma consulta só para as 5.570 cidades
  (`dados/municipios/salario_medio.csv`), de novo a cada 30 dias. No `municipios.json` é o 9º campo de cada cidade.
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
| Ceará | Portal da Transparência da Alece: CSV mensal da folha de pagamento (categoria "DEPUTADOS") e CSV mensal da VDP | Salário e 13º da folha (remuneração bruta menos abate-teto; sem descontos pessoais); Verba de Desempenho Parlamentar empenho por empenho, com credor e CNPJ. Quem está no cargo: quem está na folha do mês |
| Paraíba | Portal da Transparência da ALPB: a planilha ODS dos eletivos da folha de cada mês | Subsídio da folha e a VIAP paga na folha (só o total do mês, sem fornecedores; as notas saem num arquivo por deputado). Jul/2025 sem planilha: vale o subsídio da lei |
| Rondônia | Portal da Transparência da ALE-RO: a página da verba indenizatória por gabinete e mês | Subsídio da lei (Lei 5.530/2023); verba nota a nota (prestador, CNPJ, classe), mais os reembolsos de saúde (só o valor). Quem está no cargo: a lista de gabinetes da página |
| Goiás | Portal da Transparência da Alego: o que a página usa (meses publicados, deputados com prestação no mês e a prestação de cada um) | Subsídio da lei (Lei 17.253/2011, redação da Lei 21.780/2023); verba indenizatória nota a nota (valor indenizado, fornecedor, CNPJ). Quem está no cargo: deputados com prestação no mês |
| Santa Catarina | Portal da Transparência da Alesc: CSV anual dos gastos dos gabinetes; a página de deputados para quem está no cargo hoje | Subsídio da lei (Lei 18.642/2023); diárias, passagens, telefone, veículos, aluguel e reembolsos do gabinete (sem CNPJ; nas diárias e passagens, sem o nome da pessoa) |
| Mato Grosso do Sul | Portal da Transparência da Alems: CSV anual da CEAP | Subsídio da lei (Lei 6.016/2022); CEAP nota a nota, com CNPJ e comprovante. Sem lista de deputados aberta: quem está no cargo sai dos meses com notas. Partido: o da candidatura de 2026 no TSE |
| Tocantins | Portal da Transparência da Aleto: a pesquisa da Verba Indenizatória (CODAP), que devolve um PDF por deputado e mês | Subsídio da lei (Lei 4.073/2022); CODAP nota a nota (emitente, CNPJ, valor), lida do PDF. O PDF não tem a categoria: ela sai do nome do emitente (posto, hotel, escritório de advocacia...). O total do mês é o valor ressarcido do PDF. A folha tem hCaptcha e não entra. Quem está no cargo: a lista de deputados da página |
| Sergipe | Portal da Transparência da Alese: o PDF mensal da folha de pagamento e o PDF mensal do ressarcimento dos deputados | Rendimentos da folha (subsídio, "outras verbas", 13º, auxílio; sem descontos nem líquido); ressarcimento por deputado e categoria (sem fornecedor), no mês da competência; equipe do gabinete (pessoas lotadas e soma dos rendimentos, sem nomes). Quem está no cargo: quem está na folha |
| Espírito Santo | Portal da Transparência da Ales (só abre do Brasil: roda no Mac): o que a página das cotas parlamentares usa, por gabinete e mês | Subsídio da lei (Lei 11.766/2022), desde fev/2025; cota por rubrica (diárias, passagens, divulgação, consultorias, aluguel), sem fornecedor. Quem está no cargo: os meses em que a página tem a tabela do gabinete (o titular licenciado fica sem tabela) |
| Rio Grande do Sul | Portal da Transparência da ALRS (só abre do Brasil: roda no Mac): o que as páginas "Gastos | Cotas" e "Remuneração de Servidores e Parlamentares" usam | Folha de cada deputado (remuneração bruta, parcelas indenizatórias, terço de férias, 13º; sem descontos), pela busca do nome completo do TSE; cota por gabinete, mês e rubrica (sem fornecedor). Quem está no cargo: os meses na folha (o titular licenciado sai da folha, mas o gabinete continua na lista de cotas e a cota fica no nome dele) |
| Amapá | Portal da Transparência da Alap (só abre do Brasil: roda no Mac): o que as páginas da CEAP e da consulta remuneratória de deputados usam | Folha de cada deputado (subsídio, GFE, auxílio-alimentação; sem descontos); CEAP por gabinete e mês, nota a nota (CNPJ, empresa, nota, valor). Quem está no cargo: os gabinetes da CEAP do mês (e, para quem não tem gabinete, os meses na folha) |

- Nome civil, gênero e eleito/suplente: arquivo de candidatos de 2022 do TSE (`consulta_cand_2022.zip`, ~4 MB, no
  cache). O nome parlamentar é casado com o nome de urna (igual, compatível ou, por último, o único eleito com as
  mesmas palavras, sem títulos como "Dr." ou "Cel.").
- O que cada uma das 27 Assembleias publica (verba, folha, equipe, subsídio, barreiras) está em
  `dados/referencia/assembleias.json`. As outras têm barreira (CAPTCHA, token) ou só PDF; ver o levantamento. PR: CAPTCHA.
  Próximos candidatos (levantados do Brasil): DF (folha mensal em CSV com a lotação do gabinete; notas da verba em
  XLSX, só de parte dos gabinetes), AM (cota por beneficiário, formulário sem CAPTCHA) e MA (total da CEAP por
  categoria, página por deputado e mês).
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
um servidor nos EUA, e o resto, do Brasil, pelo Mac e pelo Chrome). As capitais sem robô foram levantadas em
01/10/2026. A nota da lei do governador vem de `dados/governadores/governadores.json`. A folha do Mato Grosso pede
CAPTCHA: foi conferida à mão (o CAPTCHA resolvido por uma pessoa), e o robô não lê essa consulta. Em 01/10/2026: 25
estados com índice geral e 2 com um bloco a conferir (prefeituras de Maceió e de Cuiabá, cujas consultas são muito
lentas). Os blocos atrás de CAPTCHA (Câmara de Belo Horizonte, prefeitura de São Luís) foram conferidos à mão, com o
CAPTCHA resolvido por uma pessoa; o robô não lê essas consultas. O
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
títulos e números e Barlow no texto (Google Fonts, sem travar a primeira pintura). Tema claro e escuro em
`site/estilo.css` (variáveis no começo do arquivo); o ícone (`site/favicon.svg`) e a prévia do link (`site/og.png`)
seguem o mesmo desenho.

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
- Senado: [dados abertos legislativos](https://legis.senado.leg.br/dadosabertos/docs/) e
  [administrativos](https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html).
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

## Licença

- Código: MIT (arquivo `LICENSE`).
- Dados gerados (`dados/processados/` e `site/dados/`): CC BY 4.0, citando "Contas do Poder" e as fontes originais.
