"""Assembleia Legislativa de São Paulo (Alesp): deputado estadual por deputado estadual.

Fontes (dados abertos da Alesp, https://www.al.sp.gov.br/dados-abertos/, sem cadastro):
- Deputados em exercício: https://www.al.sp.gov.br/repositorioDados/deputados/deputados.xml (atualizado todo dia):
  nome parlamentar, partido, matrícula, gabinete.
- Verba de gabinete (auxílio-encargos gerais de gabinete, Resolução 822/2001), por deputado, mês, tipo de despesa e
  fornecedor (CNPJ): https://www.al.sp.gov.br/repositorioDados/deputados/despesas_gabinetes_AAAA.xml. A Alesp soma
  as notas do mesmo fornecedor no mês: não há o número nem a data de cada nota.
- Subsídio: Lei 17.617/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025) e Lei 18.384/2025
  (R$ 34.774,64 em 2026). A folha nominal dos deputados só está publicada desde nov/2025, então o salário vem da lei.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022).
Quem esteve no cargo em cada mês: os deputados em exercício hoje (desde o início do período) e, para quem saiu, os
meses em que a matrícula aparece na verba de gabinete.
"""
import re
import time
import xml.etree.ElementTree as ET

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..prefeituras.comum import feminino
from ..vereadores import comum as vc
from . import comum

UF = "SP"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
BASE = "https://www.al.sp.gov.br/repositorioDados/deputados"
PASTA = DADOS / "assembleias" / "sp"
C = CACHE / "assembleias" / "sp"
CFG = {
    "cod": COD, "n": "São Paulo", "uf": UF, "casa": "Assembleia Legislativa de São Paulo", "vagas": 94, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 17.617/2023 e Lei 18.384/2025), proporcional aos dias no cargo. A Alesp publica a folha "
                     "nominal dos deputados só desde novembro de 2025, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Auxílio-encargos gerais de gabinete (verba de gabinete)",
    "verba_regra": "Reembolso de despesas do gabinete com nota fiscal (Resolução 822/2001 e Ato da Mesa 2/2002).",
    "verba_notas": ["A Alesp publica a verba somada por mês, tipo de despesa e fornecedor (com o CNPJ), sem o número nem a data de cada nota."],
    "credito_foto": "Assembleia Legislativa de São Paulo", "pagina": "https://www.al.sp.gov.br/deputado/lista/",
    "notas": ["Quem estava no cargo: os deputados em exercício hoje, na lista de dados abertos da Alesp, e, para quem saiu, os meses em "
              "que aparece na verba de gabinete."],
    "fontes": {"deputados": f"{BASE}/deputados.xml", "verba": f"{BASE}/despesas_gabinetes.xml",
               "subsidio": "https://www.al.sp.gov.br/repositorio/legislacao/lei/2025/lei-18384-23.12.2025.html"},
}


def _baixar(url, arquivo, dias=1):
    if arquivo.exists() and time.time() - arquivo.stat().st_mtime < dias * 86400:
        return arquivo.read_bytes()
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=300)
            r.raise_for_status()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(r.content)
    dormir(3)
    return r.content


def _registros(xml):
    raiz = ET.fromstring(xml)
    return [{c.tag: (c.text or "").strip() for c in e} for e in raiz]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    deps = pd.DataFrame(_registros(_baixar(f"{BASE}/deputados.xml", C / "deputados.xml")))
    deps = deps[["IdDeputado", "Matricula", "NomeParlamentar", "Partido", "IdUA", "Situacao", "Email"]]
    antigos = pd.read_csv(PASTA / "deputados.csv", dtype=str) if (PASTA / "deputados.csv").exists() else pd.DataFrame(columns=deps.columns)
    hoje = time.strftime("%Y-%m-%d")
    deps = deps.assign(visto_em=hoje)
    # quem saiu continua na tabela (com a última data em que estava na lista), para o nome e o partido
    todos = pd.concat([deps, antigos[~antigos.Matricula.isin(deps.Matricula)]], ignore_index=True)
    gravar_csv(todos.sort_values("Matricula"), PASTA / "deputados.csv")
    linhas = []
    for ano in range(INICIO // 100, int(time.strftime("%Y")) + 1):
        recente = ano >= int(time.strftime("%Y")) - (1 if int(time.strftime("%m")) <= 2 else 0)
        xml = _baixar(f"{BASE}/despesas_gabinetes_{ano}.xml", C / f"despesas_{ano}.xml", dias=3 if recente else 3650)
        for r in _registros(xml):
            linhas.append({"ano": int(r["Ano"]), "mes": int(r["Mes"]), "matricula": r["Matricula"], "deputado": r.get("Deputado", ""),
                           "tipo": r.get("Tipo", ""), "fornecedor": r.get("Fornecedor", ""), "cnpj_cpf": vc.mascarar(r.get("CNPJ", "")),
                           "valor": float(r.get("Valor") or 0)})
    verba = pd.DataFrame(linhas)
    verba = verba[verba.ano * 100 + verba.mes >= INICIO]
    gravar_csv(verba.sort_values(["ano", "mes", "matricula", "tipo", "fornecedor"]), PASTA / "verba_gabinete.csv")
    log(f"  Alesp: {len(deps)} deputados em exercício, {len(verba)} linhas de verba de gabinete desde {INICIO % 100:02d}/{INICIO // 100}")


def _tipo(t):
    return re.sub(r"^[A-Z]\s*-\s*", "", t).strip().capitalize() if t else "Outros"




def montar(tipos):
    arq_d, arq_v = PASTA / "deputados.csv", PASTA / "verba_gabinete.csv"
    if not arq_d.exists():
        return None
    deps = pd.read_csv(arq_d, dtype=str).fillna("")
    verba = pd.read_csv(arq_v, dtype={"matricula": str, "cnpj_cpf": str}) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "matricula"])
    tse = comum.tse_2022(UF)
    ultimo = vc.ultimo_mes_fechado()
    em_exercicio = set(deps[deps.Situacao == "EXE"].Matricula)
    ver, mandatos = [], []
    nomes_verba = verba.groupby("matricula").deputado.agg(lambda s: s.mode().iloc[0] if len(s.mode()) else "").to_dict() if len(verba) else {}
    matriculas = set(deps.Matricula) | set(verba.matricula.astype(str)) if len(verba) else set(deps.Matricula)
    for mat in sorted(matriculas):
        d = deps[deps.Matricula == mat]
        nome = d.NomeParlamentar.iloc[0] if len(d) else vc.titulo(nomes_verba.get(mat, ""))
        if not nome:
            continue
        t = comum.achar(nome, tse) or comum.achar(nomes_verba.get(mat, ""), tse) or {}
        genero = t.get("genero") or ("F" if feminino(re.sub(r"^(Profª|Prof\.?|Dra?\.?)\s+", "", nome)) else "M")
        ver.append({"codigo": int(mat), "nome": nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "",
                    "partido": (d.Partido.iloc[0] if len(d) else "") or t.get("partido", ""), "genero": genero,
                    "eleito": t.get("eleito", ""), "pagina": f"https://www.al.sp.gov.br/deputado/?matricula={mat}"})
        if mat in em_exercicio:
            # na lista de hoje: no cargo desde o primeiro mês com verba no período (ou desde o início)
            vm = verba[verba.matricula.astype(str) == mat] if len(verba) else verba
            de = int((vm.ano * 100 + vm.mes).min()) if len(vm) else INICIO
            de = INICIO if de <= vc.mes_seguinte(INICIO) else de
            mandatos.append({"codigo": int(mat), "inicio": f"{de // 100}-{de % 100:02d}-01", "fim": ""})
        else:
            vm = verba[verba.matricula.astype(str) == mat]
            ms = sorted(set(int(x) for x in vm.ano * 100 + vm.mes))
            # um mês sem verba entre dois com verba é mês no cargo (o deputado só não pediu reembolso)
            ms += [vc.mes_seguinte(a) for a, b in zip(ms, ms[1:]) if vc.mes_seguinte(vc.mes_seguinte(a)) == b]
            for i, f in vc.periodos_de_meses(ms, ultimo, aberto=False):
                mandatos.append({"codigo": int(mat), "inicio": i, "fim": f})
    ver, mandatos = pd.DataFrame(ver), pd.DataFrame(mandatos)
    desp = verba.rename(columns={"matricula": "codigo"}).copy()
    if len(desp):
        desp["codigo"] = desp.codigo.astype(int)
        desp["tipo"] = desp.tipo.map(_tipo)
    cfg = dict(CFG, ultimo_mes=min(ultimo, int((verba.ano * 100 + verba.mes).max())) if len(verba) else ultimo)
    return vc.montar(cfg, tipos, ver, mandatos, despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]] if len(desp) else None)
