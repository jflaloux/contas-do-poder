# Situação das fontes (04/11/2026 02:23, rodada: exterior)

Último mês fechado: 10/2026. 104 fontes: 90 ok, 4 com o atraso da própria fonte, 4 atrasadas, 2 falhando, 4 congeladas.

Desde a rodada anterior (semana de 27/10/2026):

- Quebrou: assembleias/pi (atrasada), folhas/AC (atrasada), judiciario/stm_oficial (atrasada), prefeituras/fortaleza (atrasada), prefeituras/salvador (falhando desde 03/11/2026).
- Voltou: judiciario/stf (agora: ok), judiciario/stm (agora: ok), judiciario/tse (agora: ok).
- Continua com problema: assembleias/mt (falhando desde 20/10/2026).

Reserva pelo Tribunal de Contas em uso: prefeituras/fortaleza (TCE-CE, o tribunal tem meses mais recentes que a fonte própria).

| Fonte | Situação | Último mês no site | Última coleta certa | Onde | Último erro ou motivo |
|---|---|---|---|---|---|
| assembleias/mt | falhando | 10/2026 | 2026-10-07 | exterior | ConnectTimeout: HTTPSConnectionPool(host='almt.eloweb.net', port=443): Max retries exceeded with url: /portaltransparenc |
| prefeituras/salvador | falhando | 09/2026 | 2026-11-03 | exterior | Recusado por perda de cobertura (fica o dado anterior): site/dados/prefeituras.json: p/cid=2927408: 19 para 1 com "x" pr |
| assembleias/pi | atrasada | 07/2026 | 2026-11-03 | exterior |  |
| folhas/AC | atrasada | 07/2026 | 2026-11-03 | exterior |  |
| judiciario/stm_oficial (só do Brasil) | atrasada | 04/2026 | 2026-10-08 | brasil |  Plano de queda: a consulta oficial só completa os meses que o DadosJusBr não tem: se ela falhar, o STM segue pelo DadosJusBr e os meses que faltam ficam sem dados (meses_sem_dados), como antes de 08/10/2026; os meses já lidos ficam; passou de 1 hora, congelar |
| prefeituras/fortaleza | atrasada | 07/2026 | 2026-11-03 | exterior |  |
| assembleias/ma (só do Brasil) | atrasada (fonte) | 05/2026 | 2026-10-22 | brasil | a Alema publica a prestação de contas de cada deputado com meses de atraso; o site vai até o último mês com 80% dos depu |
| assembleias/rj | atrasada (fonte) | 06/2026 | 2026-10-29 | brasil | ConnectTimeout: HTTPSConnectionPool(host='docigp.alerj.rj.gov.br', port=443): Max retries exceeded with url: /api/v1/con |
| folhas/SP | atrasada (fonte) | 04/2026 | 2026-10-27 | exterior | ValueError: max() arg is an empty sequence |
| prefeituras/recife | atrasada (fonte) | 06/2026 | 2026-11-03 | exterior | o arquivo de 2026 no portal de dados abertos da Prefeitura vai até jun/2026 (atualizado pela última vez em 26/06/2026, c |
| folhas/PA (só do Brasil) | congelada | 03/2026 | 2026-10-02 | brasil | desde abr/2026 a consulta pública da folha do Estado não mostra quem tem mandato eletivo |
| folhas/RJ (só do Brasil) | congelada | 03/2026 | 2026-10-02 | brasil | desde mar/2026 o governador em exercício é o presidente do Tribunal de Justiça, pago pelo Tribunal, e o cargo de vice es |
| prefeituras/campo_grande | congelada | 02/2026 | 2026-10-02 | brasil | a consulta da Prefeitura não traz a folha depois de fev/2026 |
| vereadores/recife | congelada | 09/2026 | 2026-10-20 | exterior | a consulta da verba indenizatória no servidor da Câmara do Recife retorna erro HTTP 500 desde 20/10/2026; a coleta da ve |
| assembleias/ac | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/al (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| assembleias/am (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/ap (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/ba | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/ce | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/df (só do Brasil) | ok | 09/2026 | 2026-10-27 | brasil |  |
| assembleias/es (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/go (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/mg | ok | 08/2026 | 2026-11-03 | exterior |  |
| assembleias/ms | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/pa | ok | 08/2026 | 2026-11-03 | exterior |  |
| assembleias/pb | ok | 08/2026 | 2026-11-03 | exterior |  |
| assembleias/pe | ok | 10/2026 | 2026-10-22 | brasil | ConnectionError: o robots.txt de dadosabertos.alepe.pe.gov.br não abriu (site fora do ar ou bloqueado) |
| assembleias/pr | ok | 09/2026 | 2026-10-27 | exterior | HTTPError: 429 Client Error: Too Many Requests for url: https://transparencia.assembleia.pr.leg.br/api/remuneracao/70004 |
| assembleias/rn | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/ro | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/rr | ok | 09/2026 | 2026-11-03 | exterior |  |
| assembleias/rs (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| assembleias/sc | ok | 10/2026 | 2026-11-03 | exterior |  |
| assembleias/se | ok | 09/2026 | 2026-11-03 | exterior |  |
| assembleias/sp | ok | 09/2026 | 2026-11-03 | exterior |  |
| assembleias/to | ok | 09/2026 | 2026-11-03 | exterior |  |
| federal/atividade | ok | 10/2026 | 2026-11-03 | exterior |  |
| federal/camara | ok | 10/2026 | 2026-11-03 | exterior |  |
| federal/executivo | ok | 08/2026 | 2026-11-03 | exterior |  |
| federal/municipios | ok | — | 2026-11-03 | exterior |  |
| federal/renda | ok | — | 2026-11-03 | exterior |  |
| federal/senado | ok | 10/2026 | 2026-11-03 | exterior |  |
| folhas/AL (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| folhas/AM (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/BA | ok | 09/2026 | 2026-11-03 | exterior |  |
| folhas/CE (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/DF | ok | 09/2026 | 2026-11-03 | exterior |  |
| folhas/ES | ok | 10/2026 | 2026-11-03 | exterior |  |
| folhas/GO | ok | 08/2026 | 2026-11-03 | exterior |  |
| folhas/MA (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/MG | ok | 09/2026 | 2026-11-03 | exterior |  |
| folhas/MS | ok | 09/2026 | 2026-11-03 | exterior |  |
| folhas/PB (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| folhas/PE | ok | 09/2026 | 2026-11-03 | exterior |  |
| folhas/PI (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| folhas/PR | ok | 10/2026 | 2026-11-03 | exterior |  |
| folhas/RN (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| folhas/RO | ok | 10/2026 | 2026-11-03 | exterior |  |
| folhas/RR | ok | 08/2026 | 2026-11-03 | exterior |  |
| folhas/RS | ok | 09/2026 | 2026-11-03 | exterior |  |
| folhas/SC | ok | 09/2026 | 2026-10-27 | exterior | ConnectionError: o robots.txt de dados.sc.gov.br não abriu (site fora do ar ou bloqueado) |
| folhas/SE (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| judiciario/cnj | ok | 09/2026 | 2026-11-03 | exterior |  |
| judiciario/pgr | ok | 09/2026 | 2026-11-03 | exterior |  |
| judiciario/stf | ok | 08/2026 | 2026-11-03 | exterior |  |
| judiciario/stj | ok | 09/2026 | 2026-11-03 | exterior |  |
| judiciario/stm | ok | 09/2026 | 2026-11-03 | exterior |  |
| judiciario/tse | ok | 09/2026 | 2026-11-03 | exterior |  |
| judiciario/tst | ok | 09/2026 | 2026-11-03 | exterior |  |
| prefeituras/curitiba | ok | 09/2026 | 2026-11-03 | exterior |  |
| prefeituras/natal (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| prefeituras/porto_alegre | ok | 09/2026 | 2026-11-03 | exterior |  |
| prefeituras/rio | ok | 09/2026 | 2026-11-03 | exterior |  |
| prefeituras/sp | ok | 08/2026 | 2026-11-03 | exterior |  |
| prefeituras/vitoria | ok | 09/2026 | 2026-11-03 | exterior |  |
| tce/ce | ok | 09/2026 | 2026-11-03 | exterior |  |
| tce/es | ok | 09/2026 | 2026-10-27 | exterior | RuntimeError: TCE-ES: arquivos que não baixaram (os meses deles ficaram como estavam): vinculo-2025-4: ('Connection abor |
| tce/pb | ok | 09/2026 | 2026-11-03 | exterior |  |
| tce/pe | ok | 09/2026 | 2026-11-03 | exterior |  |
| tce/rj | ok | 09/2026 | 2026-11-03 | exterior |  |
| vereadores/aracaju | ok | 09/2026 | 2026-11-03 | exterior |  |
| vereadores/belo_horizonte (só do Brasil) | ok | 10/2026 | 2026-10-02 | brasil |  |
| vereadores/boa_vista | ok | 09/2026 | 2026-11-03 | exterior |  |
| vereadores/cuiaba | ok | 09/2026 | 2026-10-08 | brasil | ConnectionError: o robots.txt de legislativo.camaracuiaba.mt.gov.br não abriu (site fora do ar ou bloqueado) |
| vereadores/fortaleza (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| vereadores/goiania | ok | 10/2026 | 2026-11-03 | exterior |  |
| vereadores/joao_pessoa | ok | 09/2026 | 2026-10-27 | exterior | HTTPError: 500 Server Error: Internal Server Error for url: https://joaopessoa.pb.leg.br/transparencia/recursos-humanos/ |
| vereadores/maceio (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/manaus (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/natal (só do Brasil) | ok | 08/2026 | 2026-10-22 | brasil |  |
| vereadores/porto_alegre (só do Brasil) | ok | 09/2026 | 2026-10-02 | brasil |  |
| vereadores/porto_velho | ok | 09/2026 | 2026-10-27 | exterior | AttributeError: 'str' object has no attribute 'get' |
| vereadores/rio_branco | ok | 10/2026 | 2026-11-03 | exterior |  |
| vereadores/rio_de_janeiro (só do Brasil) | ok | 10/2026 | 2026-10-02 | brasil |  |
| vereadores/sao_luis (só do Brasil) | ok | 09/2026 | 2026-10-22 | brasil |  |
| vereadores/sp | ok | 10/2026 | 2026-11-03 | exterior |  |
| vereadores/teresina | ok | 09/2026 | 2026-11-03 | exterior |  |
| vereadores/vitoria (só do Brasil) | ok | 09/2026 | 2026-10-08 | brasil |  |
| viagens/AM (só do Brasil) | ok | 09/2026 | 2026-10-03 | brasil |  |
| viagens/MG | ok | 10/2026 | 2026-11-03 | exterior |  |
| viagens/PB (só do Brasil) | ok | 09/2026 | 2026-10-03 | brasil |  |
| viagens/SE (só do Brasil) | ok | 09/2026 | 2026-10-03 | brasil |  |
| viagens/SP | ok | 10/2026 | 2026-11-03 | exterior |  |
