"""Quanto ganha quem trabalha no Brasil: a distribuição da renda do trabalho, pela PNAD Contínua do IBGE.

É o que permite dizer, ao lado dos salários mínimos, que um político "ganha mais que 99,6% dos brasileiros que
trabalham". Usamos os microdados dos 4 trimestres mais recentes da PNAD Contínua (a pesquisa oficial de emprego e renda
do IBGE), juntos para ter mais gente na ponta de cima:

- quem entra: as pessoas ocupadas (VD4002 = 1) com rendimento do trabalho (VD4019 maior que zero), com o peso de cada
  pessoa na amostra (V1028) dividido por 4, já que são 4 trimestres;
- a renda: o rendimento mensal habitual de todos os trabalhos (VD4019), bruto, antes de impostos e descontos, como o
  salário do político que mostramos;
- a régua: cada renda é dividida pelo salário mínimo do ano do trimestre, o que tira o efeito da inflação entre os
  trimestres e deixa comparar com o político do mesmo jeito que já fazemos (em salários mínimos de cada ano).

Grava dados/referencia/renda_trabalho.json: a parte de quem trabalha que ganha MENOS que x salários mínimos, para uma
lista de valores de x (o site interpola entre eles). Só baixa de novo (uns 900 MB) quando o IBGE publica um trimestre
novo.

Limite conhecido: pesquisas domiciliares captam mal as rendas muito altas (quem ganha muito responde menos e declara
menos). Então a parte de quem ganha mais que um deputado deve ser um pouco maior do que a PNAD mostra, e o percentual
que exibimos, um pouco otimista. Por isso arredondamos para baixo e nunca passamos de 99,9%.
"""
import io
import re
import tempfile
import zipfile
from datetime import datetime

from .config import DADOS
from .padronizar import SALARIO_MINIMO
from .util import _sessao, gravar_json, ler_json, log, verificar_prazo

BASE = "https://ftp.ibge.gov.br/Trabalho_e_Rendimento/Pesquisa_Nacional_por_Amostra_de_Domicilios_continua/Trimestral/Microdados"
FONTE = "https://www.ibge.gov.br/estatisticas/sociais/trabalho/9173-pesquisa-nacional-por-amostra-de-domicilios-continua-trimestral.html?t=microdados"
SAIDA = DADOS / "referencia" / "renda_trabalho.json"
# posições no arquivo de largura fixa (input_PNADC_trimestral.txt, na pasta Documentacao do IBGE)
CAMPOS = {"ano": (0, 4), "tri": (4, 5), "peso": (49, 64), "ocupada": (409, 410), "renda": (443, 451)}
# valores de x (em salários mínimos) em que guardamos a parte de quem ganha menos que x
GRADE = ([i / 4 for i in range(1, 21)] + [i / 2 for i in range(11, 21)] + list(range(11, 31))
         + list(range(32, 62, 2)) + list(range(65, 105, 5)) + [120, 150, 200])


def _trimestres():
    """[(ano, tri, url)] dos arquivos publicados, do mais novo para o mais velho."""
    achados = []
    for ano in range(datetime.now().year, 2023, -1):
        r = _sessao().get(f"{BASE}/{ano}/", timeout=60)
        if r.status_code != 200:
            continue
        for tri, a in re.findall(r'href="PNADC_0(\d)(\d{4})[^"]*\.zip"', r.text):
            achados.append((int(a), int(tri), f"{BASE}/{ano}/" + re.search(rf'href="(PNADC_0{tri}{a}[^"]*\.zip)"', r.text).group(1)))
    return sorted(set(achados), reverse=True)


def _pessoas(url):
    """(salários mínimos, peso) de cada pessoa ocupada com renda do trabalho no trimestre."""
    saida = []
    with tempfile.TemporaryFile() as tmp:
        with _sessao().get(url, stream=True, timeout=900) as r:
            r.raise_for_status()
            for bloco in r.iter_content(1 << 22):
                tmp.write(bloco)
        verificar_prazo()
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as z:
            nome = next(n for n in z.namelist() if n.lower().endswith(".txt"))
            with z.open(nome) as f:
                for bruta in io.TextIOWrapper(f, encoding="latin-1"):
                    c = lambda k: bruta[CAMPOS[k][0]:CAMPOS[k][1]].strip()
                    if c("ocupada") != "1" or not c("renda"):
                        continue
                    renda = float(c("renda"))
                    if renda <= 0:
                        continue
                    saida.append((renda / SALARIO_MINIMO[int(c("ano"))], float(c("peso"))))
    return saida


def executar(forcar=False):
    tris = _trimestres()[:4]
    if len(tris) < 4:
        log("Renda (PNAD): não achei 4 trimestres publicados.")
        return
    usados = [f"{t}º/{a}" for a, t, _ in tris]
    atual = ler_json(SAIDA) if SAIDA.exists() else None
    if atual and atual.get("trimestres") == usados and not forcar:
        log(f"Renda (PNAD): nada novo (já usa {', '.join(usados)}).")
        return
    pessoas = []
    for a, t, url in tris:
        log(f"Renda (PNAD): baixando o {t}º trimestre de {a}...")
        pessoas += _pessoas(url)
    pessoas.sort()
    total = sum(p for _, p in pessoas)
    # parte (%) de quem ganha menos que x, para cada x da grade
    menos, i, acum = [], 0, 0.0
    for x in GRADE:
        while i < len(pessoas) and pessoas[i][0] < x:
            acum += pessoas[i][1]
            i += 1
        menos.append(round(acum / total * 100, 3))

    def quantil(q):
        alvo, s = q * total, 0.0
        for v, p in pessoas:
            s += p
            if s >= alvo:
                return round(v, 2)

    dados = {
        "fonte": "IBGE, PNAD Contínua (microdados trimestrais)",
        "url": FONTE,
        "trimestres": usados,
        "conceito": "pessoas ocupadas com rendimento do trabalho; rendimento mensal habitual de todos os trabalhos (bruto), "
                    "em salários mínimos do ano de cada trimestre",
        "pessoas": round(total / 4),
        "amostra": len(pessoas),
        "amostra_acima_20sm": sum(1 for v, _ in pessoas if v > 20),
        "mediana_sm": quantil(0.5),
        "p90_sm": quantil(0.9),
        "p99_sm": quantil(0.99),
        "p999_sm": quantil(0.999),
        "grade": [[x, m] for x, m in zip(GRADE, menos)],
    }
    gravar_json(SAIDA, dados, compacto=False, indent=1)
    log(f"Renda (PNAD): {dados['pessoas'] / 1e6:.1f} milhões de pessoas; mediana {dados['mediana_sm']} SM, "
        f"1% mais bem pagos acima de {dados['p99_sm']} SM ({SAIDA.relative_to(DADOS.parent)})")
