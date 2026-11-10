# Balanço 2023–2026: conferência

Feita em 09/11/2026 e refeita em 10/11/2026, depois de três revisões independentes, sobre a base padronizada de 04/11/2026 (`dados/processados/lancamentos.csv.gz`, rodada do GitHub) e
o `site/dados/balanco.json` gerado por `python3 coletar.py site` (`coleta/balanco.py`). As páginas oficiais foram lidas
em 09/11/2026.

Faixas de meses usadas: Câmara — folha fev/2023 a out/2026, cota fev/2023 a out/2026, verba de gabinete fev/2023 a
jul/2026 (a Câmara está quatro meses atrasada; dez/2024 não está na página de nenhum deputado e fica fora da
média da equipe); Senado — folha, CEAPS, outros gastos e equipe (estimativa) de fev/2023
a out/2026.

## (a) Soma do balanço × base

- **Balanço × perfis**: para as 755 pessoas (648 deputados, 107 senadores), recebeu = `per.leg.g`, cota + outros gastos =
  `per.leg.c` e equipe = `per.leg.e` do `dados.json`, sem nenhuma diferença acima de R$ 1. Na equipe do Senado, a
  comparação é com `e.eb` (a estimativa do mês inteiro, a do perfil); o balanço usa a estimativa pelos dias no cargo
  (R$ 1.128.727.383 contra R$ 1.168.113.220 do perfil). Nenhum perfil de deputado ou senador ficou fora do balanço.
- **Balanço × base bruta** (`lancamentos.csv.gz`, sem os ajustes do site): as diferenças são os ajustes que o site faz
  nos perfis: o salário pago pelo Congresso nos meses como ministro de 18 deputados e senadores (R$ 21.632.402, fica na
  página de ministro) e os pagamentos da Câmara fora do mandato de 8 deputados (no mês seguinte à saída, só o salário igual ao de um mês que já sai) (`site._sem_pagamento_fora_do_mandato`).
- **Base mudada nesta conferência** (perfis também; registrado em `site/dados/correcoes.json`): os outros gastos do
  mandato de 25 senadores que não estavam em exercício no dia da coleta (R$ 2.879.741, da página de transparência de cada
  um; `dados/senado/outros_gastos.csv`); e, pelo `site.py`, 11 perfis de deputados (pagamentos fora do mandato).
- Totais do balanço: Câmara R$ 4.701.988.000; Senado R$ 1.472.413.131 (R$ 343.685.749 sem a equipe estimada).

## (b) Cinco pessoas conferidas à mão

Valores do balanço × páginas oficiais, ano a ano. "Nossa" = soma do ano no `dados.json` (o mesmo do balanço).

**Pompeo de Mattos (dep-73486, RS, titular, 45 meses)** —
[página da Câmara](https://www.camara.leg.br/deputados/73486?ano=2025),
[remuneração](https://www.camara.leg.br/deputados/73486/remuneracao?ano=2025)

| Ano | Cota oficial | Nossa | Verba de gabinete oficial | Nossa |
|---|---|---|---|---|
| 2023 | 633.212,12 | 633.212 | 1.401.124,69 | 1.289.810 (sem janeiro, que é da legislatura anterior: 111.315,08) |
| 2024 | 667.819,06 | 667.819 | 1.369.151,29 | 1.369.151 |
| 2025 | 620.510,26 | 620.510 | 1.586.437,87 | 1.586.438 |
| 2026 | 416.925,15 | 409.375 | 1.100.589,97 | 1.100.590 |

Salário mês a mês igual ao da página de remuneração (39.293,32 até mar/2023; 41.650,92; 44.008,52 desde fev/2024;
46.366,19 desde fev/2025); o 13º e os acertos vêm do contracheque detalhado. Cota 2026: a página anual de hoje tem
R$ 7.550 a mais que a nossa coleta de 04/11 (notas de agosto a outubro que chegaram depois; o prazo é de 90 dias).
Balanço: cota R$ 2.330.917 = 108,2% do limite. A página oficial mostra "não utilizado: 0,00" em 2023, 2024 e 2025, e o
gasto de 2023 (633.212,12) passa de 12 × o limite do RS (46.669,70): são as passagens de ida e volta ao estado, que o
Ato da Mesa nº 43/2009, art. 2º, § 3º, paga além da cota e que a Câmara soma no total da cota.

**Leandre (dep-178832, PR, titular licenciada para ser secretária no Paraná)** —
[página da Câmara](https://www.camara.leg.br/deputados/178832?ano=2023),
[remuneração 2024](https://www.camara.leg.br/deputados/178832/remuneracao?ano=2024)

| Ano | Cota oficial | Nossa | Verba de gabinete oficial | Nossa |
|---|---|---|---|---|
| 2023 | 5.076,20 | 5.076 | 169.404,33 | 63.483 (janeiro de 2023, 105.921,41, é da legislatura anterior) |
| 2024 | sem cota | sem cota | 0,00 | 0 |
| 2025 | sem cota | sem cota | 4.406,32 | 4.406 |
| 2026 | 220.636,64 | 205.008 | 518.861,47 | 518.861 |

A página de remuneração mostra o subsídio todos os meses de 2024 e 2025, quando ela estava licenciada (histórico da
Câmara: licença de 15/2/2023 a 6/4/2026, com voltas de poucos dias em nov/2023, dez/2024 e nov/2025). O balanço conta 7,6
meses no cargo e divide o recebido por 44,9 meses (os meses em que ela recebeu o subsídio): média de R$ 47.819. Cota
2026: out/2026 tinha R$ 9.618 na coleta de 04/11 e tem R$ 24.642,77 hoje; ago/2026, R$ 26.002 × 26.606,29 (notas que
chegaram depois).

**Jorge Araújo (dep-235800, BA, suplente de 8/4 a 13/10/2026)** —
[página da Câmara](https://www.camara.leg.br/deputados/235800?ano=2026),
[remuneração](https://www.camara.leg.br/deputados/235800/remuneracao?ano=2026)

Cota 2026: oficial 166.901,94, nossa 166.902. Verba de gabinete 2026: oficial 578.742,38, nossa 578.742. Salário: abr
35.547,41 (dias do mês), mai a set 46.366,19, out 18.546,48 — igual. Balanço: 6,2 meses no cargo; a cota usada é 52,9% do
limite proporcional aos dias (Ato da Mesa nº 43/2009, art. 11); a equipe é dividida por 3,8 meses (abr a jul, a faixa
que a Câmara já publicou).

**Esperidião Amin (sen-22, SC, titular, 45 meses)** —
[transparência do Senado](https://www6g.senado.leg.br/transparencia/sen/22/?ano=2025),
[folha de jun/2025 (dados abertos)](https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/remuneracoes/2025/6/csv)

| Ano | CEAPS oficial | Nossa |
|---|---|---|
| 2023 | 356.041,23 | 329.929 (a página soma janeiro de 2023, da legislatura anterior) |
| 2024 | 389.786,11 | 389.786 |
| 2025 | 463.396,89 | 463.397 |
| 2026 | 300.984,09 | 285.925 (notas que chegaram depois de 04/11; a página é de 09/11) |

Folha: jun/2025 = 46.366,19 (normal) + 23.183,09 (13º, suplementar) + 5.500,00 (auxílios) = 75.049, igual ao nosso mês;
mar/2026 = 46.366,19 + 5.500,00 = 51.866, igual.

**Ana Paula Lobato (sen-6358, MA, 1ª suplente, três períodos no cargo)** —
[transparência do Senado](https://www6g.senado.leg.br/transparencia/sen/6358/?ano=2025)

| Ano | CEAPS oficial | Nossa |
|---|---|---|
| 2023 | 394.945,30 | 394.945 |
| 2024 | 413.351,17 | 413.351 |
| 2025 | 520.369,19 | 522.790 (nov/2025: R$ 76.170,66 na nossa cópia, R$ 73.749,64 no arquivo da CEAPS de hoje: o Senado mudou o mês depois da cópia, que para o ano passado valia 30 dias; agora vale 7) |
| 2026 | 374.836,62 | 374.837 |

Folha: jun/2025 = 46.366,19 + 23.183,09 (13º) = 69.549, igual; mar/2026 = 46.366,19, igual. Ela esteve fora do exercício
de 31/7 a 5/10/2026 e a folha mostra o subsídio em ago e set/2026: o balanço divide o recebido por 44,3 meses (42,1 no
cargo + os meses com subsídio). A equipe dela no balanço é a estimativa pelos dias no cargo: R$ 12.350.492 (R$ 13.528.333
no perfil, com os meses inteiros).

## (c) Maiores e menores médias por mês

Só quem tem 3 meses ou mais na média da parte. O que olhar está na seção seguinte.

**Câmara, Recebeu (sem a ajuda de custo): 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Lenir de Assis (dep-231911) | PR | 12,9 | 12,9 | 735.828 | 53.447 |
| Carla Dickson (dep-213762) | RN | 22,0 | 22,0 | 1.213.136 | 53.142 |
| Enfermeira Rejane (dep-230765) | RJ | 22,0 | 22,0 | 1.210.343 | 53.015 |
| Pastor Claudio Mariano (dep-230762) | PA | 11,5 | 11,6 | 657.979 | 52.862 |
| André Abdon (dep-178831) | AP | 15,0 | 15,0 | 838.515 | 52.810 |
| Glaycon Franco (dep-236284) | MG | 3,9 | 3,5 | 228.848 | 52.639 |
| Romero Rodrigues (dep-160629) | PB | 41,2 | 41,6 | 2.210.238 | 52.186 |
| João Carlos (dep-235869) | AM | 4,0 | 4,0 | 252.669 | 52.179 |
| Marcos Pereira (dep-204506) | SP | 45,0 | 45,0 | 2.385.556 | 52.139 |
| Ilacir Bicalho (dep-235620) | MG | 4,0 | 3,8 | 246.630 | 52.121 |

**Câmara, Recebeu (sem a ajuda de custo): 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Chiquinho Brazão (dep-204476) | RJ | 23,0 | 26,8 | 917.109 | 32.761 |
| Nivaldo Albuquerque (dep-194260) | AL | 3,0 | 3,1 | 158.031 | 36.528 |
| Wolmer Araújo (dep-182146) | MA | 4,1 | 4,1 | 200.368 | 39.163 |
| Eliza Virgínia (dep-220008) | PB | 4,0 | 4,0 | 210.721 | 41.678 |
| Priscila Costa (dep-226075) | CE | 6,7 | 6,7 | 325.831 | 42.178 |
| Paulo Marinho Jr (dep-128760) | MA | 8,1 | 8,1 | 385.307 | 42.179 |
| Flavinha (dep-225727) | MT | 4,0 | 4,0 | 209.590 | 42.337 |
| Luciano Galego (dep-227323) | MA | 4,0 | 4,0 | 211.281 | 42.408 |
| Henrique Júnior (dep-227324) | MA | 4,0 | 4,0 | 212.232 | 42.645 |
| Fábio Henrique (dep-68720) | SE | 3,8 | 3,9 | 210.416 | 43.036 |

**Câmara, Cota parlamentar: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) | % do limite |
|---|---|---|---|---|---|---|
| Vavá (dep-235712) | MG | 4,0 | 4,0 | 221.591 | 55.398 | 116,3 |
| Marcelo Nilo (dep-204558) | BA | 6,8 | 6,8 | 367.008 | 54.238 | 106,4 |
| Zé Adriano (dep-230768) | AC | 22,0 | 22,0 | 1.160.544 | 52.675 | 99,3 |
| Pompeo de Mattos (dep-73486) | RS | 45,0 | 45,0 | 2.330.917 | 51.798 | 108,2 |
| Vanderlan Alves (dep-234673) | CE | 6,1 | 6,1 | 312.949 | 51.576 | 99,2 |
| Gabriel Mota (dep-224117) | RR | 43,8 | 43,8 | 2.251.542 | 51.435 | 97,5 |
| Albuquerque (dep-220538) | RR | 45,0 | 45,0 | 2.295.212 | 51.005 | 96,8 |
| Eunício Oliveira (dep-74454) | CE | 41,1 | 41,1 | 2.089.548 | 50.869 | 102,6 |
| Helena Lima (dep-220537) | RR | 45,0 | 45,0 | 2.268.598 | 50.413 | 95,6 |
| Duda Ramos (dep-220540) | RR | 45,0 | 45,0 | 2.259.154 | 50.203 | 95,2 |

**Câmara, Cota parlamentar: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) | % do limite |
|---|---|---|---|---|---|---|
| Dr. Gonçalo (dep-212625) | MA | 3,9 | 3,9 | 1.138 | 289 | 0,6 |
| Nivaldo Albuquerque (dep-194260) | AL | 3,0 | 3,0 | 5.479 | 1.807 | 3,4 |
| Amom Mandel (dep-220715) | AM | 45,0 | 45,0 | 156.361 | 3.475 | 6,9 |
| Marcio Alvino (dep-178983) | SP | 45,0 | 45,0 | 190.677 | 4.237 | 9,6 |
| João Carlos (dep-235869) | AM | 4,0 | 4,0 | 21.201 | 5.362 | 9,5 |
| Adriana Ventura (dep-204528) | SP | 45,0 | 45,0 | 300.643 | 6.681 | 15,2 |
| Renan Ferreirinha (dep-225386) | RJ | 4,8 | 4,8 | 51.060 | 10.615 | 25,5 |
| Sandro Alex (dep-160621) | PR | 9,5 | 9,5 | 110.430 | 11.627 | 23,7 |
| Gilson Marques (dep-204365) | SC | 45,0 | 45,0 | 623.257 | 13.850 | 29,6 |
| Pastor Sargento Isidório (dep-204553) | BA | 45,0 | 45,0 | 644.968 | 14.333 | 31,2 |

**Câmara, Outros gastos do mandato: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Gorete Pereira (dep-129618) | CE | 4,1 | 4,1 | 17.718 | 4.360 |
| Claudio Cajado (dep-74537) | BA | 45,0 | 45,0 | 163.594 | 3.635 |
| João Carlos Bacelar (dep-141458) | BA | 45,0 | 45,0 | 142.227 | 3.161 |
| Aguinaldo Ribeiro (dep-160527) | PB | 45,0 | 45,0 | 119.653 | 2.659 |
| Hugo Motta (dep-160674) | PB | 45,0 | 45,0 | 115.389 | 2.564 |
| Danilo Forte (dep-62881) | CE | 45,0 | 45,0 | 115.030 | 2.556 |
| Ricardo Barros (dep-73788) | PR | 19,8 | 19,8 | 43.940 | 2.215 |
| Padovani (dep-220706) | PR | 41,0 | 41,0 | 90.091 | 2.195 |
| Pedro Paulo (dep-122158) | RJ | 45,0 | 45,0 | 96.308 | 2.140 |
| Arnaldo Jardim (dep-141391) | SP | 45,0 | 45,0 | 89.589 | 1.991 |

**Câmara, Outros gastos do mandato: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Marina Silva (dep-220637) | SP | 7,1 | 7,1 | -3.214 | -452 |
| Geovania de Sá (dep-178966) | SC | 38,0 | 38,0 | -4.605 | -121 |
| Fernando Monteiro (dep-92699) | PE | 45,0 | 45,0 | -1.150 | -26 |
| José Guimarães (dep-141470) | CE | 38,5 | 38,5 | 0 | 0 |
| Jadyel Alencar (dep-220697) | PI | 45,0 | 45,0 | 0 | 0 |
| Robério Monteiro (dep-204489) | CE | 31,0 | 31,0 | 0 | 0 |
| Ivoneide Caetano (dep-220696) | BA | 45,0 | 45,0 | 0 | 0 |
| Ivan Valente (dep-73531) | SP | 38,0 | 38,0 | 0 | 0 |
| Ivan Junior (dep-230764) | MA | 3,3 | 3,3 | 0 | 0 |
| Itamar Paim (dep-225846) | PR | 5,9 | 5,9 | 0 | 0 |

**Câmara, Equipe do gabinete: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) | % do limite |
|---|---|---|---|---|---|---|
| Jorge Araújo (dep-235800) | BA | 6,2 | 3,8 | 578.742 | 153.648 | 92,7 |
| Afonso Florence (dep-160508) | BA | 8,3 | 5,0 | 737.284 | 148.238 | 94,1 |
| Sérgio Brito (dep-73808) | BA | 13,0 | 9,7 | 1.431.772 | 147.922 | 98,7 |
| Rosangela Gomes (dep-178945) | RJ | 8,0 | 4,9 | 718.416 | 146.272 | 91,7 |
| Professora Marcivania (dep-160641) | AP | 15,0 | 12,0 | 1.688.296 | 140.691 | 95,2 |
| André Abdon (dep-178831) | AP | 15,0 | 12,0 | 1.679.330 | 139.944 | 94,7 |
| Aline Gurgel (dep-204353) | AP | 9,3 | 6,3 | 877.257 | 139.461 | 90,6 |
| Rafael Fera (dep-233594) | RO | 15,0 | 12,0 | 1.662.962 | 138.209 | 93,5 |
| Fatima Pelaes (dep-74065) | AP | 5,8 | 5,8 | 793.864 | 137.459 | 97,3 |
| Tiago Dimas (dep-143084) | TO | 15,0 | 12,0 | 1.649.494 | 137.089 | 92,8 |

**Câmara, Equipe do gabinete: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) | % do limite |
|---|---|---|---|---|---|---|
| Dra. Mayra Pinheiro (dep-230088) | CE | 4,1 | 3,1 | 0 | 0 | 0,0 |
| Ribeiro Neto (dep-235088) | MA | 4,1 | 4,1 | 0 | 0 | 0,0 |
| Dr. Remy Soares (dep-228616) | MA | 3,9 | 3,9 | 0 | 0 | 0,0 |
| Dr. Gonçalo (dep-212625) | MA | 3,9 | 3,9 | 0 | 0 | 0,0 |
| Loreny (dep-171139) | SP | 3,6 | 3,6 | 0 | 0 | 0,0 |
| Sérgio Turra (dep-235776) | RS | 4,0 | 3,8 | 0 | 0 | 0,0 |
| Dr Fabio Rueda (dep-227401) | AC | 4,0 | 4,0 | 0 | 0 | 0,0 |
| Luciano Galego (dep-227323) | MA | 4,0 | 4,0 | 0 | 0 | 0,0 |
| Lucyana Genésio (dep-229082) | MA | 3,9 | 3,9 | 0 | 0 | 0,0 |
| Wolmer Araújo (dep-182146) | MA | 4,1 | 4,1 | 0 | 0 | 0,0 |

**Senado, Recebeu (sem a ajuda de custo): 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Pedro Chaves (sen-453) | GO | 3,9 | 4,0 | 309.146 | 54.103 |
| José Lacerda (sen-6305) | MT | 3,9 | 4,0 | 306.580 | 53.911 |
| Castellar Neto (sen-5991) | MG | 4,0 | 4,0 | 297.281 | 52.528 |
| Hamilton Mourão (sen-6341) | RS | 45,0 | 45,0 | 2.398.009 | 52.416 |
| Angelo Coronel (sen-5967) | BA | 45,0 | 45,0 | 2.341.276 | 52.028 |
| Jaques Wagner (sen-581) | BA | 45,0 | 45,0 | 2.339.312 | 51.985 |
| Astronauta Marcos Pontes (sen-6009) | SP | 45,0 | 45,0 | 2.376.166 | 51.930 |
| Ireneu Orth (sen-6015) | RS | 3,9 | 3,9 | 289.441 | 51.733 |
| Margareth Buzetti (sen-6304) | MT | 33,5 | 33,7 | 1.741.227 | 51.715 |
| Esperidião Amin (sen-22) | SC | 45,0 | 45,0 | 2.321.512 | 51.589 |

**Senado, Recebeu (sem a ajuda de custo): 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Augusta Brito (sen-6350) | CE | 34,0 | 34,0 | 1.518.337 | 42.285 |
| Alessandro Vieira (sen-5982) | SE | 45,0 | 45,0 | 1.905.023 | 42.334 |
| Dr. Samuel Araújo (sen-6021) | RO | 4,4 | 4,4 | 232.520 | 43.710 |
| Camilo Santana (sen-6336) | CE | 7,2 | 7,0 | 313.665 | 44.809 |
| Rodrigo Cunha (sen-5905) | AL | 22,9 | 23,0 | 1.091.576 | 45.546 |
| Vanderlan Cardoso (sen-5899) | GO | 41,1 | 41,1 | 1.880.509 | 45.723 |
| Professora Dorinha Seabra (sen-5386) | TO | 45,0 | 45,0 | 2.100.869 | 45.813 |
| Mauro Carvalho Junior (sen-6362) | MT | 3,9 | 3,9 | 219.380 | 45.913 |
| Mecias de Jesus (sen-6027) | RR | 37,4 | 37,4 | 1.768.736 | 46.108 |
| Rodrigo Pacheco (sen-5732) | MG | 44,0 | 44,0 | 2.080.216 | 46.224 |

**Senado, Cota parlamentar: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Hermes Klann (sen-6381) | SC | 3,9 | 3,9 | 212.743 | 54.489 |
| Omar Aziz (sen-5525) | AM | 45,0 | 45,0 | 2.145.401 | 47.676 |
| Laércio Oliveira (sen-4811) | SE | 45,0 | 45,0 | 2.139.239 | 47.539 |
| Mecias de Jesus (sen-6027) | RR | 37,4 | 37,4 | 1.763.049 | 47.197 |
| Alessandro Vieira (sen-5982) | SE | 45,0 | 45,0 | 2.088.425 | 46.409 |
| Randolfe Rodrigues (sen-5012) | AP | 45,0 | 45,0 | 2.081.055 | 46.246 |
| Beto Faro (sen-4639) | PA | 45,0 | 45,0 | 2.064.622 | 45.880 |
| Rogério Carvalho (sen-5352) | SE | 45,0 | 45,0 | 2.063.928 | 45.865 |
| Marcio Bittar (sen-285) | AC | 45,0 | 45,0 | 2.003.593 | 44.524 |
| Lucas Barreto (sen-5926) | AP | 45,0 | 45,0 | 1.956.276 | 43.473 |

**Senado, Cota parlamentar: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Jorge Kajuru (sen-5895) | GO | 45,0 | 45,0 | 0 | 0 |
| Cleitinho (sen-6337) | MG | 45,0 | 45,0 | 178.856 | 3.975 |
| Flavio Azevedo (sen-6374) | RN | 3,9 | 3,9 | 25.928 | 6.567 |
| Oriovisto Guimarães (sen-5924) | PR | 45,0 | 45,0 | 371.601 | 8.258 |
| Eduardo Girão (sen-5976) | CE | 42,3 | 42,3 | 477.462 | 11.290 |
| Flávio Bolsonaro (sen-5894) | RJ | 45,0 | 45,0 | 574.965 | 12.777 |
| Vanderlan Cardoso (sen-5899) | GO | 41,1 | 41,1 | 536.862 | 13.063 |
| Camilo Santana (sen-6336) | CE | 7,2 | 7,2 | 99.794 | 13.842 |
| Leila Barros (sen-5979) | DF | 44,1 | 44,1 | 635.793 | 14.418 |
| Wilder Morais (sen-5070) | GO | 45,0 | 45,0 | 665.191 | 14.782 |

**Senado, Outros gastos do mandato: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Nelsinho Trad (sen-5985) | MS | 45,0 | 45,0 | 1.381.283 | 30.695 |
| Irajá (sen-5385) | TO | 45,0 | 45,0 | 1.275.623 | 28.347 |
| Fabiano Contarato (sen-5953) | ES | 45,0 | 45,0 | 1.140.039 | 25.334 |
| Astronauta Marcos Pontes (sen-6009) | SP | 45,0 | 45,0 | 1.103.645 | 24.525 |
| Castellar Neto (sen-5991) | MG | 4,0 | 4,0 | 96.487 | 24.219 |
| Roberta Acioly (sen-6025) | RR | 7,7 | 7,7 | 181.137 | 23.593 |
| Rodrigo Cunha (sen-5905) | AL | 22,9 | 22,9 | 535.298 | 23.339 |
| Esperidião Amin (sen-22) | SC | 45,0 | 45,0 | 1.025.208 | 22.782 |
| Laércio Oliveira (sen-4811) | SE | 45,0 | 45,0 | 1.001.151 | 22.248 |
| Dra. Eudócia (sen-5906) | AL | 22,1 | 22,1 | 483.484 | 21.880 |

**Senado, Outros gastos do mandato: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Jorge Kajuru (sen-5895) | GO | 45,0 | 45,0 | 1.474 | 33 |
| Cleitinho (sen-6337) | MG | 45,0 | 45,0 | 16.201 | 360 |
| Oriovisto Guimarães (sen-5924) | PR | 45,0 | 45,0 | 17.069 | 379 |
| Vanderlan Cardoso (sen-5899) | GO | 41,1 | 41,1 | 19.998 | 487 |
| Pedro Chaves (sen-453) | GO | 3,9 | 3,9 | 2.291 | 582 |
| Jader Barbalho (sen-35) | PA | 45,0 | 45,0 | 53.046 | 1.179 |
| Mauro Carvalho Junior (sen-6362) | MT | 3,9 | 3,9 | 7.025 | 1.784 |
| Wilder Morais (sen-5070) | GO | 45,0 | 45,0 | 80.967 | 1.799 |
| Leila Barros (sen-5979) | DF | 44,1 | 44,1 | 92.788 | 2.104 |
| Renan Filho (sen-5207) | AL | 7,4 | 7,4 | 15.818 | 2.149 |

**Senado, Equipe do gabinete (estimativa, pelos dias no cargo): 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Marcos Rogério (sen-5422) | RO | 40,6 | 40,6 | 27.378.613 | 673.797 |
| Nelsinho Trad (sen-5985) | MS | 45,0 | 45,0 | 26.546.462 | 589.921 |
| Lucas Barreto (sen-5926) | AP | 45,0 | 45,0 | 25.542.598 | 567.613 |
| Marcio Bittar (sen-285) | AC | 45,0 | 45,0 | 25.265.511 | 561.456 |
| Omar Aziz (sen-5525) | AM | 45,0 | 45,0 | 24.756.019 | 550.134 |
| Weverton (sen-5411) | MA | 45,0 | 45,0 | 23.633.435 | 525.187 |
| Angelo Coronel (sen-5967) | BA | 45,0 | 45,0 | 22.996.738 | 511.039 |
| Sérgio Petecão (sen-4560) | AC | 45,0 | 45,0 | 22.701.740 | 504.483 |
| Esperidião Amin (sen-22) | SC | 45,0 | 45,0 | 21.970.142 | 488.225 |
| Veneziano Vital do Rêgo (sen-5748) | PB | 45,0 | 45,0 | 21.558.317 | 479.074 |

**Senado, Equipe do gabinete (estimativa, pelos dias no cargo): 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Dr. Samuel Araújo (sen-6021) | RO | 4,4 | 4,4 | -205 | -47 |
| André Amaral (sen-6366) | PB | 3,9 | 3,9 | 0 | 0 |
| Ireneu Orth (sen-6015) | RS | 3,9 | 3,9 | 0 | 0 |
| Bene Camacho (sen-4979) | MA | 3,1 | 3,1 | 0 | 0 |
| Pedro Chaves (sen-453) | GO | 3,9 | 3,9 | 0 | 0 |
| Bruno Bonetti (sen-6372) | RJ | 3,8 | 3,8 | 0 | 0 |
| Augusta Brito (sen-6350) | CE | 34,0 | 34,0 | 51.578 | 1.519 |
| Rosana Martinelli (sen-6363) | MT | 4,5 | 4,5 | 7.136 | 1.584 |
| Hermes Klann (sen-6381) | SC | 3,9 | 3,9 | 26.585 | 6.809 |
| Margareth Buzetti (sen-6304) | MT | 33,5 | 33,5 | 245.792 | 7.343 |

## O que a conferência achou (09/11) e o que as revisões de 10/11 mudaram

Erros nossos, corrigidos na origem e registrados em `site/dados/correcoes.json`; nenhum mês duplicado nem sinal trocado
por nós.

1. **Pagamentos a suplentes fora do mandato** (correção de 09/11). A página de remuneração da Câmara mostra como salário o
   que é pago a suplentes nos meses fora do mandato; a página não diz a que se refere. O site só tirava valores abaixo de
   40% do subsídio. Agora sai todo mês sem dia em exercício nem de licença e sem cota nem equipe positiva (um estorno não
   conta: Leônidas Cristino, ago/2024), e o mês seguinte à saída fica (traz os acertos: Silvia Waiãpi, Augusto Puppio e
   Lázaro Botelho, que saíram em 30/7/2025, têm em ago/2025 salário de R$ 4,9 a 5,7 mil e "férias, acertos" de R$ 2,3 a
   2,6 mil). Na terceira revisão: nesse mês, o salário da página sai quando é igual ao de um mês que já sai (é o mesmo
   pagamento que se repete: Leônidas Cristino mai/2026, R$ 29.144,46; Pauderney Avelino abr/2026 e nov/2024; Missionário
   José Olimpio nov/2025, R$ 10.597,99); ficam os pagamentos do contracheque detalhado. Ivan Valente mai/2026 (R$ 33.251,18)
   não é igual a nenhum mês que sai e fica. 11 perfis mudaram desde a versão publicada.
2. **Outros gastos do mandato do Senado de quem não estava em exercício** (correção de 10/11). `coleta/senado.py` só lia a
   API, que responde 404 para quem não está em exercício; 25 senadores ficavam com zero (Rodrigo Pacheco sem os correios
   de 2024–2025; Lourdinha Pereira sem R$ 18.504 de 2026; Mecias de Jesus, R$ 773.256). Agora vêm da página de
   transparência de cada senador (o mesmo quadro da API; conferido com Esperidião Amin 2025: os seis valores iguais) e
   ficam em `dados/senado/outros_gastos.csv`. Ano não lido fica marcado como incompleto (`o.inc`); hoje, nenhum.
3. **Histórico da Câmara**: situações no mesmo dia na ordem da API; "CONVOCADO" sem posse depois conta como exercício; e,
   com posse depois da convocação, vale a posse (Priscila Costa: convocada 9/7/2026, posse 6/8/2026).
4. **Equipe do Senado** (estimativa pela lotação atual): no balanço, a estimativa de cada mês conta pelos dias no cargo
   (Renzo Braz, que assumiu em 30/9/2026, tinha R$ 672.397 de setembro; agora R$ 22.413). O titular licenciado para ser
   ministro fica sem a equipe dos meses fora do cargo (Camilo Santana: R$ 11,2 milhões no perfil, R$ 2,7 milhões no
   balanço). A ordem e as comparações do Senado usam o total sem a equipe estimada (`t.ts`, `t.ms`). Marcos Rogério tem a
   maior média da equipe estimada (R$ 673.797 por mês).
5. **Elegibilidade**: só entra nas comparações (`t.ok`) quem tem 3 meses ou mais em cada parte que forma o total (Câmara:
   as quatro; Senado: recebeu, cota e outros). 28 pessoas ficam fora (Itamar Paim, que era o primeiro da Câmara com
   R$ 243.371 por mês, tem 2,9 meses de equipe). Média com menos de 1 mês no divisor não existe (Jarbas Vasconcelos: 1 dia
   em set/2023, R$ 8.664 de acertos).
6. **Limite da cota** pelos dias em exercício, com o valor de cada dia (fev/2026 mudou no dia 20: Soldado Noelio, 11 a
   28/02); nota lançada num mês sem exercício entra no gasto sem criar limite (Gláucia Santiago: 99,0%). 33 deputados
   com 3 meses ou mais passam de 100% (`meta.acima_100`): as passagens ao estado são pagas além da cota (Ato da Mesa nº
   43/2009, art. 2º, § 3º) e aparecem no total; líderes e presidentes de comissão têm um adicional fora do limite.
7. **Recebeu**: mês no cargo sem nenhum pagamento na fonte não entra no divisor (`r.sp`, 96 pessoas): o mês da posse de
   vários suplentes e alguns meses seguidos sem pagamento de algumas deputadas. Os licenciados que ficaram com o salário
   do mandato (54 pessoas) contam os meses com subsídio.
8. **Verba de gabinete da Câmara**: dez/2024 não está na página de nenhum deputado (a tabela de 2024 vai de jan a nov;
   conferido em Pompeo de Mattos) e fica fora da média. O valor mensal disponível subiu de R$ 118.376 (2023) para
   R$ 125.478 (fev/2024), R$ 133.171 (fev/2025) e R$ 165.806 (mar/2026), estimado pela própria página
   (`dados/referencia/teto_verba_gabinete_camara.csv`); o balanço traz a % desse valor (`e.p`).
9. **Senado: 13º negativo na fonte.** A folha oficial traz, todo mês, valor negativo na coluna do 13º de Alessandro
   Vieira, Augusta Brito e Camilo Santana (conferido em dez/2025 e mar/2026). Somado como a fonte publica; ressalva neutra.
10. **Câmara: verba de gabinete R$ 0,00 para 54 deputados**, quase todos suplentes de cerca de 4 meses (conferido na
    página oficial de Dr Fabio Rueda e Capitão Samuel). A mediana da equipe conta só quem teve equipe.
11. **Valores negativos e picos que não são erro**: estornos na cota, devoluções de diárias, acertos; cota de dezembro
    acima de R$ 120 mil (o saldo do ano acumula); recebido alto no mês da posse (ajuda de custo); equipe do Senado perto
    de R$ 1 milhão em junho e dezembro.
12. **Diferenças com as páginas de hoje**: só nos últimos meses (notas que chegaram depois de 04/11), em janeiro de 2023
    (as páginas anuais somam janeiro, da legislatura anterior) e na CEAPS de nov/2025 de Ana Paula Lobato (explicada acima).

### Terceira revisão (10/11/2026)

A revisão refez as 755 pessoas e bateu campo a campo; os problemas eram de regra:

- Média do total em branco no CSV fora das comparações (Itamar Paim, Renzo Braz, Jarbas Vasconcelos) e `t.m`/`t.ms` nulos
  no JSON quando falta a média de alguma parte (Nivaldo Albuquerque).
- Verba de gabinete da Câmara: o mês pesa ao menos o gasto ÷ o valor disponível (mês com 1 dia no cargo e o resto de
  licença: Wilson Santiago jun/2026, R$ 165.580). Nenhum deputado passa de 100% do valor disponível (eram 21). A cota não
  muda: o limite é proporcional aos dias pela regra da Câmara.
- Outros gastos do Senado (valor anual repartido): pesam só a fração no cargo (Carlos Fávaro: 7,95 meses na média, eram
  38,95; Wellington Dias, com 0,5 mês no cargo, fica sem média).
- Nota da cota num mês sem exercício fica no gasto e não conta no divisor (Gláucia Santiago: R$ 41.488 por mês, eram
  R$ 33.205); só a licença da Câmara conta o mês.
- "CONVOCADO" e "SUPLENCIA" sem posse só contam se o intervalo passar de 2 dias ou houver pagamento ou cota (Marcelo Calero,
  Duarte Gonçalves Jr, de fev a jun/2024, Wolmer Araújo).
- Deputados acima de 100% do limite da cota pela % arredondada que a página mostra: 33.
