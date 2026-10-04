"""Assembleia Legislativa do Paraná (Alep): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alep, https://transparencia.assembleia.pr.leg.br):
- Folha: a página "Parlamentares" (/pessoal/parlamentares) e o que ela usa: a lista do mês (/api/remuneracao, tipo
  "deputado estadual") e os valores de cada deputado (/api/remuneracao/<matrícula>): subsídio, 1/3 de férias, vantagens
  transitórias, abono, benefícios, RRA e o redutor constitucional. Descontos obrigatórios e o valor depois deles (líquido)
  não são guardados.
- Equipe: a página "Comissionados" (/pessoal/comissionados), exportação do mês em planilha: quantos servidores
  comissionados estão lotados em cada gabinete ("GAB. DEP. ...") e em que cargos. A lista traz o valor de cada um
  depois dos descontos obrigatórios; o total bruto só sai pessoa por pessoa, e o custo da equipe não entra.
- Verba de ressarcimento: a "Consulta de despesa" da Alep (/receitas-e-despesas/despesas/consultas, dados do SIAFIC
  do Estado), exportação dos pagamentos do mês (grupo 3, outras despesas correntes): as ordens bancárias de
  ressarcimento a cada deputado ("Ressarc. Dep. ...", "Ressa.Deput. ..."), com a natureza da despesa. É o pagamento ao
  deputado, sem fornecedor nem nota: as notas estão na consulta do ressarcimento, que tem reCAPTCHA e não é lida.
- Nome parlamentar, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os meses com o gabinete na lista de comissionados (54 por mês). O titular licenciado continua na folha
com o subsídio, mas o gabinete dele fica sem comissionados enquanto o suplente exerce.
"""
import difflib
import io
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "PR"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://transparencia.assembleia.pr.leg.br"
PASTA = DADOS / "assembleias" / "pr"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Paraná", "uf": UF, "casa": "Assembleia Legislativa do Paraná", "vagas": 54, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 32196.01], [202502, 33448.48], [202602, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da Alep (subsídio, 1/3 de férias, vantagens transitórias, abono, benefícios e RRA, menos o "
                     "redutor constitucional), sem os descontos obrigatórios. Subsídio pela Lei 21.348/2022. Quando o Total Bruto "
                     "da folha é menor que a soma das parcelas (a página não diz o motivo), vale o Total Bruto. A página da folha "
                     "dos deputados não mostra 13º salário."),
    "verba_nome": "Verba de ressarcimento",
    "verba_regra": "Ressarcimento das despesas da atividade parlamentar (Resolução 6/2025), pago ao deputado.",
    "verba_notas": ["A verba entra pelos pagamentos de ressarcimento a cada deputado na consulta de despesas da Alep (SIAFIC), "
                    "por natureza da despesa e no mês do pagamento, sem fornecedor nem nota. O detalhe nota a nota fica na "
                    "consulta do ressarcimento, que pede reCAPTCHA e não é lida.",
                    "O mês é o do pagamento: um pagamento pode juntar despesas de mais de um mês.",
                    "Entram só os pagamentos ao próprio deputado: os de ressarcimento a servidores e a empresas ficam de fora."],
    "equipe_nota": ("Equipe: servidores comissionados lotados no gabinete do deputado, pela lista de comissionados da Alep no "
                    "mês. A lista traz o valor de cada um depois dos descontos obrigatórios; o custo da equipe não entra."),
    "pagina": "https://www.assembleia.pr.leg.br/",
    "notas": ["Quem está no cargo: os meses com o gabinete na lista de comissionados da Alep (54 gabinetes por mês). O titular "
              "licenciado continua na folha com o subsídio (o salário aparece), mas o gabinete dele fica sem comissionados "
              "enquanto o suplente exerce.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": f"{SITE}/pessoal/parlamentares", "equipe": f"{SITE}/pessoal/comissionados",
               "verba": f"{SITE}/receitas-e-despesas/despesas/consultas"},
}
# rubricas da folha (o número entre parênteses é o da legenda da página); 13 e 14 (descontos e líquido) não são lidos
RUBRICAS = {1: "fixas", 2: "pessoais", 3: "comissao", 4: "policial", 5: "pensao", 6: "subsidio", 7: "ferias", 8: "transitorias",
            9: "abono", 10: "beneficios", 11: "bruto", 12: "redutor", 15: "rra"}
NATUREZAS = {"339014": "Diárias", "339030": "Material de consumo", "339033": "Passagens e locomoção", "339036": "Serviços de pessoa física",
             "339039": "Serviços de empresas", "339040": "Serviços de tecnologia da informação", "339093": "Indenizações e restituições",
             "339015": "Diárias", "339092": "Despesas de exercícios anteriores"}


class _Portal:
    """Sessão no portal (cookie e o token CSRF que a página entrega a qualquer visitante)."""
    def __init__(self, pagina="/pessoal/parlamentares"):
        t = self.pedir("GET", pagina).text
        self.csrf = re.search(r'name="csrf-token" content="([^"]+)"', t).group(1)

    def pedir(self, metodo, caminho, **kw):
        verificar_prazo()
        for tentativa in range(3):
            try:
                r = _sessao().request(metodo, SITE + caminho, timeout=150, **kw)
                r.raise_for_status()
                dormir(1)
                return r
            except TempoEsgotado:
                raise
            except Exception:
                if tentativa == 2:
                    raise
                dormir(15)

    def json(self, metodo, caminho, **kw):
        h = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json", "X-CSRF-TOKEN": self.csrf, "Referer": SITE + "/pessoal/parlamentares"}
        return self.pedir(metodo, caminho, headers=h, **kw).json()


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _valor(t):
    return num(str(t).replace("R$", "").strip()) if str(t).strip() else 0.0


def _folha_mes(p, am):
    """Deputados na lista da folha do mês, com os valores de cada um."""
    linhas, pagina = [], 1
    while True:
        d = p.json("GET", "/api/remuneracao", params={"t": "deputado estadual", "mes": am % 100, "ano": am // 100, "page": pagina, "search": "", "searchType": "nome"})
        lista = d.get("remuneracoes") or []
        if lista and isinstance(lista[0], list):
            lista = [dict(zip([h.lower() for h in d["header"]], x)) for x in lista]
        linhas += lista
        if pagina >= int(d.get("last_page") or 1):
            break
        pagina += 1
    def valores(x):
        det = _portal().json("POST", f"/api/remuneracao/{x['matricula']}", data={"t": "deputado estadual", "mes": am % 100, "ano": am // 100, "id": x["id"]})
        lot = (x.get("lotacao") or "").strip()
        reg = {"ano": am // 100, "mes": am % 100, "id": x["id"], "matricula": x["matricula"], "nome": x["nome"], "lotacao": "" if lot.strip(". ") == "" else lot,
               "nomeacao": x.get("data_nomeacao") or "", "exoneracao": x.get("data_exoneracao") or ""}
        for bloco in ("valores", "valores_eventuais"):
            rot, val = (det.get(bloco) or [[], []])[:2]
            for r, v in zip(rot, val):
                n = re.search(r"\((\d+)\)\s*$", r)
                if n and int(n.group(1)) in RUBRICAS:
                    reg[RUBRICAS[int(n.group(1))]] = _valor(v)
        return reg
    deputados = [x for x in linhas if "DEPUTAD" in normalizar_nome(x.get("cargo") or x.get("vinculo") or "")]
    with ThreadPoolExecutor(SIMULTANEOS) as ex:
        return list(ex.map(valores, deputados))


_local = threading.local()


def _portal():
    """Uma sessão do portal por linha de execução (cada uma com o seu cookie e o seu token CSRF)."""
    if not hasattr(_local, "p"):
        _local.p = _Portal()
    return _local.p


def _equipe_mes(p, am):
    """Comissionados lotados em gabinete de deputado no mês: [(lotação, cargo, pessoas)]."""
    r = p.pedir("GET", "/pessoal/export-remuneracao", params={"ano": am // 100, "mes": am % 100, "export": "excel", "t": "comissionado"})
    df = pd.read_excel(io.BytesIO(r.content), dtype=str).fillna("")
    df.columns = [normalizar_nome(c) for c in df.columns]
    df = df[df["LOTACAO"].str.upper().str.startswith("GAB. DEP")]
    # quem foi exonerado no mês não conta (em fev/2025 a lista traz os 821 exonerados e os 791 nomeados de novo)
    fim = pd.Timestamp(am // 100, am % 100, 1) + pd.offsets.MonthEnd(0)
    exo = pd.to_datetime(df["DATA EXONERACAO"], format="%d/%m/%Y", errors="coerce")
    df = df[exo.isna() | (exo > fim)].drop_duplicates(["MATRICULA"], keep="last")
    g = df.groupby(["LOTACAO", "CARGO"]).size().reset_index(name="pessoas")
    return [{"ano": am // 100, "mes": am % 100, "lotacao": " ".join(l.split()), "cargo": c.strip(), "pessoas": int(n)} for l, c, n in g.itertuples(index=False)]


_RESSARC = re.compile(r"^\W*ressa(rc|\.|\s+dep)|ressarcimento\s+(do\s+|da\s+)?deputad", re.I)
_DIARIAS = re.compile(r"^\W*ressarcimento\s+(de\s+)?despesas\s*\(", re.I)  # diárias de servidores, não é a verba do deputado


def _casar_credor(credor, civis):
    """Código do deputado pelo nome do credor (nome civil, às vezes abreviado ou com outra grafia), ou None."""
    n = normalizar_nome(credor)
    if n in civis:
        return civis[n]
    compat = {c for k, c in civis.items() if vc.compativel(n, k) or vc.compativel(k, n)}
    if len(compat) == 1:
        return compat.pop()
    mesmos = [k for k in civis if k.split()[:1] == n.split()[:1]]
    perto = difflib.get_close_matches(n, mesmos, n=1, cutoff=0.7)
    return civis[perto[0]] if perto else None


def _sem_cpf(texto):
    """O objeto do pagamento às vezes traz o CPF do deputado ("Ressarc. Dep. X, 00595-74.2025 0166369...."): sai."""
    return " ".join(re.sub(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)", " ", str(texto)).split())


def _verba_mes(p, am):
    """Pagamentos de ressarcimento a deputados no mês (exportação da consulta de despesas, grupo 3)."""
    r = p.pedir("GET", "/siafic/despesas/download", params={"tipo": "pagamentos", "ano": am // 100, "escopo": "mes", "mes": am % 100, "grupo_natureza": "3"},
                headers={"X-CSRF-TOKEN": p.csrf, "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    df = pd.read_excel(io.BytesIO(r.content), dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    df = df[df["Objeto"].map(lambda o: bool(_RESSARC.search(o.strip())) and not _DIARIAS.search(o.strip()))]
    # só os pagamentos ao próprio deputado (os outros credores são servidores, com diárias, ou empresas)
    arq_f = PASTA / "folha_deputados.csv"
    if arq_f.exists():
        civis = {normalizar_nome(n): n for n in set(pd.read_csv(arq_f, dtype=str).nome)}
        df = df[df["Credor"].map(lambda c: _casar_credor(c, civis) is not None)]
    return [{"ano": am // 100, "mes": am % 100, "natureza": x["Natureza Despesa"].strip(), "empenho": x["Nota de Empenho"].strip(),
             "ordem_bancaria": x["Ordem Bancária"].strip(), "credor": " ".join(x["Credor"].split()), "objeto": _sem_cpf(x["Objeto"])[:200],
             "valor": round(float(str(x["Despesa Paga"]).replace(",", ".") or 0), 2)} for _, x in df.iterrows()]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:
        p = _portal()
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"  Alep: o portal não abriu ({type(e).__name__}); fica o que já estava gravado")
        return
    meses = _meses()
    velho = lambda arq: not arq.exists() or time.time() - arq.stat().st_mtime > 86400
    arqs = {"folha": PASTA / "folha_deputados.csv", "equipe": PASTA / "equipe_gabinetes.csv", "verba": PASTA / "ressarcimento_pagamentos.csv"}
    funcs = {"folha": _folha_mes, "equipe": _equipe_mes, "verba": _verba_mes}
    for nome in ("folha", "verba", "equipe"):
        arq = arqs[nome]
        df = pd.read_csv(arq, dtype=str) if arq.exists() else pd.DataFrame(columns=["ano", "mes"])
        feitos = set(zip(df.ano.astype(int), df.mes.astype(int))) if len(df) else set()
        rev = velho(arq)
        if nome == "verba" and (PASTA / "ressarcimento_meses.csv").exists():  # meses lidos sem nenhum pagamento também contam
            lidos = pd.read_csv(PASTA / "ressarcimento_meses.csv")
            feitos |= set(zip(lidos.ano, lidos.mes))
        pedir = [am for am in meses if (am // 100, am % 100) not in feitos or (am >= meses[-2] and rev)]
        feitos_agora = 0
        try:
            for am in pedir:
                novos = funcs[nome](p, am)
                if nome != "verba" and not novos:
                    continue  # mês ainda sem dados publicados
                df = pd.concat([df[~((df.ano.astype(int) == am // 100) & (df.mes.astype(int) == am % 100))], pd.DataFrame(novos, dtype=str)])
                if not gravar_csv(df.sort_values([c for c in ("ano", "mes", "nome", "lotacao", "credor", "cargo") if c in df.columns]), arq):
                    break  # recusado por perda de cobertura (util.gravar_com): fica o que estava, e o mês é lido de novo
                if nome == "verba":
                    lidos = pd.read_csv(PASTA / "ressarcimento_meses.csv") if (PASTA / "ressarcimento_meses.csv").exists() else pd.DataFrame(columns=["ano", "mes"])
                    lidos = pd.concat([lidos, pd.DataFrame([{"ano": am // 100, "mes": am % 100}])]).drop_duplicates()
                    gravar_csv(lidos.sort_values(["ano", "mes"]), PASTA / "ressarcimento_meses.csv")
                feitos_agora += 1
        finally:
            log(f"  Alep: {nome}, {feitos_agora} de {len(pedir)} meses lidos agora")


def _tipo(natureza):
    return NATUREZAS.get(str(natureza).strip(), f"Natureza {natureza}")


def _sem_titulo(lotacao):
    return re.sub(r"^GAB(?:INETE)?\.?\s*(?:DA\s+|DO\s+)?DEP(?:UTAD[OA])?\.?\s*", "", str(lotacao), flags=re.I).strip()


def montar(tipos):
    arq_f = PASTA / "folha_deputados.csv"
    if not arq_f.exists():
        return None
    fol = pd.read_csv(arq_f, dtype={"matricula": str}).fillna({"lotacao": ""})
    for c in RUBRICAS.values():
        fol[c] = pd.to_numeric(fol[c], errors="coerce").fillna(0.0) if c in fol else 0.0
    # a mesma folha listada duas vezes no mês (mesmos valores) conta uma vez; folhas diferentes (a complementar) somam
    fol = fol.drop_duplicates(["ano", "mes", "matricula"] + list(RUBRICAS.values()))
    eq = pd.read_csv(PASTA / "equipe_gabinetes.csv") if (PASTA / "equipe_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    vb = pd.read_csv(PASTA / "ressarcimento_pagamentos.csv", dtype={"natureza": str}).fillna("") if (PASTA / "ressarcimento_pagamentos.csv").exists() \
        else pd.DataFrame(columns=["ano", "mes", "natureza", "credor", "objeto", "valor"])
    vb = vb[~vb.objeto.astype(str).map(lambda o: bool(_DIARIAS.search(o)))]
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    fol["am"] = fol.ano * 100 + fol.mes
    fol["lotacao"] = fol.lotacao.astype(str).map(lambda l: "" if l.strip(". ") in ("", "nan") else " ".join(l.split()))
    ultimo_dado = int(fol.am.max())
    ver, mandatos, cod_mat, cod_lot, civis, parlam, meses_folha = [], [], {}, {}, {}, {}, {}
    for mat, g in fol.sort_values("am").groupby("matricula"):
        civil = g.nome.iloc[-1]
        lot = next((l for l in reversed(list(g.lotacao)) if l.upper().startswith("GAB")), "")
        t = por_civil.get(normalizar_nome(civil)) or (comum.achar(_sem_titulo(lot), tse) if lot else None) or comum.achar(civil, tse) or {}
        codigo = comum.codigo_de(civil, t)
        cod_mat[mat] = codigo
        for l in set(g.lotacao):
            if l.upper().startswith("GAB"):
                cod_lot[l] = codigo
        civis[normalizar_nome(civil)] = codigo
        nome = vc.titulo(t.get("urna") or _sem_titulo(lot) or civil)
        for n in {t.get("urna"), _sem_titulo(lot)} - {None, ""}:
            parlam[normalizar_nome(n)] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome") or civil),
                    "partido": partidos.get(normalizar_nome(t.get("nome") or civil), ""),
                    "genero": t.get("genero") or ("F" if feminino(civil) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_folha[codigo] = set(g[g.subsidio > 0].am)  # quem saiu aparece no mês seguinte com a folha zerada
    # no cargo: os meses com o gabinete na lista de comissionados (54 por mês, o número de vagas). O titular licenciado
    # (secretário de Estado, por exemplo) continua na folha com o subsídio, mas o gabinete dele fica sem comissionados
    # enquanto o suplente exerce. Sem gabinete na lista nenhuma vez: os meses com subsídio na folha.
    meses_gab = {}
    if len(eq):
        com_gente = eq[pd.to_numeric(eq.pessoas, errors="coerce").fillna(0) > 0]
        for l, g in com_gente.groupby("lotacao"):
            l = " ".join(str(l).split())
            c = cod_lot.get(l) or parlam.get(normalizar_nome(_sem_titulo(l)))
            if c is None:
                t = comum.achar(_sem_titulo(l), tse)
                c = next((cod for cod in meses_folha if t and cod == comum.codigo_de("", t)), None)
            if c is None:
                log(f"  Alep: gabinete sem deputado na folha ({l})")
                continue
            meses_gab.setdefault(c, set()).update(set(g.ano * 100 + g.mes))
    ult_eq = int((eq.ano * 100 + eq.mes).max()) if len(eq) else 0
    for codigo, mf in meses_folha.items():
        meses_p = sorted(m for m in (meses_gab[codigo] | {x for x in mf if x > ult_eq}) if m <= ultimo_dado) if codigo in meses_gab else sorted(mf)
        if not meses_p:
            continue
        per = comum.periodos(meses_p, ultimo_dado, ultimo, folga=1)
        fim = max(meses_p)
        if fim < ultimo_dado:
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    ganha = []
    for r in fol.itertuples():
        c = cod_mat[r.matricula]
        outros = r.ferias + r.transitorias + r.abono + r.rra + r.fixas + r.pessoais + r.comissao + r.policial + r.pensao
        # o Total Bruto às vezes é menor que a soma das parcelas (em 2026, sem motivo na página): vale o Total Bruto
        falta = min(r.subsidio, max(0.0, r.subsidio + r.beneficios + outros - r.rra - r.bruto)) if r.bruto > 0 else 0.0
        for cat, v in (("salario", r.subsidio - r.redutor - falta), ("auxilios", r.beneficios), ("outros_rendimentos", outros)):
            if abs(v) >= 0.005:
                ganha.append({"ano": r.ano, "mes": r.mes, "codigo": c, "categoria": cat, "valor": round(v, 2)})

    # verba: só os pagamentos ao próprio deputado (o credor é ele)
    cred = {c: _casar_credor(c, civis) for c in set(vb.credor)}
    vb = vb.assign(codigo=vb.credor.map(cred))
    sem = vb[vb.codigo.isna()]
    if len(sem):
        log(f"  Alep: {len(sem)} pagamentos de ressarcimento sem deputado ({', '.join(sorted(set(sem.credor))[:5])})")
    d = vb[vb.codigo.notna()]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.codigo.astype(int), "tipo": d.natureza.map(_tipo), "fornecedor": "",
                         "cnpj_cpf": "", "valor": d.valor.astype(float)})
    e = eq.assign(codigo=eq.lotacao.map(lambda l: cod_lot.get(" ".join(str(l).split())))).dropna(subset=["codigo"])
    equipe = e.groupby(["ano", "mes", "codigo"]).pessoas.sum().reset_index().assign(custo="") if len(e) else None
    cargos, equipe_em = None, ""
    if len(e):
        ult = int((e.ano * 100 + e.mes).max())
        ue = e[e.ano * 100 + e.mes == ult]
        cargos = ue.groupby(["codigo", "cargo"]).pessoas.sum().reset_index().assign(cargo=lambda x: x.cargo.map(lambda c: c.capitalize()))
        equipe_em = f"{ult % 100:02d}/{ult // 100}"
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), equipe_em=equipe_em)
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]), despesas=desp, equipe=equipe, cargos=cargos)
