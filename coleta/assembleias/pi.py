"""Assembleia Legislativa do Piauí (Alepi): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alepi, https://transparencia.al.pi.leg.br; consultas em ScriptCase, que guardam a
pesquisa na sessão):
- Verba indenizatória: a consulta /grid_transp_publico_gecop/ (todas as notas desde 2012, da competência mais recente
  para a mais antiga): parlamentar (nome civil, cortado em 30 letras), competência, subcota e valor de cada nota, e o
  nome do arquivo do comprovante (que traz a matrícula do deputado). O fornecedor só está no PDF de cada nota, que não
  é lido.
- Folha: a consulta /grid_transp_publico_remuneracao/ ("Remuneração do Servidor"), pesquisada pelo mês e pelo nome de
  cada deputado: os rendimentos de quem tem o regime PARLAMENTARES (subsídio, gratificação, férias e 13º...).
  Previdência e imposto de renda não são guardados (as deduções pessoais a Alepi não publica).
- Nome parlamentar, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os meses com notas da verba (o licenciado continua na folha como parlamentar, sem verba) e, depois do
último mês com a verba publicada, os meses na folha; para quem não tem verba nenhuma, os meses na folha.
"""
import html as H
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

UF = "PI"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://transparencia.al.pi.leg.br"
VERBA = SITE + "/grid_transp_publico_gecop/"
FOLHA = SITE + "/grid_transp_publico_remuneracao/"
PASTA = DADOS / "assembleias" / "pi"
POR_PAGINA = 500
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Piauí", "uf": UF, "casa": "Assembleia Legislativa do Piauí", "vagas": 30, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da Alepi (subsídio, gratificação, férias e 13º), sem previdência e imposto de renda. "
                     "Nos meses no cargo sem a folha do deputado, vale o subsídio da Lei 7.955/2023. Quem está na folha como "
                     "parlamentar num mês sem verba (licenciado para ser secretário de Estado, por exemplo) tem o salário "
                     "mostrado, mas não conta como no cargo nesse mês."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Ressarcimento de despesas do mandato, por subcota, com nota fiscal.",
    "verba_notas": ["A Alepi publica a verba nota a nota (competência, subcota e valor). O fornecedor e o CNPJ só estão no PDF "
                    "de cada nota, que não é lido: a verba aparece por subcota, sem fornecedor.",
                    "O site vai até o último mês em que a verba de pelo menos 80% dos deputados já está publicada."],
    "pagina": "https://www.al.pi.leg.br/",
    "notas": ["Quem está no cargo: os meses com notas da verba indenizatória e, depois do último mês com a verba publicada, "
              "os meses na folha da Alepi como parlamentar. Até mar/2026 a folha traz cerca de 39 parlamentares para 30 vagas: "
              "os licenciados (secretários de Estado) continuam nela.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": VERBA, "folha": FOLHA},
}
MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9,
         "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}


def _pedir(metodo, url, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=150, **kw)
            r.raise_for_status()
            dormir(1)
            return r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _texto(t):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())


def _campo(nome, t):
    m = re.search(rf'name="{nome}" value="([^"]*)"', t)
    return H.unescape(m.group(1)) if m else ""


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


# ---------------------------------------------------------------- verba
def _notas(t):
    """Página da consulta da verba -> [notas]. Cada nota é uma linha da tabela, seguida da linha (escondida) do comprovante."""
    saida = []
    for parte in re.split(r'<TR[^>]*id="SC_ancor\d+"[^>]*>', t)[1:]:
        cel = {m.group(1): _texto(m.group(2)) for m in re.finditer(r'<TD[^>]*class="[^"]*css_(mv_[a-z_]+)_grid_line[^"]*"[^>]*>(.*?)</TD>', parte, flags=re.S | re.I)}
        if cel.get("mv_competencia"):
            m = re.match(r"(\d{2})/(\d{4})", cel["mv_competencia"])
            if m:
                saida.append({"ano": int(m.group(2)), "mes": int(m.group(1)), "parlamentar": cel.get("mv_parlamentar", ""),
                              "subcota": cel.get("mv_subcota", ""), "valor": num(cel.get("mv_valor") or "0"), "documento": "", "matricula": ""})
        doc = re.search(r"(\d{6})_(\d{7})_[0-9a-f]{32}\.pdf", parte)
        if doc and saida and not saida[-1]["documento"]:
            saida[-1]["documento"] = doc.group(0)
            saida[-1]["matricula"] = str(int(doc.group(2)))
    return saida


def _coletar_verba(meses):
    arq = PASTA / "verba_notas.csv"
    vb = pd.read_csv(arq, dtype={"matricula": str, "documento": str}) if arq.exists() else pd.DataFrame(columns=["ano", "mes"])
    feitos = set(zip(vb.ano, vb.mes)) if len(vb) else set()
    rev = not arq.exists() or time.time() - arq.stat().st_mtime > 86400
    pedir = [am for am in meses if (am // 100, am % 100) not in feitos or (am >= meses[-2] and rev)]
    if not pedir:
        return
    desde = min(pedir)
    t = _pedir("GET", VERBA)
    init, csrf = _campo("script_case_init", t), _campo("csrf_token", t)
    t = _pedir("POST", VERBA, data={"nmgp_opcao": "muda_qt_linhas", "nmgp_quant_linhas": str(POR_PAGINA), "script_case_init": init,
                                    "nm_grid_submit": "1", "csrf_token": csrf})
    notas, rec = [], 1
    while True:
        lidas = _notas(t)
        total = re.search(r"\[\s*\d+\s*a\s*(\d+)\s*de\s*([\d.]+)\s*\]", _texto(t))
        notas += lidas
        if not lidas or min(n["ano"] * 100 + n["mes"] for n in lidas) < desde or not total or int(total.group(1)) >= int(total.group(2).replace(".", "")):
            break
        rec += POR_PAGINA
        t = _pedir("POST", VERBA, data={"nmgp_opcao": "rec", "rec": str(rec), "script_case_init": init, "nm_grid_submit": "1",
                                        "csrf_token": _campo("csrf_token", t) or csrf})
    novos = pd.DataFrame(notas)
    if not len(novos):
        return
    am = novos.ano * 100 + novos.mes
    if any(b > a for a, b in zip(list(am), list(am)[1:])):
        log("  Alepi: a consulta da verba não veio em ordem de competência; conferir")
    # a leitura passou do mês mais antigo pedido (ou chegou ao fim): os meses a partir dele estão completos
    novos = novos[am >= desde]
    vb = pd.concat([vb[(vb.ano * 100 + vb.mes) < desde] if len(vb) else vb, novos])
    gravar_csv(vb.sort_values(["ano", "mes", "parlamentar", "subcota", "valor"]), arq)
    log(f"  Alepi: verba, {len(novos)} notas desde {desde}")


# ---------------------------------------------------------------- folha
class _Folha:
    """A pesquisa da folha (mês e nome); a página de resultado só aparece pedida como a moldura da página de pesquisa."""
    def __init__(self):
        t = _pedir("GET", FOLHA)
        self.init = _campo("script_case_init", t)
        self.meses = {}
        for valor, rotulo in re.findall(r'<OPTION value="(\d+##@@[^"]+)"[^>]*>([^<]+)</OPTION>', t, flags=re.I):
            m = re.match(r"(DECIMO.*|[A-Z]+)/(\d{4})$", normalizar_nome(rotulo).strip())
            if m:
                mes = 12 if m.group(1).startswith("DECIMO") else MESES.get(m.group(1))
                if mes:
                    self.meses.setdefault((int(m.group(2)), mes, "13" if m.group(1).startswith("DECIMO") else "normal"), valor)

    def buscar(self, valor_mes, nome):
        t = _pedir("POST", FOLHA, data={"script_case_init": self.init, "nmgp_opcao": "busca", "fp_regfolha_cond": "eq", "fp_regfolha": valor_mes,
                                        "fp_nome_cond": "qp", "fp_nome": nome, "NM_operador": "and", "nmgp_tab_label": "fp_regfolha?#?Mes/ano?@?fp_nome?#?Nome?@?",
                                        "bprocessa": "pesq", "form_condicao": "3"})
        u = re.search(r"src = '([^']+)'", t)
        if not u:
            return []
        url = FOLHA + u.group(1)
        for _ in range(3):
            t = _pedir("GET", url, headers={"Referer": url})
            m = re.search(r'id="nmsc_iframe_grid_transp_publico_remuneracao"[^>]*src="([^"]+)"', t)
            if not m:  # a página do resultado (com ou sem registros)
                return self._linhas(t)
            url = FOLHA + H.unescape(m.group(1))
        return None

    @staticmethod
    def _linhas(t):
        saida = []
        partes = re.split(r'<TD[^>]*class="[^"]*css_fp_servidor_grid_line[^"]*"[^>]*>', t)[1:]
        for p in partes:
            servidor = _texto(p.split("</TD>", 1)[0])
            cargo = re.search(r'css_fp_cargo_grid_line[^>]*>(.*?)</TD>', p, flags=re.S)
            regime = re.search(r'css_fp_regime_grid_line[^>]*>(.*?)</TD>', p, flags=re.S)
            grupos = [_texto(x) for x in re.findall(r'css_mv_grupo_grid_line[^>]*>(.*?)</TD>', p, flags=re.S)]
            valores = [_texto(x) for x in re.findall(r'css_mv_valor_grid_line[^>]*>(.*?)</TD>', p, flags=re.S)]
            m = re.match(r"\((\d+)\)\s*(.*)", servidor)
            if not m:
                continue
            saida.append({"matricula": m.group(1), "nome": m.group(2).strip(), "cargo": _texto(cargo.group(1)) if cargo else "",
                          "regime": _texto(regime.group(1)) if regime else "", "rubricas": list(zip(grupos, [num(v or "0") for v in valores]))})
        return saida


_FORA = re.compile(r"PREVID|IMPOSTO|IRRF|DESCONTO|CONSIGN|PENS[AÃ]O ALIM|EMPREST", re.I)


def _alvos(vb, tse):
    """Quem buscar na folha: {chave: [termos da busca, na ordem]}. A busca é "contém", e o nome da verba vem cortado em
    30 letras e às vezes abreviado ("ANA PAULA M DE ARAUJO"), que não acha ninguém: quando o nome da verba não é o
    começo do nome civil do TSE, busca primeiro pelo nome civil. Entram também os eleitos de 2022 que não aparecem na
    verba (licenciados, por exemplo)."""
    civis = sorted({normalizar_nome(x["nome"]) for x in tse.values()})
    alvos, usados = {}, set()
    for n in sorted({normalizar_nome(x) for x in vb.parlamentar}):
        achados = [c for c in civis if c.startswith(n) or vc.compativel(n, c)]
        usados |= set(achados)
        if len(achados) == 1 and not achados[0].startswith(n):
            alvos[n] = [achados[0], n]
        else:
            alvos[n] = [n]
    for v in tse.values():
        c = normalizar_nome(v["nome"])
        if v["eleito"] == "eleito" and c not in usados:
            alvos[c] = [c]
    return alvos


def _coletar_folha(meses, alvos_nomes):
    arq, arq_b = PASTA / "folha_deputados.csv", PASTA / "folha_buscas.csv"
    fol = pd.read_csv(arq, dtype={"matricula": str}) if arq.exists() else pd.DataFrame(columns=["ano", "mes", "folha", "busca", "matricula", "nome", "rubrica", "valor"])
    bus = pd.read_csv(arq_b) if arq_b.exists() else pd.DataFrame(columns=["ano", "mes", "folha", "busca", "achados"])
    rev = not arq_b.exists() or time.time() - arq_b.stat().st_mtime > 86400
    f = _Folha()
    feitos = set(zip(bus.ano, bus.mes, bus.folha, bus.busca))
    alvos = [(a, m, tipo, v) for (a, m, tipo), v in sorted(f.meses.items()) if a * 100 + m in meses]
    pedir = [(a, m, tipo, v, n) for a, m, tipo, v in alvos for n in sorted(alvos_nomes)
             if (a, m, tipo, n) not in feitos or (a * 100 + m >= meses[-2] and rev)]
    local = threading.local()

    def buscar(item):
        a, m, tipo, v, n = item
        if not hasattr(local, "f"):  # uma pesquisa (sessão ScriptCase) por linha de execução
            local.f = _Folha()
        ok = []
        for termo in alvos_nomes[n]:  # o primeiro termo que acha um parlamentar vale
            achados = local.f.buscar(v, termo)
            if achados is None:
                return None, []
            ok = [x for x in achados if "PARLAMENT" in normalizar_nome(x["regime"] + " " + x["cargo"])]
            if ok:
                break
        linhas = [{"ano": a, "mes": m, "folha": tipo, "busca": n, "matricula": x["matricula"], "nome": x["nome"], "rubrica": rub, "valor": val}
                  for x in ok for rub, val in x["rubricas"] if not _FORA.search(rub) and abs(val) >= 0.005]
        return {"ano": a, "mes": m, "folha": tipo, "busca": n, "achados": len(ok)}, linhas
    novas, buscas = [], []
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for b, linhas in ex.map(buscar, pedir):
                if b:
                    buscas.append(b)
                    novas += linhas
    finally:
        if buscas:
            chave = {(b["ano"], b["mes"], b["folha"], b["busca"]) for b in buscas}
            bus = pd.concat([bus[[k not in chave for k in zip(bus.ano, bus.mes, bus.folha, bus.busca)]], pd.DataFrame(buscas)])
            fol = pd.concat([fol[[k not in chave for k in zip(fol.ano, fol.mes, fol.folha, fol.busca)]], pd.DataFrame(novas, columns=fol.columns)])
            if gravar_csv(fol.sort_values(["ano", "mes", "folha", "nome", "rubrica"]), arq):  # as buscas só contam se a folha foi gravada
                gravar_csv(bus.sort_values(["ano", "mes", "folha", "busca"]), arq_b)
        log(f"  Alepi: folha, {len(buscas)} de {len(pedir)} buscas feitas agora ({len(novas)} linhas)")


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:
        _sessao().get(VERBA, timeout=60).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Alepi: o portal não abriu ({type(e).__name__}); fica o que já estava gravado")
        return
    meses = _meses()
    _coletar_verba(meses)
    vb = pd.read_csv(PASTA / "verba_notas.csv", dtype=str) if (PASTA / "verba_notas.csv").exists() else pd.DataFrame(columns=["parlamentar"])
    _coletar_folha(meses, _alvos(vb, comum.tse_2022(UF)))


def _categoria(rubrica, folha):
    u = normalizar_nome(rubrica)
    if folha == "13":
        return "decimo_terceiro"
    if "SUBSIDIO" in u or "SALARIO BASE" in u:
        return "salario"
    if "AUXILIO" in u:
        return "auxilios"
    return "outros_rendimentos"


def montar(tipos):
    arq_v = PASTA / "verba_notas.csv"
    if not arq_v.exists():
        return None
    vb = pd.read_csv(arq_v, dtype={"matricula": str, "documento": str}).fillna({"matricula": "", "subcota": ""})
    fol = pd.read_csv(PASTA / "folha_deputados.csv", dtype={"matricula": str}) if (PASTA / "folha_deputados.csv").exists() \
        else pd.DataFrame(columns=["ano", "mes", "folha", "busca", "matricula", "nome", "rubrica", "valor"])
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    vb["am"] = vb.ano * 100 + vb.mes
    fol = fol.drop_duplicates(["ano", "mes", "folha", "matricula", "rubrica"])  # a mesma pessoa achada por duas buscas
    fol["am"] = fol.ano * 100 + fol.mes if len(fol) else pd.Series(dtype=int)
    normal = fol[fol.folha == "normal"] if len(fol) else fol
    ultimo_dado = int(normal.am.max()) if len(normal) else int(vb.am.max())
    por_mes = vb.groupby("am").parlamentar.nunique()
    ultimo_verba = max(int(m) for m, n in por_mes.items() if n >= 0.8 * por_mes.median())  # último mês com a verba publicada
    # matrícula de quem tem nota na verba (vem do nome do comprovante)
    mat_de = {}
    for p, g in vb[vb.matricula != ""].groupby("parlamentar"):
        mat_de[p] = g.matricula.mode().iloc[0]
    # pessoas pela matrícula: o nome completo vem da folha; sem folha, o nome da verba (cortado em 30 letras)
    pessoas = {}
    for mat, g in fol.groupby("matricula"):
        pessoas[mat] = {"civil": g.nome.mode().iloc[0], "meses": set(normal[normal.matricula == mat].am)}
    for p, g in vb.groupby("parlamentar"):
        mat = mat_de.get(p) or f"N:{normalizar_nome(p)}"
        x = pessoas.setdefault(mat, {"civil": p, "meses": set()})
        x["meses_verba"] = x.get("meses_verba", set()) | set(g.am)
    # a mesma pessoa por duas matrículas (ou por uma matrícula e um nome da verba sem comprovante) fica uma só
    por_cod, cod_mat = {}, {}
    for mat, x in pessoas.items():
        civil = x["civil"]
        n = normalizar_nome(civil)
        t = por_civil.get(n) or next((v for k, v in por_civil.items() if len(n) >= 25 and k.startswith(n)), None) or comum.achar(civil, tse) or {}
        codigo = int(t["sq"]) if t.get("sq", "").isdigit() else (int(mat) if mat.isdigit() else comum.codigo_de(civil, t))
        cod_mat[mat] = codigo
        y = por_cod.setdefault(codigo, {"t": t, "civil": civil, "meses": set(), "meses_verba": set()})
        if len(civil) > len(y["civil"]):
            y["civil"] = civil
        y["meses"] |= x["meses"]
        y["meses_verba"] |= x.get("meses_verba", set())
    ver, mandatos = [], []
    for codigo, x in por_cod.items():
        t, civil = x["t"], x["civil"]
        nome_civil = t.get("nome") or civil
        ver.append({"codigo": codigo, "nome": vc.titulo(t.get("urna") or civil), "nome_civil": vc.titulo(nome_civil),
                    "partido": partidos.get(normalizar_nome(nome_civil), ""),
                    "genero": t.get("genero") or ("F" if feminino(nome_civil) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        # no cargo: os meses com notas da verba (o licenciado, secretário de Estado por exemplo, continua na folha como
        # parlamentar, mas não tem verba) e, depois do último mês com a verba publicada, os meses na folha
        x["no_cargo"] = meses_p = sorted(m for m in ({v for v in x["meses_verba"] if v <= ultimo_verba} | {f for f in x["meses"] if f > ultimo_verba})
                                         if m <= ultimo_dado) if x["meses_verba"] else sorted(m for m in x["meses"] if m <= ultimo_dado)
        if not meses_p:
            continue
        per = comum.periodos(meses_p, ultimo_dado, ultimo, folga=2)
        fim = max(meses_p)
        if fim < vc.menos_meses(ultimo_dado, 1):
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    ganha = []
    for r in fol.itertuples():
        ganha.append({"ano": r.ano, "mes": r.mes, "codigo": cod_mat[r.matricula], "categoria": _categoria(r.rubrica, r.folha), "valor": r.valor})
    # mês no cargo sem a folha (a busca não achou): o subsídio da lei
    subsidio = lambda am: [v for d, v in CFG["subsidio"] if d <= am][-1]
    for codigo, x in por_cod.items():
        if not x["meses"]:
            continue
        for am in sorted(m for m in x.get("no_cargo", []) if m not in x["meses"] and min(x["meses"]) <= m <= max(x["meses"])):
            ganha.append({"ano": am // 100, "mes": am % 100, "codigo": codigo, "categoria": "salario", "valor": subsidio(am)})
    vb["codigo"] = [cod_mat.get(mat_de.get(p) or f"N:{normalizar_nome(p)}") for p in vb.parlamentar]
    d = vb[vb.valor.abs() >= 0.005]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.codigo, "tipo": d.subcota.map(_tipo), "fornecedor": "", "cnpj_cpf": "", "valor": d.valor}).dropna(subset=["codigo"])
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado, ultimo_verba))  # até o último mês com a verba de quase todos publicada
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]), despesas=desp)


_TIPOS = [(r"COMBUST", "Combustível"), (r"ALIMENTA", "Alimentação"), (r"LOCA[CÇ][AÃ]O DE IM[OÓ]VE|IM[OÓ]VE", "Escritório (aluguel e contas)"),
          (r"AERONAVE|EMBARCA|VE[IÍ]CULO", "Aluguel de carros"), (r"CONSULTORIA|TRABALHOS T[EÉ]CNICOS|PESQUISA", "Consultorias e assessorias"),
          (r"DIVULGA|PUBLICIDADE", "Divulgação do mandato"), (r"TELEF|INTERNET|COMUNICA", "Telefone e internet"),
          (r"PASSAGE|HOSPEDAG", "Passagens e hospedagem"), (r"SEGURAN", "Segurança"), (r"EXPEDIENTE|MATERIAL", "Material de escritório")]


def _tipo(subcota):
    u = normalizar_nome(subcota)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(re.sub(r"^[IVXL]+\s+(?:[a-z]\)\s*)?", "", subcota))
