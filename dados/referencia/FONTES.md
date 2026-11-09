# Tabelas de referência

## limites_cota_camara.csv

Valor mensal da Cota para o Exercício da Atividade Parlamentar (CEAP) por estado.

- Fonte: Câmara dos Deputados, "Guia para jornalistas — Cota Parlamentar"
  https://www2.camara.leg.br/comunicacao/assessoria-de-imprensa/guia-para-jornalistas/cota-parlamentar
- Consultado em 29/09/2026. A página diz "valores atuais", sem data de vigência.
- ATENÇÃO: os limites mudaram ao longo da legislatura. Usar só para o ano corrente
  até confirmarmos os valores de 2023, 2024 e 2025.
- O saldo não usado num mês acumula dentro do mesmo ano, então a comparação justa é
  gasto do ano ÷ (limite mensal × meses de mandato no ano).
- O deputado tem até 90 dias para apresentar notas: os 3 últimos meses ainda estão incompletos.

## limites_cota_camara_historico.csv

Limite mensal da CEAP por estado em cada vigência, para o balanço do mandato (`coleta/balanco.py`).

- Desde 1º/2/2023: Ato da Mesa nº 270/2023 (Anexo I). Os valores estão no texto atualizado do Ato da Mesa nº 43/2009
  ("Anexo com redação dada pelo Anexo ao Ato da Mesa nº 270, de 19/1/2023"), consultado em 09/11/2026:
  https://www2.camara.leg.br/legin/int/atomes/2009/atodamesa-43-21-maio-2009-588364-normaatualizada-cd-mesa.html
- Desde 20/2/2026: Ato da Mesa nº 244/2026, que atualiza os limites pelo IPCA de fev/2023 a dez/2025 e entra em vigor na
  publicação. O ato não traz a tabela no texto publicado; os valores são os de `limites_cota_camara.csv` (guia para
  jornalistas). Conferência: em todos os 27 estados, valor novo ÷ valor de 2023 = 1,1375 (o mesmo índice).
- Entre fev/2023 e fev/2026 não houve outra mudança da tabela (os Atos 113/2024 e 196/2025 mexem nas diárias e nos
  tipos de despesa, não nos limites).
- Fevereiro de 2026: o balanço usa a média dos dois valores pelos dias (19 dias do antigo, 9 do novo).
