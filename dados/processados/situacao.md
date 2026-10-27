# Situação das fontes (27/10/2026 11:05, rodada: brasil)

Último mês fechado: 09/2026. 104 fontes: 90 ok, 4 com o atraso da própria fonte, 0 atrasadas, 7 falhando, 3 congeladas.

Desde a rodada anterior (semana de 20/10/2026):

- Quebrou: assembleias/df (falhando desde 22/10/2026).
- Voltou: nada.
- Continua com problema: assembleias/mt (falhando desde 20/10/2026), assembleias/rj (falhando desde 20/10/2026), federal/atividade (falhando desde 20/10/2026), federal/camara (falhando desde 20/10/2026), judiciario/pgr (falhando desde 20/10/2026), vereadores/recife (falhando desde 27/10/2026).

| Fonte | Situação | Último mês no site | Última coleta certa | Onde | Último erro ou motivo |
|---|---|---|---|---|---|
| assembleias/df (só do Brasil) | falhando | 08/2026 | 2026-10-02 | brasil | ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) Plano de queda: a folha vem do CKAN (arquivo aberto, mais estável); se quebrar o PDF da verba, congelar só a verba |
| assembleias/mt | falhando | 09/2026 | 2026-10-07 | exterior | Recusado por perda de cobertura (fica o dado anterior): dados/assembleias/mt/equipe.csv: mês 01/2026: 24 para 0 linhas;  |
| assembleias/rj | falhando | 05/2026 | 2026-10-07 | exterior | Recusado por perda de cobertura (fica o arquivo anterior): dados/assembleias/rj/orcamentos.csv: o arquivo: 2864 para 118 |
| federal/atividade | falhando | 09/2026 | 2026-10-07 | exterior | ConnectionError: o robots.txt de dadosabertos.camara.leg.br não abriu (site fora do ar ou bloqueado) |
| federal/camara | falhando | 10/2026 | 2026-10-07 | exterior | a base desta rodada ficou com os dados de 07/10/2026 (FileNotFoundError: faltam camara_cota_site.csv em dados/ (a coleta |
| judiciario/pgr | falhando | 09/2026 | 2026-10-07 | exterior | HTTPError: 503 Server Error: Service Unavailable for url: https://transparencia.mpf.mp.br/conteudo/contracheque/remunera |
| vereadores/recife | falhando | 09/2026 | 2026-10-20 | exterior | Recusado por perda de cobertura (fica o dado anterior): site/dados/camaras.json: p/cid=2611606: 37 para 0 com "dt" preen Plano de queda: sem reserva no TCE-PE (ensaio de 07/10/2026: a folha da Câmara do Recife no TCE-PE vem sem nenhum vereador em todos os meses desde jan/2025; a reserva automática da situação só vale com dados do órgão no arquivo do tribunal); a folha e a verba ficam até o último mês lido; passou de 1 hora, congelar |
| assembleias/ma (só do Brasil) | atrasada (fonte) | 05/2026 | 2026-10-22 | brasil | a Alema publica a prestação de contas de cada deputado com meses de atraso; o site vai até o último mês com 80% dos depu |
| folhas/MG | atrasada (fonte) | 04/2026 | 2026-10-20 | exterior | a Secretaria de Planejamento publica a folha com alguns meses de atraso |
| folhas/SP | atrasada (fonte) | 04/2026 | 2026-10-20 | exterior | o Estado publica a série histórica com alguns meses de atraso |
| prefeituras/recife | atrasada (fonte) | 06/2026 | 2026-10-20 | exterior | o arquivo de 2026 no portal de dados abertos da Prefeitura vai até jun/2026 (atualizado pela última vez em 26/06/2026, c |
| folhas/PA (só do Brasil) | congelada | 03/2026 | 2026-10-02 | brasil | desde abr/2026 a consulta pública da folha do Estado não mostra quem tem mandato eletivo |
| folhas/RJ (só do Brasil) | congelada | 03/2026 | 2026-10-02 | brasil | desde mar/2026 o governador em exercício é o presidente do Tribunal de Justiça, pago pelo Tribunal, e o cargo de vice es |
| prefeituras/campo_grande | congelada | 02/2026 | 2026-10-02 | brasil | a consulta da Prefeitura não traz a folha depois de fev/2026 |
| assembleias/ac | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/al (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| assembleias/am (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/ap (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/ba | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/ce | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/es (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/go (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/mg | ok | 08/2026 | 2026-10-20 | exterior |  |
| assembleias/ms | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/pa | ok | 08/2026 | 2026-10-20 | exterior |  |
| assembleias/pb | ok | 08/2026 | 2026-10-20 | exterior |  |
| assembleias/pe | ok | 09/2026 | 2026-10-22 | brasil | ConnectionError: o robots.txt de dadosabertos.alepe.pe.gov.br não abriu (site fora do ar ou bloqueado) |
| assembleias/pi | ok | 07/2026 | 2026-10-20 | exterior |  |
| assembleias/pr | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/rn | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/ro | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/rr | ok | 07/2026 | 2026-10-20 | exterior |  |
| assembleias/rs (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/sc | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/se | ok | 08/2026 | 2026-10-20 | exterior |  |
| assembleias/sp | ok | 09/2026 | 2026-10-20 | exterior |  |
| assembleias/to | ok | 09/2026 | 2026-10-20 | exterior |  |
| federal/executivo | ok | 08/2026 | 2026-10-20 | exterior |  |
| federal/municipios | ok | — | 2026-10-20 | exterior |  |
| federal/renda | ok | — | 2026-10-20 | exterior |  |
| federal/senado | ok | 10/2026 | 2026-10-20 | exterior |  |
| folhas/AC | ok | 07/2026 | 2026-10-20 | exterior |  |
| folhas/AL (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| folhas/AM (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/BA | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/CE (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/DF | ok | 08/2026 | 2026-10-20 | exterior |  |
| folhas/ES | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/GO | ok | 08/2026 | 2026-10-20 | exterior |  |
| folhas/MA (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/MS | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/PB (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| folhas/PE | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/PI (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/PR | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/RN (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| folhas/RO | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/RR | ok | 08/2026 | 2026-10-20 | exterior |  |
| folhas/RS | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/SC | ok | 09/2026 | 2026-10-20 | exterior |  |
| folhas/SE (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| judiciario/cnj | ok | 09/2026 | 2026-10-20 | exterior |  |
| judiciario/stf | ok | 08/2026 | 2026-10-20 | exterior |  |
| judiciario/stj | ok | 09/2026 | 2026-10-20 | exterior |  |
| judiciario/stm | ok | 08/2026 | 2026-10-20 | exterior |  |
| judiciario/stm_oficial (só do Brasil) | ok | 09/2026 | 2026-10-08 | brasil |  |
| judiciario/tse | ok | 08/2026 | 2026-10-20 | exterior |  |
| judiciario/tst | ok | 09/2026 | 2026-10-20 | exterior |  |
| prefeituras/curitiba | ok | 09/2026 | 2026-10-20 | exterior |  |
| prefeituras/fortaleza | ok | 07/2026 | 2026-10-20 | exterior |  |
| prefeituras/natal (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| prefeituras/porto_alegre | ok | 09/2026 | 2026-10-20 | exterior |  |
| prefeituras/rio | ok | 09/2026 | 2026-10-20 | exterior |  |
| prefeituras/salvador | ok | 09/2026 | 2026-10-20 | exterior |  |
| prefeituras/sp | ok | 08/2026 | 2026-10-20 | exterior |  |
| prefeituras/vitoria | ok | 09/2026 | 2026-10-20 | exterior |  |
| tce/ce | ok | 08/2026 | 2026-10-20 | exterior |  |
| tce/es | ok | 08/2026 | 2026-10-20 | exterior |  |
| tce/pb | ok | 08/2026 | 2026-10-20 | exterior |  |
| tce/pe | ok | 09/2026 | 2026-10-07 | exterior |  |
| tce/rj | ok | 08/2026 | 2026-10-07 | exterior |  |
| vereadores/aracaju | ok | 09/2026 | 2026-10-20 | exterior |  |
| vereadores/belo_horizonte (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/boa_vista | ok | 08/2026 | 2026-10-20 | exterior |  |
| vereadores/cuiaba | ok | 09/2026 | 2026-10-08 | brasil | ConnectionError: o robots.txt de legislativo.camaracuiaba.mt.gov.br não abriu (site fora do ar ou bloqueado) |
| vereadores/fortaleza (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| vereadores/goiania | ok | 09/2026 | 2026-10-20 | exterior |  |
| vereadores/joao_pessoa | ok | 09/2026 | 2026-10-22 | brasil |  |
| vereadores/maceio (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/manaus (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/natal (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| vereadores/porto_alegre (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/porto_velho | ok | 09/2026 | 2026-10-20 | exterior |  |
| vereadores/rio_branco | ok | 09/2026 | 2026-10-20 | exterior |  |
| vereadores/rio_de_janeiro (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/sao_luis (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| vereadores/sp | ok | 09/2026 | 2026-10-20 | exterior |  |
| vereadores/teresina | ok | 08/2026 | 2026-10-22 | brasil |  |
| vereadores/vitoria (só do Brasil) | ok | 09/2026 | 2026-10-08 | brasil |  |
| viagens/AM (só do Brasil) | ok | 09/2026 | 2026-10-03 | brasil |  |
| viagens/MG | ok | 09/2026 | 2026-10-20 | exterior |  |
| viagens/PB (só do Brasil) | ok | 09/2026 | 2026-10-03 | brasil |  |
| viagens/SE (só do Brasil) | ok | 09/2026 | 2026-10-03 | brasil |  |
| viagens/SP | ok | 09/2026 | 2026-10-20 | exterior |  |
