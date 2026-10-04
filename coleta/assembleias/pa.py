"""Assembleia Legislativa do Pará (Alepa): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alepa, https://alepa.pa.gov.br/Transparencia/):
- Verba indenizatória: o painel da página "Verba Indenizatória" (DevExpress Dashboard em alepa.quartertec.com.br,
  dashboard57), lido do mesmo endereço que o painel usa (/api/dashboard/data/DashboardItemGetAction): as liquidações de
  cada deputado (data, deputado, classificação, descrição e valor). É o pagamento ao deputado, sem fornecedor nem nota.
  As linhas "REGISTRA OS VALORES REFERENTES AS RETENCOES" (o imposto retido de parte dos deputados sobre a indenização de
  transporte) não são guardadas à parte: o valor volta para a liquidação do auxílio, que fica com o valor inteiro.
- Equipe: a página "Verba de Gabinete" (sigep.alepa.pa.gov.br/transp/frame_verbagabinete.php): por gabinete e mês,
  quantos assessores e o total pago a eles.
- Folha: a "Remuneração de Pessoal" (sigep.alepa.pa.gov.br/transp/frame_servidores.php): a busca pelo começo do nome de
  cada deputado no mês e a página de rendimentos (detalhecc.php): remuneração, férias, adiantamento de 13º, pecúnia e
  redutor constitucional. Descontos, líquido e CPF não são lidos nem guardados. A folha do 13º salário de 2025 não traz
  deputados.
- Deputados: a "Relação de Pessoal" (frame_relacaopessoal.php), cargo DEPUTADO ESTADUAL: nome civil, matrícula, admissão;
  quem tem verba ou gabinete sem estar nela entra pelo nome civil do TSE.
- Nome parlamentar, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os meses com verba indenizatória ou com gabinete na verba de gabinete; para quem não aparece no painel
da verba (João Pingarilho), os meses na folha ou com gabinete. Deputado na folha sem verba no mês (licenciado, por exemplo)
não conta como no cargo.
"""
import html as H
import json
import re
import time

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "PA"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SIGEP = "https://sigep.alepa.pa.gov.br/transp/"
PAINEL = "https://alepa.quartertec.com.br"
PORTAL = "https://alepa.pa.gov.br/Transparencia/"
PASTA = DADOS / "assembleias" / "pa"
SIMULTANEOS = 3
EQUIPE_DESDE = 202604  # a página "Verba de Gabinete" só tem os meses desde abril de 2026 (conferido em 01/10/2026)
CFG = {
    "cod": COD, "n": "Pará", "uf": UF, "casa": "Assembleia Legislativa do Pará", "vagas": 41, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da Alepa (remuneração, férias, adiantamento de 13º e pecúnia, menos o redutor "
                     "constitucional), sem os descontos. Nos meses no cargo sem a folha do deputado, vale o subsídio do "
                     "Decreto Legislativo 1/2023. Quem está na folha como deputado num mês sem verba indenizatória "
                     "(licenciado, por exemplo) tem o salário mostrado, mas não conta como no cargo nesse mês."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Valor mensal pago a cada deputado para despesas do mandato, mais a indenização de transporte.",
    "verba_notas": ["A Alepa publica as liquidações da verba indenizatória e da indenização de transporte de cada deputado "
                    "(data, classificação, descrição e valor), sem fornecedor nem nota fiscal.",
                    "O mês é o que a descrição da liquidação indica (\"VERBA INDENIZATORIA SET/26\"); quando ela não diz, o mês "
                    "da liquidação (ou o anterior, se a liquidação é dos primeiros dez dias do mês).",
                    "O site vai até o último mês em que a verba de pelo menos 80% dos deputados já foi liquidada."],
    "equipe_nota": ("Equipe: assessores do gabinete e o total pago a eles no mês, pela página \"Verba de Gabinete\" da Alepa, "
                    "que tem os meses desde abril de 2026."),
    "pagina": "https://www.alepa.pa.gov.br/",
    "notas": ["Quem está no cargo: os meses com verba indenizatória ou com gabinete na verba de gabinete da Alepa; para quem "
              "não aparece no painel da verba, os meses na folha como deputado estadual ou com gabinete.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": f"{PORTAL}Page/VerbaIndenizatoria", "folha": f"{PORTAL}Page/RemuneracaodePessoal",
               "equipe": f"{PORTAL}Page/VerbadeGabinete"},
}
MESES_NOME = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}


def _pedir(metodo, url, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=120, **kw)
            r.raise_for_status()
            dormir(1)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _texto(t):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())


def _linhas(t):
    """Tabela HTML -> [[células em texto], [links da linha]]."""
    saida = []
    for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
        cel = [_texto(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, flags=re.S)]
        if cel:
            saida.append((cel, [H.unescape(x) for x in re.findall(r'href="([^"]+)"', linha)]))
    return saida


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _competencia(data, descricao):
    """Mês da liquidação: o que a descrição diz ("SET/26", "AGOSTO/26", "FEV/2026"); senão (ou se o ano da descrição
    não bate com o da liquidação, como "ABR/95"), o da data (o anterior, se a liquidação é dos primeiros dez dias)."""
    a, mm, dia = int(data[:4]), int(data[5:7]), int(data[8:10])
    d = normalizar_nome(descricao)
    m = re.search(r"\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[A-Z]*\s*[/ -]\s*(20\d{2}|\d{2})\b", d)
    if m:
        ano = int(m.group(2))
        ano = 2000 + ano if ano < 100 else ano
        if abs(ano - a) <= 1:
            return ano * 100 + MESES_NOME[m.group(1)]
    am = a * 100 + mm
    return vc.menos_meses(am, 1) if dia <= 10 else am


def _verba():
    """Liquidações do painel da verba indenizatória (todas, desde 2014; o painel não filtra por ano sem um pedido a mais)."""
    r = _pedir("GET", f"{PAINEL}/api/dashboard/data/DashboardItemGetAction", params={"dashboardId": "dashboard57", "itemId": "gridDashboardItem2"})
    d = r.json()["ItemData"]
    nomes = {x["ID"]: x["DataMember"] for x in d["MetaData"]["DimensionDescriptors"]["Default"]}
    medida = d["MetaData"]["MeasureDescriptors"][0]["ID"]
    ds = d["DataStorageDTO"]
    mapas = ds["EncodeMaps"]
    linhas = []
    for fatia in ds["Slices"]:
        chaves = fatia["KeyIds"]
        for k, v in fatia["Data"].items():
            idx = json.loads(k)
            reg = {nomes[c]: mapas[c][i] for c, i in zip(chaves, idx)}
            valor = v.get("0") if "0" in v else v.get(medida)
            if valor is None or "DatatNL" not in reg:
                continue
            linhas.append({"data": reg["DatatNL"][:10], "deputado": reg.get("NomePolitico", ""), "conta": reg.get("NomeConta", ""),
                           "descricao": reg.get("DescricaoNL", ""), "valor": round(float(valor), 2)})
    df = pd.DataFrame(linhas)
    if not len(df):
        return df
    comp = [_competencia(a, b) for a, b in zip(df.data, df.descricao)]
    df = df.assign(ano=[c // 100 for c in comp], mes=[c % 100 for c in comp])
    # "REGISTRA OS VALORES REFERENTES AS RETENCOES": o imposto retido de parte dos deputados sobre a indenização de
    # transporte (27,5%; a liquidação do auxílio vem com o valor depois da retenção). A retenção não é guardada à parte:
    # volta para a liquidação do auxílio do mesmo deputado e mês, que fica com o valor inteiro, como a dos outros.
    ret = df.descricao.map(normalizar_nome).str.contains("RETENC")
    base = df[~ret].copy()
    for (dep, a, m), v in df[ret].groupby(["deputado", "ano", "mes"]).valor.sum().items():
        alvo = base[(base.deputado == dep) & (base.ano == a) & (base.mes == m) & base.conta.map(normalizar_nome).str.contains("TRANSPORTE")]
        if len(alvo):
            base.loc[alvo.index[0], "valor"] = round(base.loc[alvo.index[0], "valor"] + v, 2)
        else:
            base = pd.concat([base, pd.DataFrame([{"data": df[ret & (df.deputado == dep) & (df.ano == a) & (df.mes == m)].data.min(), "deputado": dep,
                                                    "conta": "INDENIZACAO DE TRANSPORTE", "descricao": "AUXILIO TRANSPORTE", "valor": round(v, 2), "ano": a, "mes": m}])])
    return base[base.ano * 100 + base.mes >= INICIO].sort_values(["ano", "mes", "deputado", "data", "conta"])


def _sem_titulo(nome):
    n = re.sub(r"^GAB(?:INETE)?\.?\s*(?:DA\s+|DO\s+)?DEP(?:UTAD[OA])?\.?\s*", "", str(nome), flags=re.I)
    return re.sub(r"^Deputad[oa]\s+", "", n, flags=re.I).strip()


def _termo(nome, outros):
    """Começo do nome para a busca da folha (as três primeiras palavras, ou mais, se outro deputado começa igual): o
    nome de um deputado às vezes muda de um mês para outro ("MARIA DO CARMO MARTINS LIMA" e "MARIA DO CARMO CARDOSO
    MARTINS", a mesma matrícula)."""
    p = normalizar_nome(nome).split()
    n = 3
    while n < len(p) and any(o != normalizar_nome(nome) and normalizar_nome(o).split()[:n] == p[:n] for o in outros):
        n += 1
    return " ".join(p[:n])


def _alvos(dep, nomes_fora, tse):
    """{nome civil: começo do nome para a busca}: os deputados da Relação de Pessoal (ativos ou admitidos desde 2023) e,
    pelo nome civil do TSE, quem tem verba ou gabinete sem estar nela (o suplente Neil Duarte não aparece na Relação)."""
    ano_adm = dep.admissao.str[-4:].map(lambda x: int(x) if x.isdigit() else 0)
    nomes = {normalizar_nome(n) for n in dep[(dep.situacao.str.upper() == "ATIVO") | (ano_adm >= 2023)].nome}
    for n in nomes_fora:
        t = comum.achar(_sem_titulo(n), tse)
        civil = normalizar_nome(t["nome"]) if t else ""
        if civil and not any(civil == x or vc.compativel(civil, x) or vc.compativel(x, civil) for x in nomes):
            nomes.add(civil)
    return {n: _termo(n, nomes) for n in sorted(nomes)}


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # um pedido leve antes: se o portal não responde, fica o que já estava gravado
        _sessao().get(SIGEP + "frame_verbagabinete.php", timeout=30).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Alepa: o portal não abriu ({type(e).__name__}); fica o que já estava gravado")
        return
    meses = _meses()
    velho = lambda arq: not arq.exists() or time.time() - arq.stat().st_mtime > 86400
    arq_v, arq_e, arq_d = PASTA / "verba_liquidacoes.csv", PASTA / "equipe_gabinetes.csv", PASTA / "deputados.csv"
    arq_f, arq_b = PASTA / "folha_deputados.csv", PASTA / "folha_buscas.csv"
    # 1. verba indenizatória (um pedido traz tudo)
    if velho(arq_v):
        v = _verba()
        if len(v):
            gravar_csv(v, arq_v)
            log(f"  Alepa: verba indenizatória, {len(v)} liquidações desde {INICIO // 100}")
    # 2. equipe: verba de gabinete de cada mês
    eq = pd.read_csv(arq_e) if arq_e.exists() else pd.DataFrame(columns=["ano", "mes", "gabinete", "assessores", "total"])
    feitos, rev = set(zip(eq.ano, eq.mes)), velho(arq_e)
    for am in meses:
        if am < EQUIPE_DESDE or (am // 100, am % 100) in feitos and (am < meses[-2] or not rev):
            continue
        t = _pedir("POST", SIGEP + "frame_verbagabinete.php", data={"anoref": f"{am // 100 % 100:02d}", "mes": f"{am % 100:02d}"}).text
        novos = [{"ano": am // 100, "mes": am % 100, "gabinete": " ".join(c[0].split()), "assessores": int(re.sub(r"\D", "", c[2]) or 0), "total": num(c[3])}
                 for c, _ in _linhas(t) if len(c) >= 4 and c[0].upper().startswith("GAB") and re.search(r"\d,\d{2}", c[3])]
        ref = re.search(r"Refer[êe]ncia:\s*([A-Za-zçÇ]+)/(\d{4})", _texto(t))
        if novos and ref and int(ref.group(2)) == am // 100:
            antes = eq[~((eq.ano == am // 100) & (eq.mes == am % 100))]
            eq = pd.concat([antes, pd.DataFrame(novos)]) if len(antes) else pd.DataFrame(novos)
            gravar_csv(eq.sort_values(["ano", "mes", "gabinete"]), arq_e)
    # 3. deputados (relação de pessoal, cargo DEPUTADO ESTADUAL)
    if velho(arq_d):
        t = _pedir("POST", SIGEP + "frame_relacaopessoal.php", data={"b_nome": "", "b_cargo": "DEPUTADO ESTADUAL", "b_lotacao": ""}).text
        dep = [{"matricula": c[0], "nome": c[1], "admissao": c[2], "exoneracao": c[3], "situacao": c[-1]}
               for c, _ in _linhas(t) if len(c) >= 9 and c[0].isdigit() and "DEPUTAD" in normalizar_nome(c[5])]
        if dep:
            gravar_csv(pd.DataFrame(dep), arq_d)
    if not arq_d.exists():
        return
    dep = pd.read_csv(arq_d, dtype=str).fillna("")
    vb = pd.read_csv(arq_v).fillna("") if arq_v.exists() else pd.DataFrame(columns=["deputado"])
    alvos = _alvos(dep, sorted(set(vb.deputado) | set(eq.gabinete)), comum.tse_2022(UF))
    # 4. folha: busca pelo começo do nome em cada mês e a página de rendimentos de quem é deputado estadual
    fol = pd.read_csv(arq_f, dtype={"matricula": str}) if arq_f.exists() else pd.DataFrame(columns=["ano", "mes", "matricula", "nome"])
    bus = pd.read_csv(arq_b) if arq_b.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "achados", "termo"])
    if "termo" not in bus:
        bus["termo"] = ""
    bus["termo"] = bus.termo.fillna("")
    # já feito: achado, ou buscado pelo começo do nome (a busca antiga, pelo nome inteiro, não achava quem mudou de nome)
    feitos, rev = {(a, m, n) for a, m, n, x, t in zip(bus.ano, bus.mes, bus.nome, bus.achados, bus.termo) if x or t}, velho(arq_b)
    pedir = [(am, n) for am in meses for n in alvos if (am // 100, am % 100, n) not in feitos or (am >= meses[-2] and rev)]

    def buscar(item):
        am, n = item
        termo = alvos[n]
        consulta = lambda b: _pedir("POST", SIGEP + "frame_servidores.php", data={"anoref": f"{am // 100 % 100:02d}", "mes": f"{am % 100:02d}", "b_nome": b}).text
        t = consulta(termo)
        if re.search(r"«[^»]*-\s*2\b", _texto(t)):  # mais de uma página (20 por página): busca pelo nome inteiro
            termo = n
            t = consulta(termo)
        linhas = []
        for c, links in _linhas(t):
            if len(c) < 4 or not normalizar_nome(c[1]).startswith(termo) or "DEPUTAD" not in normalizar_nome(c[2]):
                continue
            link = next((x for x in links if x.startswith("detalhecc.php")), None)
            if not link:
                continue
            x = _texto(_pedir("GET", SIGEP + link).text)
            ref = re.search(r"Rendimentos,\s*([A-Za-zçÇ]+)/(\d{4})", x)
            if not ref or int(ref.group(2)) != am // 100:
                continue
            v = lambda rotulo: num((re.search(rotulo + r"\s*R\$\s*(-?[\d.]+,\d{2})", x) or [None, "0,00"])[1])
            linhas.append({"ano": am // 100, "mes": am % 100, "matricula": c[0].lstrip("0"), "nome": c[1], "folha": (re.search(r"TIPO DE FOLHA:\s*(\S+)", x) or [None, ""])[1],
                           "remuneracao": v("Remuneração"), "ferias": v("Férias"), "decimo": v("Adiantamento de 13º"), "pecunia": v("Pecúnia"),
                           "bruto": v("Total Bruto"), "redutor": v(r"Redutor C\w+")})
        return {"ano": am // 100, "mes": am % 100, "nome": n, "achados": len(linhas), "termo": termo}, linhas
    novas, buscas = [], []
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for b, linhas in ex.map(buscar, pedir):
                buscas.append(b)
                novas += linhas
    finally:
        if buscas:
            chave = {(b["ano"], b["mes"], b["nome"]) for b in buscas}
            bus = pd.concat([bus[[k not in chave for k in zip(bus.ano, bus.mes, bus.nome)]], pd.DataFrame(buscas)])
            gravou = True
            if novas:
                # a mesma matrícula no mesmo mês vale uma vez (a busca nova substitui a antiga)
                nv = pd.DataFrame(novas).drop_duplicates(["ano", "mes", "matricula", "folha"])
                novos_k = set(zip(nv.ano, nv.mes, nv.matricula))
                antes = fol[[k not in novos_k for k in zip(fol.ano, fol.mes, fol.matricula.astype(str))]] if len(fol) else fol
                fol = pd.concat([x for x in (antes, nv) if len(x)])
                gravou = gravar_csv(fol.sort_values(["ano", "mes", "nome"]), arq_f)
            if gravou:  # as buscas só contam como feitas se a folha foi gravada (util.gravar_com pode recusar)
                gravar_csv(bus.sort_values(["ano", "mes", "nome"]), arq_b)
        log(f"  Alepa: folha, {len(buscas)} de {len(pedir)} buscas feitas agora ({len(novas)} contracheques)")


# nomes que o TSE não resolve sozinho (nome do gabinete ou do painel -> nome de urna de 2022), conferidos pelos meses
APELIDOS = {"TORRINHO TORRES": "TORRINHO"}


def _tipo(conta):
    u = normalizar_nome(conta)
    if "TRANSPORTE" in u:
        return "Indenização de transporte"
    if "RESTITU" in u:
        return "Indenizações e restituições"
    return "Verba indenizatória"


def montar(tipos):
    arq_f = PASTA / "folha_deputados.csv"
    if not arq_f.exists() and not (PASTA / "equipe_gabinetes.csv").exists():
        return None
    fol = pd.read_csv(arq_f, dtype={"matricula": str}) if arq_f.exists() else pd.DataFrame(columns=["ano", "mes", "matricula", "nome", "folha", "remuneracao", "ferias", "decimo", "pecunia", "redutor"])
    fol = fol.drop_duplicates(["ano", "mes", "matricula", "folha"])
    eq = pd.read_csv(PASTA / "equipe_gabinetes.csv") if (PASTA / "equipe_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "gabinete", "assessores", "total"])
    vb = pd.read_csv(PASTA / "verba_liquidacoes.csv").fillna("") if (PASTA / "verba_liquidacoes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "deputado", "conta", "valor"])
    dep = pd.read_csv(PASTA / "deputados.csv", dtype=str).fillna("") if (PASTA / "deputados.csv").exists() else pd.DataFrame(columns=["matricula", "nome"])
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    for df in (fol, eq, vb):
        df["am"] = df.ano.astype(int) * 100 + df.mes.astype(int) if len(df) else pd.Series(dtype=int)
    # o mês a mês vai até o último mês com a folha completa (a busca de um mês leva algumas rodadas)
    por_mes = fol.groupby("am").matricula.nunique() if len(fol) else pd.Series(dtype=int)
    completos = [int(m) for m, n in por_mes.items() if n >= 0.9 * por_mes.median()]
    ultimo_dado = max(completos) if completos else int(eq.am.max())
    pessoas = {}  # chave -> {"k", "t", "nome", "civil", "meses_folha", "meses_verba", "meses_gab", "mats"}

    def pessoa(t, nome, civil=""):
        k = t["sq"] if t else "N:" + normalizar_nome(civil or nome)
        p = pessoas.setdefault(k, {"k": k, "t": t or {}, "nome": nome, "civil": civil, "meses_folha": set(), "meses_verba": set(), "meses_gab": set(), "mats": set()})
        if civil and not p["civil"]:
            p["civil"] = civil
        return p

    def resolver(nome):
        n = normalizar_nome(_sem_titulo(nome))
        return comum.achar(APELIDOS.get(n, n), tse)
    # folha: pela matrícula (o nome às vezes muda de um mês para outro); o nome civil é o da Relação de Pessoal ou o mais recente
    nome_rel = {str(m).lstrip("0"): n for m, n in zip(dep.matricula, dep.nome)}
    for mat, g in fol.sort_values("am").groupby("matricula"):
        civil = nome_rel.get(str(mat).lstrip("0")) or g.nome.iloc[-1]
        t = next((por_civil[normalizar_nome(n)] for n in [civil] + list(g.nome) if normalizar_nome(n) in por_civil), None) or comum.achar(civil, tse)
        p = pessoa(t, vc.titulo((t or {}).get("urna") or civil), civil)
        p["meses_folha"] |= set(g.am)
        p["mats"].add(mat)

    # gabinete e painel: pelo TSE; senão, o nome mais parecido entre as pessoas já achadas
    def casar(nome):
        t = resolver(nome)
        if t:
            return pessoa(t, vc.titulo(t["urna"]))
        opcoes = [(p["t"].get("urna") or p["nome"], k) for k, p in pessoas.items()] + [(p["civil"], k) for k, p in pessoas.items() if p["civil"]]
        k = vc.achar_parecido(_sem_titulo(nome), opcoes)
        return pessoas[k] if k else pessoa(None, vc.titulo(_sem_titulo(nome)))
    gab_de = {}
    for gab, g in eq.groupby("gabinete"):
        p = casar(gab)
        p["meses_gab"] |= set(g.am)
        gab_de[gab] = p
    verba_de = {n: casar(n) for n in sorted(set(vb.deputado)) if n}
    for n, g in vb[vb.valor.abs() >= 0.005].groupby("deputado"):
        if n in verba_de:
            verba_de[n]["meses_verba"] |= set(g.am)
    ver, mandatos, cod_de = [], [], {}
    for k, p in pessoas.items():
        t = p["t"]
        codigo = comum.codigo_de(p["civil"] or p["nome"], t)
        cod_de[k] = codigo
        civil = t.get("nome") or p["civil"] or p["nome"]
        ver.append({"codigo": codigo, "nome": p["nome"], "nome_civil": vc.titulo(civil), "partido": partidos.get(normalizar_nome(civil), ""),
                    "genero": t.get("genero") or ("F" if feminino(civil) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        p["no_cargo"] = sorted(m for m in ((p["meses_verba"] if p["meses_verba"] else p["meses_folha"]) | p["meses_gab"]) if m <= ultimo_dado)
        if not p["no_cargo"]:
            continue
        per = comum.periodos(p["no_cargo"], ultimo_dado, ultimo, folga=2)
        fim = max(p["no_cargo"])
        if fim < vc.menos_meses(ultimo_dado, 1):
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    ganha = []
    cod_mat = {m: cod_de[k] for k, p in pessoas.items() for m in p["mats"]}
    for r in fol.itertuples():
        c = cod_mat.get(r.matricula)
        if c is None:
            continue
        for cat, v in (("salario", r.remuneracao - r.redutor), ("outros_rendimentos", r.ferias + r.pecunia), ("decimo_terceiro", r.decimo)):
            if abs(v) >= 0.005:
                ganha.append({"ano": r.ano, "mes": r.mes, "codigo": c, "categoria": cat, "valor": round(v, 2)})
    # mês no cargo sem a folha de quem aparece na folha em outros meses: o subsídio do Decreto Legislativo 1/2023
    subsidio = lambda am: [v for d, v in CFG["subsidio"] if d <= am][-1]
    for k, p in pessoas.items():
        if not p["meses_folha"]:
            continue  # sem folha nenhuma: o vc.montar usa o subsídio da lei
        for am in p.get("no_cargo", []):
            if am not in p["meses_folha"]:
                ganha.append({"ano": am // 100, "mes": am % 100, "codigo": cod_de[k], "categoria": "salario", "valor": subsidio(am)})
    d = vb[vb.valor.abs() >= 0.005] if len(vb) else vb
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.deputado.map(lambda n: cod_de[verba_de[n]["k"]] if n in verba_de else None),
                         "tipo": d.conta.map(_tipo), "fornecedor": "", "cnpj_cpf": "", "valor": d.valor}).dropna(subset=["codigo"]) if len(d) else None
    e = eq.assign(codigo=eq.gabinete.map(lambda g: cod_de[gab_de[g]["k"]] if g in gab_de else None)).dropna(subset=["codigo"]) if len(eq) else eq
    equipe = pd.DataFrame({"ano": e.ano, "mes": e.mes, "codigo": e.codigo.astype(int), "pessoas": e.assessores, "custo": e.total}) if len(e) else None
    ind = vb[vb.conta.map(normalizar_nome) == "INDENIZACOES"].groupby("am").deputado.nunique() if len(vb) else pd.Series(dtype=int)
    ultimo_verba = max([int(m) for m, n in ind.items() if n >= 0.8 * ind.median()] or [ultimo_dado])
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado, ultimo_verba))  # até o último mês com a verba de quase todos liquidada
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]), despesas=desp, equipe=equipe)
