# Raio-X das fontes (03/10/2026)

As 91 fontes de `site/dados/situacao.json`, uma por uma: como o robô lê, onde roda, o que já deu problema, o tamanho do robô, quanta gente cobre, o risco de dar trabalho e o que fazer. Diagnóstico só: nenhum robô foi mudado. Gerado a partir do código, dos arquivos do site, do registro de tentativas e do log da rodada de 02/10.

## Resumo

- **Risco**: 17 fontes de risco alto, 31 de risco médio e 43 de risco baixo. As de risco alto: `judiciario/cnj`, `folhas/MA`, `folhas/PA`, `folhas/RJ`, `folhas/RN`, `assembleias/al`, `assembleias/ap`, `assembleias/df`, `assembleias/ma`, `assembleias/pa`, `assembleias/rr`, `assembleias/rs`, `vereadores/maceio`, `vereadores/belo_horizonte`, `vereadores/recife`, `vereadores/rio_de_janeiro`, `prefeituras/campo_grande`.
- **De onde vem o trabalho**: dos portais estaduais e municipais, cada um com seu formato. São 79 robôs (folhas e viagens dos governadores, Assembleias, Câmaras e Prefeituras das capitais), com 15.591 linhas, para 2.144 pessoas; 16 das 17 fontes de risco alto e as 4 falhas da rodada de 02/10 estão aí. Os 2 robôs dos Tribunais de Contas cobrem 7.507 pessoas em 407 cidades com 785 linhas; os 3 federais, 824 pessoas com 1.237. O caso extremo são os governadores: 24 robôs de folha e 5 de viagens para 58 pessoas (2 por robô), quando o subsídio dos 27 já vem da lei.
- **Tipo de acesso e problemas**: com o histórico curto, já houve problema na própria fonte em proporções parecidas nos três tipos de acesso (23% das fontes de acesso estável, 30% das de acesso intermediário e 22% das de página, formulário, PDF ou painel). O que separa o risco é o custo de manter e de consertar: nos portais estaduais e municipais, o robô de acesso estável tem em média 124 linhas, o de acesso intermediário 180 e o de página, formulário, PDF ou painel 312; e a dependência do Mac.
- **Dependência do Mac**: 30 das 91 fontes só abrem do Brasil e dependem do Mac ligado na terça (a rodada do GitHub não as alcança).
- **Histórico ainda curto**: o projeto começou em 29/09/2026; houve uma rodada completa no Mac (02/10) e uma no GitHub (29/09, com o código antigo). O registro de tentativas (`coletas_brasil.json`) existe desde 02/10 e o do exterior ainda não. Na rodada de 02/10, 4 de 79 fontes falharam: uma por ambiente (faltava o odfpy no Python do Mac, ALPB), uma por erro do robô (404 do mês ainda não publicado, RO), uma por queda da fonte (RR, 504, voltou em 03/10) e uma por erro 500 da fonte (verba da Câmara do Recife), que tirou a cidade do site até o conserto. Os commits por módulo (1 a 3) ainda refletem a construção, não consertos. Por isso o risco abaixo pesa sobretudo o tipo de acesso (o custo de manter) e a dependência do Mac. Vale refazer este raio-X com o histórico de `rodada-resumo.json` depois de 6 a 8 rodadas (fim de novembro).
- **Recomendação por fonte**: 33 manter semanal, 55 passar a mensal e 3 congelar ("dados até X"). Trocar por agregador não cabe hoje em nenhuma: o Judiciário já usa o DadosJusBr onde ele bate com a fonte (STF, STM, TSE e reserva do STJ e do PGR), e os Tribunais de Contas que cobrem capitais servem de reserva parcial (ver a 5ª mudança).

### As 5 mudanças que mais reduzem a manutenção

1. **Rodada do Brasil mensal e "pular quem está em dia".** Uma fonte que já tem o último mês fechado não tem nada novo até o mês seguinte fechar: pular essas fontes nas rodadas do meio do mês corta cerca de 3/4 das execuções (e das falhas passageiras a olhar). Com isso, a rodada do Mac (30 fontes só do Brasil) pode ser mensal: o Mac precisa estar ligado uma terça por mês, não toda semana. Exceção: as fontes que publicam mais de uma vez por mês (Câmara, Senado, CEAP de MS, SC e SP, TCE-PB) seguem semanais no GitHub.
2. **Congelar o que a fonte parou de publicar**, com "dados até X" no site e uma conferência a cada 3 meses: folha do Pará (até mar/2026), folha do Rio de Janeiro (até mar/2026) e Prefeitura de Campo Grande (até fev/2026). Hoje esses robôs rodam toda semana sem trazer nada.
3. **Governadores: a lei é o número, a folha é complemento.** O subsídio dos 27 já vem da lei; os 24 robôs de folha só acrescentam 13º, férias e abate-teto de 2 pessoas cada. Regra: folha de governador que quebrar e não se consertar em cerca de 1 hora fica congelada, sem prejuízo para a comparação entre estados, que usa a lei.
4. **Plano de queda nas 17 fontes de risco alto**: cada uma ganha no módulo o que fazer quando quebrar (reserva, ou "dados até X" e conserto só se couber em cerca de 1 hora). Junto, o ambiente igual nas duas rodadas: `pip install -r requirements.txt` no começo da rodada do Mac (1 das 4 falhas de 02/10 foi só isso). E o aviso da rodada mostra primeiro o que quebrou de novo (`rodada-resumo.json`, feito agora), em vez da lista inteira de problemas.
5. **Tribunal de Contas como reserva das capitais que ele cobre**, como o DadosJusBr no Judiciário: o TCE-CE tem prefeito, vice e vereadores de Fortaleza (até ago/2026; o robô da Prefeitura de Fortaleza está em jul/2026), o TCE-PE tem a Câmara do Recife (até ago/2026) e o TCE-ES o valor pago ao prefeito, ao vice e aos vereadores de Vitória. Não resolve a Prefeitura do Recife: no TCE-PE ela também para em jun/2026. Os secretários não estão nos TCs de valor por cargo.

### Regra para fonte nova

Concordo com a proposta ("só entra se cobre muita gente com um robô só ou se tem API ou arquivo aberto estável; portal frágil, só se o dado for muito importante"), com números e um ajuste: "muito importante" vira um teste objetivo.

Uma fonte nova entra se cumprir **uma** destas:

- **cobre 100 pessoas ou mais com um robô só** (hoje: Tribunais de Contas, cerca de 3.750 pessoas por robô; federais, cerca de 275; Assembleias e Câmaras das capitais, cerca de 40; folhas dos governadores, 2); ou
- **é API documentada ou arquivo aberto (CSV, JSON, XML, CKAN) que abre de fora do Brasil**: roda no GitHub, sem o Mac; ou
- **completa uma série que o site já mostra** (o mesmo cargo nos outros estados ou capitais) e não há lei nem agregador que dê o número. Nesse caso, portal frágil (página, formulário, PDF, painel, ou só do Brasil) entra **com o plano de queda escrito no módulo** antes do primeiro commit.

Fonte que só abre do Brasil conta como portal frágil (depende do Mac). Não entra: robô de portal frágil para 1 ou 2 pessoas quando a lei já dá o número (governador, vice). Os números por trás da regra: os robôs de portais estaduais e municipais têm cerca de 7 linhas de código por pessoa coberta, os dos Tribunais de Contas 0,1; 16 das 17 fontes de risco alto são do primeiro grupo; e o robô de página, formulário, PDF ou painel tem em média 2,5 vezes as linhas do de acesso estável.

### Resumo da rodada (feito)

No fim de cada rodada, `coleta/situacao.py` grava `dados/processados/rodada-resumo.json`: o que quebrou desde a rodada anterior, o que voltou e o que continua com problema, mais o histórico das últimas 26 rodadas (para o próximo raio-X). A rodada é a semana que começa na terça (a do GitHub e a do Mac são a mesma rodada); rodar `coletar.py situacao` de novo na mesma semana atualiza a rodada da semana, e a comparação é sempre com a semana anterior. A versão pública vai em `site/dados/situacao.json` (chave `rodada`, só ids e datas); o aviso do Mac e o resumo do GitHub mostram o mesmo.

## Como ler as tabelas

- **Acesso**: estável (API oficial documentada, arquivo aberto ou agregador), intermediário (a API interna do portal, o JSON que a página usa, sem documentação, que pode mudar sem aviso; ou planilha exportada de uma página simples) ou frágil (página HTML, formulário JSF/ScriptCase/ASP.NET, PDF, painel Power BI ou DevExpress).
- **Onde**: EUA (GitHub Actions, terça de manhã) ou Brasil (Mac, terça à tarde). Em 02/10 o Mac rodou quase tudo porque o GitHub ainda não tinha rodado com o código novo; a partir de 06/10, o Mac pega só as fontes de `SO_BRASIL` e as que falharem de fora.
- **Linhas · commits**: linhas do módulo da fonte (sem as partes comuns) e commits que mexeram nele.
- **Cobertura**: pessoas no arquivo do site (inclui quem já saiu do cargo; nas folhas e viagens, governador e vice).
- **Risco**: pontos = acesso (0, 1 ou 2) + só do Brasil (1) + problema já visto na fonte (1; 2 se recorrente ou ainda aberto) + robô grande ou lento (1: mais de 400 linhas para menos de 100 pessoas, ou rodada longa por limite de pedidos) − reserva automática (1). Alto: 3 ou mais; médio: 2; baixo: 0 ou 1.
- **Recomendação**: congelar quando a fonte parou de publicar; manter semanal quando a fonte publica mais de uma vez por mês e o risco não é alto; passar a mensal quando o risco é médio ou alto, a fonte só abre do Brasil ou cada rodada baixa arquivos grandes; manter semanal no resto (risco baixo, roda no GitHub, custo quase zero).

## Governo federal e Congresso

3 fontes, 1.237 linhas, 824 pessoas, 0 só do Brasil. Risco: 0 alto, 1 médio, 2 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `federal/camara` | API oficial + arquivos da cota + páginas de cada deputado (exceção ao robots.txt) | EUA | diária (API); mensal (folha) | 09/2026 | robots.txt passou a proibir /deputados/*/* em 18/09/2026 (exceção registrada) | 631 · 5 | 648 | **médio** (2): acesso intermediário; problema já visto na fonte | manter semanal |
| `federal/executivo` | arquivo aberto (Portal da Transparência, ~80 MB por mês) | EUA | mensal, ~2 meses depois | 07/2026 | — | 244 · 2 | 71 | **baixo** (0): acesso estável | passar a mensal (só há mês novo uma vez por mês) |
| `federal/senado` | API oficial (dados abertos legislativos e administrativos) | EUA | mensal (folha); contínua (cota) | 09/2026 | — | 362 · 1 | 105 | **baixo** (0): acesso estável | manter semanal |

## Judiciário

7 fontes, 699 linhas, 126 pessoas, 0 só do Brasil. Risco: 1 alto, 1 médio, 5 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `judiciario/cnj` | página (POST rem.php; valores dentro do JavaScript) | EUA | mensal | 08/2026 | números em formato americano e brasileiro misturados; às vezes perde o 1º algarismo do subsídio | 83 · 1 | 19 | **alto** (3): página, formulário, PDF ou painel; problema já visto na fonte | passar a mensal (sem reserva: o DadosJusBr não bate com a fonte) |
| `judiciario/tst` | arquivo aberto (CSV mensal) | EUA | mensal | 08/2026 | leiaute muda de um mês para outro; jun/2025 em MacRoman; aposentado como INATIVO ou APOSENTADO | 91 · 1 | 28 | **médio** (2): acesso estável; problema recorrente ou ainda aberto | passar a mensal (sem reserva: o DadosJusBr não bate com a fonte) |
| `judiciario/stf` | agregador (DadosJusBr, API e cópia do arquivo oficial) | EUA | mensal, ~dia 16 do mês seguinte | 07/2026 | dez/2025 com colunas e linhas repetidas; sinal das férias de jul/2026 (tratados) | 271 · 2 | 11 | **baixo** (1): acesso estável; problema já visto na fonte | manter semanal (já é o agregador) |
| `judiciario/stj` | API do portal de transparência (GET/POST, CSV detalhado) | EUA | mensal | 08/2026 | CSV com BOM duplo; retenção do teto marcada como "Remuneratória" (tratados) | 114 · 1 | 33 | **baixo** (1): acesso intermediário; problema já visto na fonte; com reserva | manter semanal (reserva pelo DadosJusBr) |
| `judiciario/stm` | agregador (DadosJusBr) | EUA | mensal, ~dia 16 do mês seguinte | 08/2026 | — | 271 · 2 | 18 | **baixo** (0): acesso estável | manter semanal (já é o agregador) |
| `judiciario/tse` | agregador (DadosJusBr) | EUA | mensal, ~dia 16 do mês seguinte | 07/2026 | — | 271 · 2 | 16 | **baixo** (0): acesso estável | manter semanal (já é o agregador) |
| `judiciario/pgr` | arquivo aberto (ODS do MPF, endereço previsível) | EUA | mensal | 08/2026 | — | 140 · 1 | 1 | **baixo** (-1): acesso estável; com reserva | manter semanal (reserva pelo DadosJusBr) |

## Governadores (folha)

24 fontes, 1.525 linhas, 48 pessoas, 10 só do Brasil. Risco: 4 alto, 7 médio, 13 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `folhas/PA` | API interna do portal | Brasil | mensal | 03/2026 (atraso da fonte) | desde abr/2026 a consulta não traz quem tem mandato eletivo | 49 · 1 | 2 | **alto** (4): acesso intermediário; só abre do Brasil; problema recorrente ou ainda aberto | congelar (dados até mar/2026; o subsídio continua pela lei) |
| `folhas/RJ` | API interna do portal (lenta; por matrícula) | Brasil | mensal | 03/2026 (atraso da fonte) | busca por nome passa de 60 s; desde mar/2026 o governador em exercício é pago pelo TJ | 40 · 1 | 2 | **alto** (4): acesso intermediário; só abre do Brasil; problema recorrente ou ainda aberto | congelar (dados até mar/2026; o subsídio continua pela lei) |
| `folhas/RN` | API do site (busca por nome) | Brasil | mensal | 09/2026 | exportação por órgão passou a dar 429 sempre; ~1 min por mês | 55 · 2 | 2 | **alto** (4): acesso intermediário; só abre do Brasil; problema já visto na fonte; robô grande ou lento | passar a mensal |
| `folhas/MA` | página (busca por nome e histórico do ano) | Brasil | mensal | 08/2026 | — | 85 · 1 | 2 | **alto** (3): página, formulário, PDF ou painel; só abre do Brasil | passar a mensal |
| `folhas/AC` | página (busca por nome e detalhe, com token do formulário) | EUA | mensal | 07/2026 | — | 67 · 1 | 2 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `folhas/AM` | API interna do portal | Brasil | mensal | 08/2026 | — | 43 · 1 | 2 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `folhas/BA` | painel Power BI (chave anônima da página) | EUA | mensal | 08/2026 | — | 129 · 1 | 2 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `folhas/PR` | página (busca por nome e detalhe; exceção ao robots.txt) | EUA | mensal | 08/2026 | — | 94 · 3 | 2 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `folhas/RR` | API interna do portal | EUA | mensal | 07/2026 | 02 e 03/10: API fora do ar (504); voltou sozinha | 51 · 1 | 2 | **médio** (2): acesso intermediário; problema já visto na fonte | passar a mensal |
| `folhas/RS` | painel Power BI (chave anônima da página) | EUA | mensal | 08/2026 | — | 141 · 1 | 2 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `folhas/SE` | API interna do portal | Brasil | mensal | 09/2026 | — | 53 · 1 | 2 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `folhas/AL` | API oficial documentada | Brasil | mensal | 08/2026 | — | 67 · 1 | 2 | **baixo** (1): acesso estável; só abre do Brasil | passar a mensal |
| `folhas/CE` | arquivo aberto (CSV mensal) | Brasil | mensal | 08/2026 | — | 53 · 1 | 2 | **baixo** (1): acesso estável; só abre do Brasil | passar a mensal |
| `folhas/DF` | API interna do portal (cabeçalho x-client-id) | EUA | mensal | 08/2026 | — | 54 · 1 | 2 | **baixo** (1): acesso intermediário | manter semanal |
| `folhas/MG` | arquivo aberto (CKAN, CSV de ~130 MB) | EUA | mensal, com meses de atraso | 03/2026 (atraso da fonte) | leiaute mudou em fev/2026; atraso da fonte | 53 · 2 | 2 | **baixo** (1): acesso estável; problema já visto na fonte | passar a mensal |
| `folhas/MS` | API interna do portal (chave anônima de /Auth/Token) | EUA | mensal | 08/2026 | — | 63 · 2 | 2 | **baixo** (1): acesso intermediário | manter semanal |
| `folhas/PB` | API de dados abertos (Codata) | Brasil | mensal | 08/2026 | — | 61 · 1 | 2 | **baixo** (1): acesso estável; só abre do Brasil | passar a mensal |
| `folhas/PI` | API oficial documentada | Brasil | mensal | 08/2026 | — | 52 · 1 | 2 | **baixo** (1): acesso estável; só abre do Brasil | passar a mensal |
| `folhas/SP` | arquivo aberto (CSV do mês e .rar da série) | EUA | mensal, com meses de atraso | 04/2026 (atraso da fonte) | o arquivo "atual" não diz o mês; atraso da fonte | 96 · 1 | 2 | **baixo** (1): acesso estável; problema já visto na fonte | passar a mensal |
| `folhas/ES` | arquivo aberto (CKAN, CSV de 85 a 195 MB) | EUA | mensal | 09/2026 | — | 50 · 2 | 2 | **baixo** (0): acesso estável | passar a mensal |
| `folhas/GO` | arquivo aberto (CSV e ZIP) | EUA | mensal | 08/2026 | — | 97 · 1 | 2 | **baixo** (0): acesso estável | manter semanal |
| `folhas/PE` | arquivo aberto (CKAN, CSV de ~34 MB) | EUA | mensal | 08/2026 | — | 56 · 2 | 2 | **baixo** (0): acesso estável | manter semanal |
| `folhas/RO` | API oficial documentada (swagger) | EUA | mensal | 09/2026 | 02/10: 404 no mês ainda não publicado (o robô lia como erro; corrigido) | 61 · 2 | 2 | **baixo** (0): acesso estável | manter semanal |
| `folhas/SC` | arquivo aberto (CKAN, CSV de ~22 MB) | EUA | mensal | 08/2026 | — | 37 · 2 | 2 | **baixo** (0): acesso estável | manter semanal |

## Viagens dos governadores

5 fontes, 261 linhas, 10 pessoas, 3 só do Brasil. Risco: 0 alto, 2 médio, 3 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `viagens/AM` | API interna do portal (SCDP) | Brasil | contínua | 09/2026 | — | 57 · 1 | 2 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `viagens/SE` | API interna do portal | Brasil | contínua | 09/2026 | — | 38 · 1 | 2 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `viagens/PB` | API de dados abertos (swagger) | Brasil | contínua | 09/2026 | — | 39 · 1 | 2 | **baixo** (1): acesso estável; só abre do Brasil | passar a mensal |
| `viagens/SP` | API interna do portal (POST da busca) | EUA | contínua | 09/2026 | — | 52 · 1 | 2 | **baixo** (1): acesso intermediário | manter semanal |
| `viagens/MG` | arquivo aberto (CKAN, ~42 MB; 10 s entre pedidos) | EUA | contínua | 09/2026 | — | 75 · 1 | 2 | **baixo** (0): acesso estável | passar a mensal |

## Assembleias Legislativas

27 fontes, 7.272 linhas, 1.191 pessoas, 8 só do Brasil. Risco: 7 alto, 10 médio, 10 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `assembleias/al` | página (relação nominal letra por letra e detalhe de cada pessoa) | Brasil | mensal | 09/2026 | ~18 s por letra; a letra sem nomes (X) devolve a lista do A; VIAP só em imagem | 271 · 1 | 30 | **alto** (5): página, formulário, PDF ou painel; só abre do Brasil; problema já visto na fonte; robô grande ou lento | passar a mensal |
| `assembleias/df` | arquivo aberto (CKAN) e PDF assinado da verba | Brasil | mensal | 08/2026 | o arquivo de fev/2026 no CKAN é cópia do de jun/2025; 13º em folhas à parte | 460 · 1 | 24 | **alto** (5): página, formulário, PDF ou painel; só abre do Brasil; problema já visto na fonte; robô grande ou lento | passar a mensal |
| `assembleias/rr` | arquivos ODT/PDF por deputado e mês (lista pelo admin-ajax da página) | EUA | mensal | 07/2026 | meses até ago/2025 dão 504; folha não publicada depois de set/2025; portal lento | 652 · 2 | 25 | **alto** (5): página, formulário, PDF ou painel; problema recorrente ou ainda aberto; robô grande ou lento | passar a mensal |
| `assembleias/ma` | formulário JSF/PrimeFaces (o número do deputado só sai do clique) | Brasil | mensal, com meses de atraso | 05/2026 (atraso da fonte) | atraso da fonte: prestação de contas publicada meses depois | 357 · 1 | 50 | **alto** (4): página, formulário, PDF ou painel; só abre do Brasil; problema já visto na fonte | passar a mensal |
| `assembleias/ap` | API interna do portal e páginas (CEAP e folha) | Brasil | mensal | 08/2026 | — | 323 · 2 | 28 | **alto** (3): página, formulário, PDF ou painel; só abre do Brasil | passar a mensal |
| `assembleias/pa` | painel DevExpress e páginas (frame_*.php) | EUA | mensal | 08/2026 | — | 403 · 1 | 42 | **alto** (3): página, formulário, PDF ou painel; robô grande ou lento | passar a mensal |
| `assembleias/rs` | páginas e chamadas ajax do portal (cotas e busca da folha) | Brasil | mensal | 08/2026 | — | 304 · 2 | 64 | **alto** (3): página, formulário, PDF ou painel; só abre do Brasil | passar a mensal |
| `assembleias/am` | formulário com exportação em CSV (CEAP) | Brasil | mensal | 08/2026 | — | 306 · 1 | 26 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `assembleias/es` | API interna do portal (cotas por gabinete) | Brasil | mensal | 08/2026 | — | 216 · 1 | 31 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `assembleias/go` | API interna do portal (verba nota a nota) | Brasil | mensal | 07/2026 | — | 223 · 2 | 46 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `assembleias/mt` | API interna do portal (Elotech) | EUA | mensal | 09/2026 | o portal carrega o reCAPTCHA (só ativo se a entidade for integrada ao Oxy) | 384 · 2 | 38 | **médio** (2): acesso intermediário; problema já visto na fonte | passar a mensal |
| `assembleias/pe` | API de dados abertos e páginas da verba (notas uma prestação por pedido) | EUA | mensal | 08/2026 | no máximo 400 prestações por vez | 169 · 1 | 51 | **médio** (2): acesso intermediário; robô grande ou lento | passar a mensal |
| `assembleias/pi` | formulário ScriptCase (pesquisa guardada na sessão) | EUA | mensal | 07/2026 | — | 379 · 1 | 40 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `assembleias/rj` | API interna do portal (DOCIGP; exceção ao robots.txt) | EUA | mensal, com meses de atraso | 05/2026 (atraso da fonte) | atraso da fonte: o mês sai depois da análise da prestação | 261 · 3 | 82 | **médio** (2): acesso intermediário; problema já visto na fonte | passar a mensal |
| `assembleias/ro` | páginas (verba por gabinete e mês) | EUA | mensal | 09/2026 | — | 180 · 2 | 25 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `assembleias/se` | PDF mensal (folha e ressarcimento) | EUA | mensal | 08/2026 | — | 336 · 2 | 26 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `assembleias/to` | PDF por deputado e mês (pela pesquisa da página) | EUA | mensal | 08/2026 | — | 242 · 1 | 24 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `assembleias/ac` | API interna do portal (lista de servidores) e página de deputados | EUA | mensal | 09/2026 | — | 162 · 1 | 25 | **baixo** (1): acesso intermediário | manter semanal |
| `assembleias/ba` | página (lista) e planilha mensal da verba | EUA | mensal | 09/2026 | — | 147 · 1 | 68 | **baixo** (1): acesso intermediário | manter semanal |
| `assembleias/pr` | API interna do portal e planilha de comissionados | EUA | mensal | 09/2026 | — | 342 · 1 | 56 | **baixo** (1): acesso intermediário | manter semanal |
| `assembleias/rn` | API aberta da lista de parlamentares (salário pela lei) | EUA | quando muda a composição | 09/2026 | verba e folha só por API com credencial (não usada) | 126 · 2 | 24 | **baixo** (1): acesso intermediário | manter semanal |
| `assembleias/sc` | arquivo aberto (CSV anual) e listas de deputados | EUA | contínua | 09/2026 | 02/10: listas de deputados fora do ar ou fechadas para o exterior (segue com as gravadas) | 167 · 3 | 49 | **baixo** (1): acesso estável; problema já visto na fonte | manter semanal |
| `assembleias/ce` | arquivo aberto (CSV do portal: folha e VDP) | EUA | mensal | 09/2026 | — | 214 · 3 | 64 | **baixo** (0): acesso estável | manter semanal |
| `assembleias/mg` | API oficial (webservice de dados abertos; exceção ao robots.txt) | EUA | mensal | 07/2026 | — | 210 · 2 | 82 | **baixo** (0): acesso estável | manter semanal |
| `assembleias/ms` | arquivo aberto (CSV anual da CEAP) | EUA | contínua | 09/2026 | — | 134 · 1 | 25 | **baixo** (0): acesso estável | manter semanal |
| `assembleias/pb` | arquivo aberto (ODS mensal) | EUA | mensal | 07/2026 | 02/10: faltava o odfpy no Python do Mac (ambiente, não a fonte) | 157 · 2 | 48 | **baixo** (0): acesso estável | manter semanal |
| `assembleias/sp` | arquivo aberto (XML de dados abertos) | EUA | diária (lista); anual atualizado (verba) | 08/2026 | — | 147 · 1 | 98 | **baixo** (0): acesso estável | manter semanal |

## Câmaras Municipais das capitais

13 fontes, 4.911 linhas, 561 pessoas, 8 só do Brasil. Risco: 4 alto, 6 médio, 3 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `vereadores/belo_horizonte` | páginas e POST do portal (10 s entre pedidos) | Brasil | mensal | 09/2026 | — | 469 · 1 | 43 | **alto** (4): página, formulário, PDF ou painel; só abre do Brasil; robô grande ou lento | passar a mensal |
| `vereadores/maceio` | páginas e PDF (folha nominal por lotação) | Brasil | mensal | 09/2026 | — | 595 · 1 | 34 | **alto** (4): página, formulário, PDF ou painel; só abre do Brasil; robô grande ou lento | passar a mensal |
| `vereadores/rio_de_janeiro` | páginas, ScriptCase (contracheque) e certificado incompleto | Brasil | mensal | 09/2026 | — | 868 · 2 | 59 | **alto** (4): página, formulário, PDF ou painel; só abre do Brasil; robô grande ou lento | passar a mensal |
| `vereadores/recife` | API interna do portal (Plone) e CSV da folha | EUA | mensal | 09/2026 | 02/10: verba com erro 500 (2025 e 2026); o arquivo vazio tirou a cidade do site (corrigido: não apaga mais) | 343 · 2 | 43 | **alto** (3): acesso intermediário; problema recorrente ou ainda aberto | passar a mensal (TCE-PE tem a folha da Câmara do Recife até ago/2026) |
| `vereadores/boa_vista` | PDF por vereador e mês | EUA | mensal | 08/2026 | — | 192 · 1 | 26 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `vereadores/fortaleza` | SAPL (API; 60 s entre pedidos) e API da Câmara (folha) | Brasil | mensal | 08/2026 | — | 260 · 1 | 69 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal (TCE-CE tem a folha da Câmara de Fortaleza) |
| `vereadores/manaus` | SAPL (API) e admin-ajax do portal (folha) | Brasil | mensal | 09/2026 | — | 254 · 1 | 44 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `vereadores/natal` | SAPL (API; 60 s entre pedidos) e páginas da cota | Brasil | mensal | 07/2026 | — | 186 · 1 | 30 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `vereadores/porto_alegre` | API interna do portal (portal-api v1) | Brasil | mensal | 09/2026 | — | 397 · 1 | 39 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `vereadores/sao_luis` | API interna do portal (datatables; meses com nomes irregulares) | Brasil | mensal | 08/2026 | — | 395 · 2 | 40 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `vereadores/aracaju` | planilha mensal no portal | EUA | mensal | 09/2026 | 01/10: portal fora do ar (o robô desiste logo) | 184 · 3 | 29 | **baixo** (1): acesso estável; problema já visto na fonte | manter semanal |
| `vereadores/goiania` | API interna do portal (NúcleoGov) | EUA | mensal | 09/2026 | — | 349 · 1 | 43 | **baixo** (1): acesso intermediário | manter semanal |
| `vereadores/sp` | API oficial (SPLegis) e arquivos de dados abertos | EUA | mensal | 09/2026 | — | 419 · 3 | 62 | **baixo** (1): acesso estável; robô grande ou lento | manter semanal |

## Prefeituras das capitais

10 fontes, 1.622 linhas, 334 pessoas, 1 só do Brasil. Risco: 1 alto, 3 médio, 6 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `prefeituras/campo_grande` | API interna do portal (SIG) | EUA | parada | 02/2026 (atraso da fonte) | sem folha depois de fev/2026 (conferido em 01/10) | 134 · 1 | 15 | **alto** (3): acesso intermediário; problema recorrente ou ainda aberto | congelar (dados até fev/2026) |
| `prefeituras/curitiba` | página ASP.NET com exportação em CSV | EUA | mensal | 08/2026 | — | 180 · 1 | 16 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `prefeituras/natal` | API interna do portal | Brasil | mensal | 09/2026 | — | 193 · 1 | 34 | **médio** (2): acesso intermediário; só abre do Brasil | passar a mensal |
| `prefeituras/porto_alegre` | formulário (pesquisa .do e CSV da pesquisa) | EUA | mensal | 09/2026 | — | 145 · 1 | 27 | **médio** (2): página, formulário, PDF ou painel | passar a mensal |
| `prefeituras/recife` | arquivo aberto (CKAN, um CSV de ~85 MB por ano) | EUA | irregular | 06/2026 (atraso da fonte) | arquivo de 2026 parado em jun/2026 (última atualização em 26/06) | 122 · 2 | 32 | **baixo** (1): acesso estável; problema já visto na fonte | passar a mensal (o TCE-PE também vai só até jun/2026 na Prefeitura do Recife) |
| `prefeituras/salvador` | API interna do portal | EUA | mensal | 09/2026 | — | 186 · 1 | 27 | **baixo** (1): acesso intermediário | manter semanal |
| `prefeituras/fortaleza` | arquivo aberto (CKAN, CSV de ~24 MB) | EUA | mensal | 07/2026 | — | 160 · 2 | 68 | **baixo** (0): acesso estável | manter semanal (TCE-CE tem prefeito e vice de Fortaleza) |
| `prefeituras/rio` | arquivo mensal (CSV sem o cargo: só prefeito e vice) | EUA | mensal | 09/2026 | — | 126 · 1 | 2 | **baixo** (0): acesso estável | manter semanal |
| `prefeituras/sp` | arquivo aberto (CKAN; exceção ao robots.txt) | EUA | mensal | 08/2026 | — | 244 · 3 | 92 | **baixo** (0): acesso estável | manter semanal |
| `prefeituras/vitoria` | API de dados abertos da Prefeitura | EUA | mensal | 08/2026 | — | 132 · 1 | 21 | **baixo** (0): acesso estável | manter semanal (TCE-ES tem o valor pago ao prefeito e ao vice) |

## Tribunais de Contas (interior)

2 fontes, 785 linhas, 7.507 pessoas, 0 só do Brasil. Risco: 0 alto, 1 médio, 1 baixo.

| Fonte | Acesso | Onde | Publicação | Último mês | Histórico | Linhas · commits | Cobertura | Risco | Recomendação |
|---|---|---|---|---|---|---|---|---|---|
| `tce/ce` | API oficial documentada (OpenAPI, SIM) | EUA | mensal | 08/2026 | 02/10: parou de responder ~12 min depois de 3 h com 3 pedidos por vez (agora 2) | 527 · 1 | 2.951 pessoas, 184 cidades | **médio** (2): acesso estável; problema já visto na fonte; robô grande ou lento | passar a mensal |
| `tce/pb` | arquivo aberto (ZIP anual, ~70 MB, atualizado todo dia) | EUA | diária | 08/2026 | — | 258 · 1 | 4.556 pessoas, 223 cidades | **baixo** (0): acesso estável | manter semanal |

## Fora desta lista

- Tribunais de Contas do Espírito Santo, de Pernambuco e do Rio de Janeiro (valor por cargo, `site/dados/interior-cargo/`): feitos em 03/10 por outra sessão e ainda fora de `site/dados/situacao.json` quando este raio-X foi gerado; cobrem 78, 184 e 91 cidades com 3 robôs.
- Fontes sem robô de folha (AP, MT e TO nos governadores; verba e folha da ALRN): CAPTCHA, navegador ou credencial; o site usa a lei.
