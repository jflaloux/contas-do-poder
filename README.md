# Contas do Poder

Quanto ganha e quanto custa cada deputado federal e senador, com números oficiais da Câmara e do Senado.
Um projeto [Contas do Brasil](https://contasdobrasil.com), criado por [Jean-François Laloux](https://laloux.me).

Este repositório tem os robôs que coletam os dados oficiais, a base unificada e o site.

## Como rodar

```bash
pip3 install -r requirements.txt
python3 coletar.py tudo          # Câmara + Senado + base unificada
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
`site/app.js` e os dados em `site/dados/dados.json`. Dá para hospedar de graça em qualquer serviço de
site estático. Para os links de compartilhamento apontarem para o endereço certo, preencha
`<meta name="endereco-do-site">` no `index.html` quando o site tiver domínio.

## Pastas

| Pasta | O que tem |
|---|---|
| `site/` | O site (protótipo) |
| `coleta/` | Código dos robôs (`camara.py`, `senado.py`), da base unificada (`padronizar.py`) e da conferência (`conferir.py`) |
| `dados/cache/` | Arquivos baixados. Pode apagar a qualquer momento (não vai para o Git) |
| `dados/brutos/` | Dados de cada fonte, já limpos |
| `dados/processados/` | Base usada pelo site |
| `dados/referencia/` | Tabelas fixas (limites da cota por estado) e suas fontes |

## A base (`dados/processados/`)

- `politicos.json` — um registro por político: nome, cargo, partido, estado, foto, se está em exercício, link oficial.
- `lancamentos.csv.gz` — (compactado) uma linha por **político · ano · mês · grupo · categoria · descrição · valor · fonte**.
  A coluna `fonte` é um código; o endereço completo está em `metadados.json` → `fontes_por_lancamento`.
- `resumo.json` — totais prontos: por ano, na legislatura e média mensal, separados em "ganha" e "custa".
- `metadados.json` — data da coleta, categorias, salário mínimo de cada ano, fontes e **pendências conhecidas**.
- `conferencia.md` — resultado da última conferência com os sites oficiais.

### Ganha × custa

- **Ganha** (vai para a pessoa): salário, 13º, auxílio-moradia e outros auxílios, ajuda de custo.
- **Custa** (despesas do mandato): cota parlamentar, assessores do gabinete, diárias, passagens e outros gastos.

A verba de gabinete paga assessores. Ela **não** vai para o bolso do parlamentar, por isso fica em "custa".

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
