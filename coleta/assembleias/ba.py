"""Assembleia Legislativa da Bahia (ALBA): deputado estadual por deputado estadual.

Fontes (Transparência da ALBA, sem cadastro):
- Deputados em exercício: https://www.al.ba.gov.br/deputados/deputados-estaduais (nome e número de cada um).
- Verba indenizatória, processo por processo (nº do processo, nº da nota, competência, deputado, categoria, valor),
  na planilha do mês: https://www.al.ba.gov.br/transparencia/verbas-idenizatorias-excel?mes=M&ano=AAAA (o mesmo do
  botão Excel de https://www.al.ba.gov.br/transparencia/verbas-idenizatorias). O fornecedor e o CNPJ só aparecem na
  página de cada processo: ainda não entram aqui.
- Subsídio: Lei 14.532/2023 (R$ 34.774,64). O período começa em fev/2025, quando passou a valer esse valor (não
  achamos o texto da lei com os valores anteriores).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
"""
import html as H
import io
import re
import time
import warnings

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "BA"
COD = comum.CODIGOS_UF[UF]
INICIO = 202502
SITE = "https://www.al.ba.gov.br"
PASTA = DADOS / "assembleias" / "ba"
C = CACHE / "assembleias" / "ba"
CFG = {
    "cod": COD, "n": "Bahia", "uf": UF, "casa": "Assembleia Legislativa da Bahia", "vagas": 63, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 14.532/2023), proporcional aos meses no cargo. A ALBA não publica a folha nominal "
                     "dos deputados, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal (Ato da Presidência 21.527/2003 e alterações).",
    "verba_notas": ["A planilha mensal da ALBA traz o processo, a nota, a categoria e o valor. O fornecedor e o CNPJ ficam só na página "
                    "de cada processo e ainda não entram aqui."],
    "pagina": f"{SITE}/deputados/deputados-estaduais",
    "notas": ["Quem está no cargo hoje: a lista de deputados da ALBA. Desde quando: os meses com verba.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"deputados": f"{SITE}/deputados/deputados-estaduais", "verba": f"{SITE}/transparencia/verbas-idenizatorias",
               "subsidio": "https://portalrh.alba.ba.gov.br/pdf/transparencia/ALBA_ECV_Deputados.pdf"},
}


def _get(url, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, params=params, timeout=180)
            r.raise_for_status()
            dormir(2)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


def _deputados():
    t = _get(f"{SITE}/deputados/deputados-estaduais").text
    saida = {}
    for id_, x in re.findall(r'href="/deputados/deputado-estadual/(\d+)"[^>]*>(.*?)</a>', t, flags=re.S):
        nome = " ".join(H.unescape(re.sub(r"<[^>]+>", " ", x)).split())
        if nome:
            saida[id_] = nome
    return pd.DataFrame(sorted(saida.items()), columns=["id", "nome"])


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m <= h.tm_year * 100 + h.tm_mon]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    C.mkdir(parents=True, exist_ok=True)
    deps = _deputados()
    if len(deps) >= 50:
        gravar_csv(deps.assign(visto_em=time.strftime("%Y-%m-%d")), PASTA / "em_exercicio.csv")
    meses = _meses()
    linhas = []
    for am in meses:
        arq = C / f"verba_{am}.xlsx"
        if not arq.exists() or am >= meses[-3] and time.time() - arq.stat().st_mtime > 3 * 86400:
            arq.write_bytes(_get(f"{SITE}/transparencia/verbas-idenizatorias-excel", {"categoria": "", "deputado": "", "mes": am % 100, "ano": am // 100}).content)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = pd.read_excel(arq, header=None)
        cab = next((i for i in range(min(20, len(d))) if any(str(x).strip().upper().startswith("N° PROCESSO") for x in d.iloc[i])), None)
        if cab is None:
            continue
        col = {str(v).strip().upper(): j for j, v in enumerate(d.iloc[cab]) if str(v) != "nan"}
        for r in d.iloc[cab + 1:].itertuples(index=False):
            dep = str(r[col["DEPUTADO (A)"]]).strip()
            if not dep or dep == "nan":
                continue
            linhas.append({"ano": am // 100, "mes": am % 100, "processo": str(r[col["N° PROCESSO"]]).strip(), "nf": str(r[col["N° NF"]]).strip(),
                           "deputado": " ".join(dep.split()), "categoria": str(r[col["CATEGORIA"]]).strip(), "valor": num(r[col["VALOR (R$)"]])})
    df = pd.DataFrame(linhas)
    gravar_csv(df.sort_values(["ano", "mes", "deputado", "processo"]), PASTA / "verba_processos.csv")
    log(f"  ALBA: {len(deps)} deputados em exercício, {len(df)} processos da verba desde {INICIO % 100:02d}/{INICIO // 100}")


def montar(tipos):
    arq = PASTA / "verba_processos.csv"
    if not arq.exists():
        return None
    v = pd.read_csv(arq, dtype=str).fillna("")
    v["ano"], v["mes"], v["valor"] = v.ano.astype(int), v.mes.astype(int), v.valor.astype(float)
    ex = pd.read_csv(PASTA / "em_exercicio.csv", dtype=str).fillna("") if (PASTA / "em_exercicio.csv").exists() else pd.DataFrame(columns=["id", "nome"])
    ids = {normalizar_nome(n): i for i, n in zip(ex.id, ex.nome)}
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((v.ano * 100 + v.mes).max())
    nomes = sorted(set(v.deputado) | set(ex.nome), key=normalizar_nome)
    ver, mandatos, cods = [], [], {}
    for nome in nomes:
        n = normalizar_nome(nome)
        t = comum.achar(nome, tse) or {}
        codigo = int(ids[n]) if n in ids else comum.codigo_de(nome, t)
        cods[nome] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "",
                    "partido": partidos.get(normalizar_nome(t.get("nome", "")), "") if t else "",
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""),
                    "pagina": f"{SITE}/deputados/deputado-estadual/{ids[n]}" if n in ids else CFG["pagina"]})
        g = v[v.deputado == nome]
        meses_g = list(g.ano * 100 + g.mes)
        atual = n in ids
        if atual:
            meses_g = sorted(set(meses_g) | {ultimo_dado})
        per = comum.periodos(meses_g, ultimo_dado, ultimo)
        if not atual:
            per = [(i, f or f"{max(meses_g) // 100}-{max(meses_g) % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    desp = v.assign(codigo=v.deputado.map(cods), tipo=v.categoria, fornecedor="", cnpj_cpf="")
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]])
