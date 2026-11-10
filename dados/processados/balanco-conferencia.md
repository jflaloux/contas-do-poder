# Balanço 2023–2026: conferência

Feita em 09/11/2026 sobre a base padronizada de 04/11/2026 (`dados/processados/lancamentos.csv.gz`, rodada do GitHub) e
o `site/dados/balanco.json` gerado por `python3 coletar.py site` (`coleta/balanco.py`). As páginas oficiais foram lidas
em 09/11/2026.

Faixas de meses usadas: Câmara — folha fev/2023 a out/2026, cota fev/2023 a out/2026, verba de gabinete fev/2023 a
jul/2026 (a Câmara está quatro meses atrasada); Senado — folha, CEAPS, outros gastos e equipe (estimativa) de fev/2023
a out/2026.

## (a) Soma do balanço × base

- **Balanço × perfis**: para as 755 pessoas (648 deputados, 107 senadores), recebeu = `per.leg.g`, cota + outros gastos =
  `per.leg.c` e equipe = `per.leg.e` do `dados.json`, sem nenhuma diferença acima de R$ 1. Nenhum perfil de deputado ou
  senador ficou fora do balanço.
- **Balanço × base bruta** (`lancamentos.csv.gz`, sem os ajustes do site): 40 pessoas diferem, R$ 23.324.347 a menos no
  balanço, todas pelos ajustes que o site faz nos perfis:
  - 18 deputados e senadores que foram ministros: R$ 21.632.402 de salário pago pelo Congresso nos meses como ministro,
    que fica na página de ministro (Alexandre Padilha, Wellington Dias, Renan Filho, Paulo Teixeira, Marina Silva,
    Carlos Fávaro, Camilo Santana, Silvio Costa Filho, André Fufuca, Celso Sabino, Juscelino Filho, Paulo Pimenta,
    Gleisi Hoffmann, Flávio Dino, Guilherme Boulos, Daniela do Waguinho, José Guimarães, Luiz Marinho);
  - 22 deputados com pagamentos da Câmara em meses fora do mandato (`site._sem_pagamento_fora_do_mandato`): R$ 1.691.945
    (líquido). 16 deles mudaram nesta conferência (ver o item 1 de "O que a conferência achou" e
    `site/dados/correcoes.json`): Pauderney Avelino, Ivan Valente, Leônidas Cristino, Luiz Carlos Hauly e Josias Gomes
    (R$ 1.172.724) e onze pagamentos pequenos do mês seguinte à saída.
- Totais do balanço: Câmara R$ 4.702.026.295 (base bruta R$ 4.717.538.157); Senado R$ 1.508.919.227 (base bruta
  R$ 1.516.731.718).

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
| 2025 | 520.369,19 | 522.790 (a nossa tem R$ 2.421 a mais: a lista de notas da CEAPS e o total da página diferem; não explicado) |
| 2026 | 374.836,62 | 374.837 |

Folha: jun/2025 = 46.366,19 + 23.183,09 (13º) = 69.549, igual; mar/2026 = 46.366,19, igual. Ela esteve fora do exercício
de 31/7 a 5/10/2026 e a folha mostra o subsídio em ago e set/2026: o balanço divide o recebido por 44,3 meses (42,1 no
cargo + os meses com subsídio).

## (c) Maiores e menores médias por mês

Só quem tem 3 meses ou mais na média do componente. O que olhar está na seção seguinte.

**Câmara, Recebeu (sem a ajuda de custo): 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Lenir de Assis (dep-231911) | PR | 12,9 | 12,9 | 735.828 | 53.407 |
| Carla Dickson (dep-213762) | RN | 22,0 | 22,0 | 1.213.136 | 53.142 |
| Enfermeira Rejane (dep-230765) | RJ | 22,0 | 22,0 | 1.210.343 | 53.015 |
| Pastor Claudio Mariano (dep-230762) | PA | 11,5 | 11,6 | 657.979 | 52.862 |
| André Abdon (dep-178831) | AP | 15,1 | 15,1 | 838.515 | 52.584 |
| Romero Rodrigues (dep-160629) | PB | 41,2 | 41,6 | 2.210.238 | 52.186 |
| Marcos Pereira (dep-204506) | SP | 45,0 | 45,0 | 2.385.556 | 52.139 |
| Marcelo Nilo (dep-204558) | BA | 6,8 | 6,8 | 398.766 | 52.079 |
| Delegado Palumbo (dep-220652) | SP | 45,0 | 45,0 | 2.378.300 | 51.978 |
| Mauro Benevides Filho (dep-204486) | CE | 45,0 | 45,0 | 2.378.176 | 51.975 |

**Câmara, Recebeu (sem a ajuda de custo): 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Marcelo Calero (dep-204433) | RJ | 3,1 | 3,2 | 142.545 | 30.881 |
| Chiquinho Brazão (dep-204476) | RJ | 23,0 | 26,8 | 919.165 | 32.838 |
| Priscila Costa (dep-226075) | CE | 7,8 | 7,8 | 325.831 | 36.224 |
| Nivaldo Albuquerque (dep-194260) | AL | 3,0 | 3,1 | 158.031 | 36.528 |
| Renan Ferreirinha (dep-225386) | RJ | 5,3 | 5,6 | 254.102 | 37.381 |
| Nelinho Freitas (dep-233218) | CE | 4,0 | 4,0 | 197.596 | 38.239 |
| Wolmer Araújo (dep-182146) | MA | 4,1 | 4,1 | 200.368 | 38.821 |
| Lucyana Genésio (dep-229082) | MA | 4,0 | 4,0 | 202.150 | 39.706 |
| Pedro Jr (dep-229112) | TO | 4,0 | 4,0 | 206.913 | 40.924 |
| Duarte Gonçalves Jr (dep-227800) | MG | 4,1 | 4,1 | 211.241 | 41.017 |

**Câmara, Cota parlamentar: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) | % do limite |
|---|---|---|---|---|---|---|
| Vavá (dep-235712) | MG | 4,0 | 4,0 | 221.591 | 55.398 | 116,3 |
| Marcelo Nilo (dep-204558) | BA | 6,8 | 6,8 | 367.008 | 54.238 | 106,4 |
| Zé Adriano (dep-230768) | AC | 22,0 | 22,0 | 1.160.544 | 52.675 | 99,3 |
| Pompeo de Mattos (dep-73486) | RS | 45,0 | 45,0 | 2.330.917 | 51.798 | 108,2 |
| Gabriel Mota (dep-224117) | RR | 43,8 | 43,8 | 2.251.542 | 51.435 | 97,5 |
| Vanderlan Alves (dep-234673) | CE | 6,1 | 6,1 | 312.949 | 51.303 | 98,7 |
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
| João Carlos (dep-235869) | AM | 4,0 | 4,0 | 21.201 | 5.317 | 9,5 |
| Adriana Ventura (dep-204528) | SP | 45,0 | 45,0 | 300.643 | 6.681 | 15,2 |
| Renan Ferreirinha (dep-225386) | RJ | 5,3 | 5,3 | 51.060 | 9.704 | 23,3 |
| Marcelo Calero (dep-204433) | RJ | 3,1 | 3,1 | 33.236 | 10.605 | 25,5 |
| Sandro Alex (dep-160621) | PR | 9,5 | 9,5 | 110.430 | 11.627 | 23,7 |
| Gilson Marques (dep-204365) | SC | 45,0 | 45,0 | 623.257 | 13.850 | 29,6 |

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
| José Priante (dep-74079) | PA | 45,0 | 45,0 | 0 | 0 |
| José Nelto (dep-204391) | GO | 45,0 | 45,0 | 0 | 0 |
| Sargento Gonçalves (dep-220621) | RN | 45,0 | 45,0 | 0 | 0 |
| José Guimarães (dep-141470) | CE | 38,5 | 38,5 | 0 | 0 |
| José Carlos Araujo (dep-74140) | BA | 4,0 | 4,0 | 0 | 0 |
| Sargento Portugal (dep-220618) | RJ | 45,0 | 45,0 | 0 | 0 |
| Josimar Maranhãozinho (dep-204563) | MA | 36,9 | 36,9 | 0 | 0 |

**Câmara, Equipe do gabinete: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Jorge Araújo (dep-235800) | BA | 6,2 | 3,8 | 578.742 | 153.648 |
| Sérgio Brito (dep-73808) | BA | 13,0 | 10,0 | 1.431.772 | 143.151 |
| Rosangela Gomes (dep-178945) | RJ | 8,0 | 5,0 | 718.416 | 142.527 |
| Professora Marcivania (dep-160641) | AP | 15,1 | 12,1 | 1.688.296 | 139.939 |
| Afonso Florence (dep-160508) | BA | 8,3 | 5,3 | 737.284 | 139.209 |
| André Abdon (dep-178831) | AP | 15,1 | 12,1 | 1.679.330 | 139.196 |
| Aline Gurgel (dep-204353) | AP | 9,4 | 6,4 | 877.257 | 138.046 |
| Rafael Fera (dep-233594) | RO | 15,1 | 12,1 | 1.662.962 | 137.839 |
| Fatima Pelaes (dep-74065) | AP | 5,8 | 5,8 | 793.864 | 137.459 |
| Tiago Dimas (dep-143084) | TO | 15,1 | 12,1 | 1.649.494 | 136.723 |

**Câmara, Equipe do gabinete: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Bosco Costa (dep-74052) | SE | 4,0 | 4,0 | 0 | 0 |
| Dr. Gonçalo (dep-212625) | MA | 3,9 | 3,9 | 0 | 0 |
| Dr. Remy Soares (dep-228616) | MA | 3,9 | 3,9 | 0 | 0 |
| Nelinho Freitas (dep-233218) | CE | 4,0 | 4,0 | 0 | 0 |
| Newton Bonin (dep-229939) | PR | 4,1 | 4,1 | 0 | 0 |
| Dra. Mayra Pinheiro (dep-230088) | CE | 4,2 | 4,2 | 0 | 0 |
| Silvio Antonio (dep-227310) | MA | 8,4 | 8,4 | 0 | 0 |
| Duarte Gonçalves Jr (dep-227800) | MG | 4,1 | 4,1 | 0 | 0 |
| Délio Pinheiro (dep-228272) | MG | 4,0 | 4,0 | 0 | 0 |
| Coronel Armando (dep-204376) | SC | 4,0 | 4,0 | 0 | 0 |

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
| Camilo Santana (sen-6336) | CE | 7,2 | 7,2 | 313.665 | 43.305 |
| Dr. Samuel Araújo (sen-6021) | RO | 4,4 | 4,4 | 232.520 | 43.710 |
| Carlos Fávaro (sen-6295) | MT | 8,0 | 8,0 | 347.746 | 43.722 |
| Mauro Carvalho Junior (sen-6362) | MT | 3,9 | 3,9 | 219.380 | 45.136 |
| Rodrigo Cunha (sen-5905) | AL | 22,9 | 23,0 | 1.091.576 | 45.546 |
| Vanderlan Cardoso (sen-5899) | GO | 41,1 | 41,1 | 1.880.509 | 45.723 |
| Professora Dorinha Seabra (sen-5386) | TO | 45,0 | 45,0 | 2.100.869 | 45.813 |
| Mecias de Jesus (sen-6027) | RR | 37,4 | 37,4 | 1.768.736 | 46.108 |

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
| Vanderlan Cardoso (sen-5899) | GO | 41,1 | 42,1 | 536.862 | 12.753 |
| Flávio Bolsonaro (sen-5894) | RJ | 45,0 | 45,0 | 574.965 | 12.777 |
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
| Roberta Acioly (sen-6025) | RR | 7,7 | 7,7 | 181.137 | 23.593 |
| Esperidião Amin (sen-22) | SC | 45,0 | 45,0 | 1.025.208 | 22.782 |
| Laércio Oliveira (sen-4811) | SE | 45,0 | 45,0 | 1.001.151 | 22.248 |
| Dra. Eudócia (sen-5906) | AL | 22,1 | 22,1 | 483.484 | 21.880 |
| Carlos Viana (sen-5990) | MG | 41,0 | 41,0 | 871.611 | 21.234 |
| Humberto Costa (sen-5008) | PE | 45,0 | 45,0 | 947.040 | 21.045 |

**Senado, Outros gastos do mandato: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Janaína Farias (sen-6351) | CE | 3,9 | 3,9 | 0 | 0 |
| Eduardo Girão (sen-5976) | CE | 42,3 | 42,3 | 0 | 0 |
| Flavio Azevedo (sen-6374) | RN | 3,9 | 3,9 | 0 | 0 |
| Hermes Klann (sen-6381) | SC | 3,9 | 3,9 | 0 | 0 |
| Mauro Carvalho Junior (sen-6362) | MT | 3,9 | 3,9 | 0 | 0 |
| Pedro Chaves (sen-453) | GO | 3,9 | 3,9 | 0 | 0 |
| Bruno Bonetti (sen-6372) | RJ | 3,8 | 3,8 | 0 | 0 |
| Margareth Buzetti (sen-6304) | MT | 33,5 | 33,5 | 0 | 0 |
| Castellar Neto (sen-5991) | MG | 4,0 | 4,0 | 0 | 0 |
| José Lacerda (sen-6305) | MT | 3,9 | 3,9 | 0 | 0 |

**Senado, Equipe do gabinete: 10 maiores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Marcos Rogério (sen-5422) | RO | 40,6 | 40,6 | 27.584.529 | 678.865 |
| Nelsinho Trad (sen-5985) | MS | 45,0 | 45,0 | 26.546.462 | 589.921 |
| Lucas Barreto (sen-5926) | AP | 45,0 | 45,0 | 25.542.598 | 567.613 |
| Marcio Bittar (sen-285) | AC | 45,0 | 45,0 | 25.265.511 | 561.456 |
| Omar Aziz (sen-5525) | AM | 45,0 | 45,0 | 24.756.019 | 550.134 |
| Weverton (sen-5411) | MA | 45,0 | 45,0 | 23.633.435 | 525.187 |
| Angelo Coronel (sen-5967) | BA | 45,0 | 45,0 | 22.996.738 | 511.039 |
| Sérgio Petecão (sen-4560) | AC | 45,0 | 45,0 | 22.701.740 | 504.483 |
| Esperidião Amin (sen-22) | SC | 45,0 | 45,0 | 21.970.142 | 488.225 |
| Veneziano Vital do Rêgo (sen-5748) | PB | 45,0 | 45,0 | 21.558.317 | 479.074 |

**Senado, Equipe do gabinete: 10 menores médias por mês**

| Pessoa | UF | Meses no cargo | Meses na média | Total (R$) | Média por mês (R$) |
|---|---|---|---|---|---|
| Dr. Samuel Araújo (sen-6021) | RO | 4,4 | 4,4 | -205 | -47 |
| André Amaral (sen-6366) | PB | 3,9 | 3,9 | 0 | 0 |
| Ireneu Orth (sen-6015) | RS | 3,9 | 3,9 | 0 | 0 |
| Bene Camacho (sen-4979) | MA | 3,1 | 3,1 | 0 | 0 |
| Pedro Chaves (sen-453) | GO | 3,9 | 3,9 | 0 | 0 |
| Bruno Bonetti (sen-6372) | RJ | 3,8 | 3,8 | 0 | 0 |
| Augusta Brito (sen-6350) | CE | 34,0 | 34,0 | 51.717 | 1.523 |
| Rosana Martinelli (sen-6363) | MT | 4,5 | 4,5 | 11.062 | 2.456 |
| Hermes Klann (sen-6381) | SC | 3,9 | 3,9 | 28.162 | 7.213 |
| Beto Martins (sen-6011) | SC | 3,8 | 3,8 | 32.660 | 8.583 |

## O que a conferência achou

Um erro nosso (pagamento fora do mandato), corrigido na origem e registrado em `site/dados/correcoes.json`. Nenhum
mês duplicado nem sinal trocado por nós. O que foi achado, corrigido ou explicado:

1. **Corrigido: pagamentos a suplentes fora do mandato.** A página de remuneração da Câmara mostra como salário o que é
   pago a suplentes nos meses fora do mandato (a página não diz a que se refere o pagamento). O site só tirava
   valores abaixo de 40% do subsídio, e cinco deputados ficavam com esses pagamentos: Pauderney Avelino (R$ 399.362;
   R$ 19.085 a R$ 23.845 por mês antes de ser convocado e depois de sair), Ivan Valente (R$ 258.657; o subsídio
   inteiro depois de deixar a suplência em 1º/4/2026), Leônidas Cristino (R$ 251.342), Luiz Carlos Hauly (R$ 134.598,
   fev a mai/2023, antes da posse) e Josias Gomes (R$ 128.766, jul a out/2026, depois da vacância). Agora sai todo mês
   sem nenhum dia em exercício nem de licença e sem cota nem equipe; no mês seguinte à saída (acertos), vale o corte de
   40% de antes. 16 perfis mudaram (R$ 1.217.363 a menos); a cota e a equipe não mudaram. Testes em
   `coleta/testes_fontes.py`.
2. **Corrigido: leitura do histórico da Câmara.** O código ordenava os eventos por (data, situação), e "SUPLENCIA" e
   "Exercício" no mesmo dia ficavam na ordem errada (Marcos Braz ficava com zero meses no cargo); e o suplente
   convocado às vezes não ganha o evento "Exercício" depois de "CONVOCADO" (Rodrigo Estacho, Pauderney Avelino, Pastor
   Claudio Mariano apareciam fora do cargo meses a fio, com cota e gabinete). Agora vale a ordem da API no mesmo dia e
   "CONVOCADO" conta como exercício (`balanco._intervalos_camara`, também usado por `site._em_exercicio`; o
   `dados.json` não mudou). Testes em `coleta/testes_fontes.py`.
3. **Licenciados com o salário do mandato.** 54 pessoas (50 deputados, 4 senadores) receberam o subsídio em pelo menos um
   mês inteiro em que não estavam em exercício (licença médica ou para ser secretário de Estado, por exemplo: Leandre,
   Rosangela Gomes, Afonso Florence, Sandro Alex e Guilherme Derrite, com mais de 30 meses cada). Pelos meses no cargo, a
   média deles passaria de R$ 200 mil; o balanço divide o recebido pelos meses no cargo ou com o subsídio (peso = a
   parte do subsídio paga no mês).
4. **Senado: 13º negativo na fonte.** A folha do Senado (dados abertos) traz, todo mês, um valor negativo na coluna
   "Gratificação natalina" da folha normal de três senadores: Alessandro Vieira (-4.394,84 por mês em 2025), Augusta Brito
   e Camilo Santana (-4.868,73). Somado, o 13º deles no mandato fica negativo (-69.430, -71.043 e -100.391) e o
   recebido fica abaixo do subsídio (média de R$ 42.334 de Alessandro Vieira). Conferido no arquivo oficial de dez/2025 e
   mar/2026; mostramos como a fonte publica.
5. **Senado: equipe estimada pela lotação atual.** O custo da equipe liga a folha à lotação de hoje (ou a última) de
   cada servidor. Por isso: o titular licenciado para ser ministro fica com a equipe dos meses em que o suplente estava no
   cargo (Camilo Santana: R$ 11,2 milhões em 42 meses de equipe e 7,2 no cargo; a suplente Augusta Brito, 34 meses no
   cargo, tem R$ 51.717); e quem assume agora herda o histórico de quem saiu (Renzo Braz, suplente de Rodrigo Pacheco
   desde 30/9/2026, tem R$ 672 mil de equipe em set/2026; Leany Lemos, R$ 572 mil em out/2026; Rodrigo Pacheco e Leila
   Barros ficam com zero nos últimos meses). Marcos Rogério tem a maior média (R$ 672.793 por mês); pode ser efeito do
   mesmo método. Quem tem menos de 3 meses fica fora das medianas, mas aparece na lista.
6. **Câmara: verba de gabinete R$ 0,00 para 54 deputados**, quase todos suplentes que ficaram cerca de 4 meses
   (conferido na página oficial de Dr Fabio Rueda e Capitão Samuel: "Gasto 0,00, não utilizado 100%"). A mediana da
   equipe por estado conta só quem teve equipe.
7. **Cota acima de 100% do limite: 31 de 637 deputados** (Vavá 116,3% em 4 meses; Pompeo de Mattos 108,2% em 45). É o que
   a Câmara publica: as passagens de ida e volta ao estado são pagas além da cota (Ato da Mesa nº 43/2009, art. 2º, § 3º)
   e aparecem no total da cota; líderes e presidentes de comissão têm um adicional que não está no limite que usamos.
8. **Valores negativos**: cota (67 meses, créditos e estornos de passagens), diárias (34 meses, devoluções), equipe (8
   meses, estornos) e recebido (11 meses, acertos). Marina Silva, Geovania de Sá e Fernando Monteiro ficam com as diárias
   negativas no período. Como a fonte publica.
9. **Picos que não são erro**: cota de dezembro acima de R$ 120 mil (102 casos; o saldo do ano acumula, art. 13);
   recebido acima de 2,6 subsídios no mês da posse (ajuda de custo); equipe do Senado perto de R$ 1 milhão em junho e
   dezembro (13º e férias dos assessores).
10. **Reajustes no período**: o subsídio subiu em abr/2023, fev/2024 e fev/2025, o limite da cota em fev/2026, e a verba
   de gabinete usada por mês cresce no período (Pompeo de Mattos: R$ 118 mil por mês em 2023, R$ 132 mil em 2025). Quem teve mandato só no fim do período tem média maior pelo calendário (os suplentes de
   2025–2026 encabeçam a lista da equipe da Câmara).
11. **Diferenças com as páginas de hoje**: só nos últimos meses (notas da cota que chegaram depois da coleta de 04/11) e
    em janeiro de 2023 (as páginas anuais somam janeiro, que é da legislatura anterior). Ana Paula Lobato, CEAPS 2025:
    R$ 2.421 a mais na nossa soma, sem explicação ainda.
