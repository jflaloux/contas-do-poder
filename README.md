# Contas do Poder

Quanto ganha e quanto custa cada deputado federal, senador, ministro e o presidente, com números oficiais
da Câmara, do Senado e do Portal da Transparência.
Um projeto [Contas do Brasil](https://contasdobrasil.com), criado por [Jean-François Laloux](https://laloux.me).

Este repositório tem os robôs que coletam os dados oficiais, a base unificada e o site.

## Como rodar

```bash
pip3 install -r requirements.txt
python3 coletar.py tudo          # Câmara + Senado + governo federal + base unificada + fotos + arquivo do site
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

Projeto do Cloudflare Pages conectado a este repositório, sem comando de build e com `site` como pasta
de saída. Cada mudança no repositório publica o site automaticamente.

## Ver o site no seu computador

```bash
python3 coletar.py site               # gera site/dados/dados.json a partir da base
python3 -m http.server 8000 -d site   # depois abra http://localhost:8000
```

O site é estático (HTML, CSS e JavaScript, sem instalar nada): `site/index.html`, `site/estilo.css`,
`site/app.js`, os dados em `site/dados/dados.json` e as fotos em `site/fotos/`. Dá para hospedar de graça em qualquer serviço de
site estático. Para os links de compartilhamento apontarem para o endereço certo, preencha
`<meta name="endereco-do-site">` no `index.html` quando o site tiver domínio.

## Pastas

| Pasta | O que tem |
|---|---|
| `site/` | O site. `site/fotos/` tem as fotos oficiais reduzidas (240×320, WebP, ~8 KB cada) |
| `coleta/` | Código dos robôs (`camara.py`, `senado.py`, `executivo.py`, `fotos.py`), da base unificada (`padronizar.py`) e da conferência (`conferir.py`) |
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

## Compartilhamento e medição

- **Imagem para compartilhar**: no fim da página de cada parlamentar, o site mostra uma imagem 1080×1350 (4:5,
  aparece inteira no WhatsApp e no Telegram e serve para status e stories) com a foto, o custo dele por mês,
  a posição entre os colegas e a equipe. Botões: **Copiar imagem** (para colar em qualquer conversa),
  **Enviar imagem…** (abre o menu do celular: WhatsApp, Telegram...) e **Baixar imagem**. O texto e o link
  ficam ao lado. As fotos ficam no próprio site (`site/fotos/`) porque o site da Câmara não deixa outro
  endereço usar as fotos dele num canvas.
- **Prévia do link** (`site/og.png`, 1200×630) para WhatsApp e redes sociais.
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

## Fontes

- Câmara: [API de dados abertos](https://dadosabertos.camara.leg.br/swagger/api.html),
  [arquivos da cota](https://www.camara.leg.br/cotas/), páginas de cada deputado e
  [moradia](https://www.camara.leg.br/moradia/detalhamento).
- Senado: [dados abertos legislativos](https://legis.senado.leg.br/dadosabertos/docs/) e
  [administrativos](https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html).

## Licença

- Código: MIT (arquivo `LICENSE`).
- Dados gerados (`dados/processados/` e `site/dados/`): CC BY 4.0, citando "Contas do Poder" e as fontes originais.
