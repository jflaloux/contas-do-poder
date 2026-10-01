"""Assembleia Legislativa da Paraíba (ALPB): deputado estadual por deputado estadual.

Fonte: Portal da Transparência da ALPB, "Remunerações" (Recursos Humanos), uma planilha ODS por mês para os eletivos
(os deputados): https://www.al.pb.leg.br/transparencia/recursos-humanos/remuneracoes?mes=MM&ano=AAAA (link
"Eletivos"). A planilha traz, por deputado, o subsídio ("do cargo") e a verba indenizatória paga na folha (VIAP),
além dos descontos (imposto, previdência), que não são guardados.
- A VIAP (Verba Indenizatória de Apoio Parlamentar) também sai nota por nota, um arquivo por deputado e mês, em
  https://www.al.pb.leg.br/transparencia/deputados/viap-v2; aqui entra só o total do mês, da folha.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem esteve no cargo em cada mês: quem está na planilha dos eletivos do mês.
"""
import io
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "PB"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
PAGINA = "https://www.al.pb.leg.br/transparencia/recursos-humanos/remuneracoes"
PASTA = DADOS / "assembleias" / "pb"
C = CACHE / "assembleias" / "pb"
CFG = {
    "cod": COD, "n": "Paraíba", "uf": UF, "casa": "Assembleia Legislativa da Paraíba", "vagas": 36, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]], "subsidio_folha": True,
    "salario_nota": ("Subsídio pago na folha da ALPB (\"remuneração do cargo eletivo\"), antes do imposto e da previdência. O valor é o "
                     "da Lei 12.550/2022 (R$ 34.774,64 desde fev/2025)."),
    "verba_nome": "Verba Indenizatória de Apoio Parlamentar (VIAP)",
    "verba_regra": "Reembolso de despesas do mandato, pago na folha (crédito de até R$ 50 mil por mês).",
    "verba_notas": ["Entra o total da VIAP paga na folha do mês. A ALPB publica as notas de cada mês num arquivo por deputado, que ainda "
                    "não entram aqui (sem os fornecedores)."],
    "pagina": "https://www.al.pb.leg.br/deputados",
    "notas": ["Quem estava no cargo em cada mês: quem está na planilha dos eletivos da folha do mês.",
              "A ALPB não publicou a planilha de julho de 2025: nesse mês vale o subsídio da lei, e a VIAP fica sem valor.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": PAGINA, "verba": "https://www.al.pb.leg.br/transparencia/deputados/viap-v2",
               "subsidio": "https://sapl3.al.pb.leg.br/media/sapl/public/normajuridica/2022/15969/15969_texto_integral.pdf"},
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


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _planilha(am):
    arq = C / f"{am}-ELETIVOS.ods"
    if arq.exists():
        return arq.read_bytes()
    t = _get(PAGINA, {"mes": f"{am % 100:02d}", "ano": am // 100}).text
    m = re.search(r"""href=['"]([^'"]+%d-ELETIVOS[^'"]*\.ods)['"]""" % am, t)
    if not m:
        return None
    b = _get(m.group(1)).content
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(b)
    return b


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    linhas = []
    for am in _meses():
        b = _planilha(am)
        if not b:
            log(f"  ALPB: {am % 100:02d}/{am // 100} sem a planilha dos eletivos")
            continue
        d = pd.read_excel(io.BytesIO(b), engine="odf", header=None).fillna("")
        for r in d.itertuples(index=False):
            mat = str(r[1]).strip()
            if not re.fullmatch(r"\d+(\.0)?", mat):
                continue
            linhas.append({"ano": am // 100, "mes": am % 100, "matricula": mat.replace(".0", ""), "nome": str(r[2]).strip(), "lotacao": str(r[4]).strip(),
                           "cargo": str(r[5]).strip(), "subsidio": num(r[6]), "indenizatoria": num(r[7])})
    df = pd.DataFrame(linhas)
    df.sort_values(["ano", "mes", "nome"]).to_csv(PASTA / "folha_eletivos.csv", index=False)
    log(f"  ALPB: {len(df)} linhas da folha dos eletivos, {df.matricula.nunique()} deputados desde {INICIO % 100:02d}/{INICIO // 100}")


def _parlamentar(lotacao):
    """'GAB DEP ADRIANO GALDINO' -> 'Adriano Galdino' (o nome do gabinete é o nome parlamentar)."""
    n = re.sub(r"^GAB(INETE)?\.?\s*(DO\s+|DA\s+)?DEP(UTAD[OA])?\.?\s*", "", lotacao.strip(), flags=re.I)
    return vc.titulo(n) if n and n.upper() != lotacao.strip().upper() else ""


def montar(tipos):
    arq = PASTA / "folha_eletivos.csv"
    if not arq.exists():
        return None
    f = pd.read_csv(arq, dtype={"matricula": str}).fillna("")
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(v["nome"]): v for v in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((f.ano * 100 + f.mes).max())
    com_planilha = set(f.ano * 100 + f.mes)
    meses_sem = {am for am in _meses() if am < ultimo_dado and am not in com_planilha}

    def subsidio_lei(am):
        return [v for de, v in CFG["subsidio"] if am >= de][-1]

    ver, mandatos, ganha, desp = [], [], [], []
    for mat, g in f.groupby("matricula"):
        civil = g.nome.iloc[-1]
        t = comum.achar(civil, por_civil) or {}
        nome = vc.titulo(t["urna"]) if t.get("urna") else (_parlamentar(g.lotacao.iloc[-1]) or vc.titulo(civil))
        ver.append({"codigo": int(mat), "nome": nome, "nome_civil": vc.titulo(t.get("nome") or civil), "partido": partidos.get(normalizar_nome(civil), ""),
                    "genero": t.get("genero") or ("F" if feminino(civil) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_g = set(g.ano * 100 + g.mes)
        for i, fim in comum.periodos(list(meses_g), ultimo_dado, ultimo, folga=1):
            mandatos.append({"codigo": int(mat), "inicio": i, "fim": fim})
        for am in sorted(meses_sem):  # mês sem planilha entre dois meses com o deputado: vale o subsídio da lei
            if vc.menos_meses(am, 1) in meses_g and vc.mes_seguinte(am) in meses_g:
                ganha.append({"ano": am // 100, "mes": am % 100, "codigo": int(mat), "categoria": "salario", "valor": subsidio_lei(am)})
        for r in g.itertuples():
            ganha.append({"ano": r.ano, "mes": r.mes, "codigo": int(mat), "categoria": "salario", "valor": float(r.subsidio)})
            if r.indenizatoria:
                desp.append({"ano": r.ano, "mes": r.mes, "codigo": int(mat), "tipo": "Verba indenizatória (VIAP)", "fornecedor": "", "cnpj_cpf": "",
                             "valor": float(r.indenizatoria)})
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=pd.DataFrame(ganha), despesas=pd.DataFrame(desp) if desp else None)
