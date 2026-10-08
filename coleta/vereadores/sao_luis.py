"""Câmara Municipal de São Luís: vereador por vereador.

Fontes:
- Folha de pagamento nominal, mês a mês (vereadores e servidores), no Portal da Remuneração da Câmara:
  https://cmsaoluis.portalremuneracao.com.br/ — os meses estão na lista "referencia" da página inicial (com nomes
  irregulares: "jan/25", "10/2025", "12/25"...) e os dados vêm de /data?referencia=&nome=&draw=1&start=0&length=
  (JSON). O robots.txt desse endereço permite tudo.
  Guardamos o bruto de cada vereador (cargo VEREADOR) e, dos gabinetes (lotação "GAB VER <nome>" e variações), só o
  número de pessoas e o custo bruto por mês e a contagem de cargos do último mês. Descontos, líquido, CPF, matrícula e
  nomes de servidores não são guardados.
- Nome de urna, nome completo, partido e gênero: TSE (eleição de 2024).
- Foto, página, nome civil e partido de quem está na legislatura (desde 08/10/2026): a lista de vereadores do site
  principal da Câmara, https://www.cmsaoluis.ma.gov.br/vereadores (robots.txt "Disallow: /", que é uma convenção e não lei:
  lemos com pausa). O partido é o da Câmara (o de hoje); sem ele, o do TSE.
Fora: a verba indenizatória de exercício parlamentar (VIEP). O site da Câmara só publica relatórios de empenho do ano
(https://www.cmsaoluis.ma.gov.br/transparencia/cotas-parlamentares: empenhos anuais e valores pagos acumulados, sem o mês
a mês de cada vereador), que não cabem no mês a mês do site.
"""
import hashlib
import html as html_lib
import json
import re
import time

import pandas as pd

from ..config import DADOS
from ..util import _sessao, cache_valido, gravar_csv, log, normalizar_nome, verificar_prazo
from . import comum

COD = 2111300
SITE = "https://www.cmsaoluis.ma.gov.br"
LISTA = f"{SITE}/vereadores"
COTAS = f"{SITE}/transparencia/cotas-parlamentares"
INICIO = 202501
PORTAL = "https://cmsaoluis.portalremuneracao.com.br"
PASTA = DADOS / "municipios" / "sao_luis"
REBAIXAR = 3
MESES_ABREV = {m: i for i, m in enumerate(["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"], 1)}
CFG = {
    "cod": COD, "n": "São Luís", "uf": "MA", "casa": "Câmara Municipal de São Luís", "vagas": 31, "inicio": INICIO,
    "equipe_nota": "Servidores lotados no gabinete do vereador, pela folha de pagamento da Câmara (valor bruto, todos os vínculos: "
                   "verba de gabinete, comissionados, prestadores de serviço e servidores efetivos). O gabinete da Presidência não entra. "
                   "Quando o titular se licencia, o gabinete continua com o nome dele e a folha não diz qual suplente o ocupa: esses meses ficam de fora.",
    "credito_foto": "Câmara Municipal de São Luís", "pagina": f"{PORTAL}/",
    "fontes": {"folha": f"{PORTAL}/", "vereadores": "https://www.cmsaoluis.ma.gov.br/vereadores",
               "cotas": "https://www.cmsaoluis.ma.gov.br/transparencia/cotas-parlamentares"},
    "conferir_gastos": False,  # a Câmara não publica a verba (ou cota) de cada gabinete: não há gasto do mês para conferir
}
CAMPOS = ["nome", "referencia", "cargo_funcao", "lotacao", "vinculo", "tipo_folha", "valor", "admissao", "exoneracao", "matricula"]


# ---------------------------------------------------------------- acesso ao portal
def _pedir(caminho, params=None, arquivo=None, dias=None):
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_text(encoding="utf-8")
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().get(f"{PORTAL}{caminho}", params=params, timeout=180)
            r.raise_for_status()
            t = r.text
            break
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))
    time.sleep(1.2)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(t, encoding="utf-8")
    return t


def _valor(t):
    t = re.sub(r"[^\d,]", "", str(t or ""))
    return float(t.replace(",", ".")) if t else 0.0


def _mes(rotulo):
    """"jan/25", "10/2025", "12/25", "13/2021" -> (ano, mês); o mês 13 é a folha do 13º."""
    t = rotulo.strip().lower()
    m = re.match(r"^([a-zç]{3})/(\d{2}|\d{4})$", t)
    if m and m.group(1) in MESES_ABREV:
        mes, ano = MESES_ABREV[m.group(1)], int(m.group(2))
    else:
        m = re.match(r"^(\d{1,2})/(\d{2}|\d{4})$", t)
        if not m:
            return None
        mes, ano = int(m.group(1)), int(m.group(2))
    ano = ano + 2000 if ano < 100 else ano
    return (ano, mes) if 1 <= mes <= 13 else None


def referencias():
    """Meses publicados: [(rótulo, ano, mês)], pela lista "referencia" da página inicial."""
    t = _pedir("/")
    sel = re.search(r'<select[^>]*id="referencia"[^>]*>(.*?)</select>', t, re.S)
    saida = []
    for v in re.findall(r'<option[^>]*value="([^"]*)"', sel.group(1) if sel else ""):
        v = html_lib.unescape(v).strip()
        am = _mes(v)
        if am:
            saida.append((v, am[0], am[1]))
        elif v:
            log(f"  São Luís: mês com nome desconhecido na lista: {v!r}")
    return saida


def _folha_do_mes(rotulo):
    """Linhas da folha de um mês, só com os campos usados (CPF, descontos e líquido são descartados aqui mesmo)."""
    linhas, inicio = [], 0
    while True:
        d = json.loads(_pedir("/data", params={"referencia": rotulo, "nome": "", "draw": 1, "start": inicio, "length": 5000}))
        lote = d.get("data") or []
        linhas += [{k: (x.get(k) or "") for k in CAMPOS} for x in lote]
        total = int(d.get("recordsFiltered") or d.get("recordsTotal") or 0)
        inicio += len(lote)
        if not lote or inicio >= total:
            return linhas


# ---------------------------------------------------------------- coleta
def _eh_gabinete(lot):
    n = normalizar_nome(lot)
    return bool(n.startswith("GAB") or re.search(r"\bVER\b\.?", n)) and n != "VEREADORES"


_CARGOS = [(r"^CHEFE", "Chefe de gabinete"), (r"^OFICIAL", "Oficial de gabinete"), (r"^MOTORISTA", "Motorista"),
           (r"^ASSIST(ENTE)? DE GAB", "Assistente de gabinete"), (r"^ASSISTENTE LEGIS", "Assistente legislativo"),
           (r"^ASS(ESSOR)? PAR(LAMENTAR)? ESP", "Assessor parlamentar especial"), (r"^ASS(ESSOR)? TEC(NICO)? ESP", "Assessor técnico especial"),
           (r"^ASS(ESSOR)? ESP(ECIAL)? LEG", "Assessor especial legislativo"), (r"^ASSESSOR ESPECIAL", "Assessor especial"),
           (r"^ASSESSOR PARLAMENTAR", "Assessor parlamentar"), (r"^SEC(RETARIO)? PARL", "Secretário parlamentar"),
           (r"^SEC(RETARIO)? LEGIS", "Secretário legislativo"), (r"^TEC", "Técnico legislativo")]


def _cargo(c):
    t = re.sub(r"\s+", " ", re.sub(r"[.]", " ", normalizar_nome(c))).strip()
    for padrao, nome in _CARGOS:
        if re.search(padrao, t):
            return nome
    t = re.sub(r"\s+[IVX]+$", "", t)
    return comum.titulo(t) if t else "Sem cargo informado"


def folha():
    """Bruto de cada vereador por mês; dos gabinetes, pessoas e custo bruto por mês e vínculo; cargos do último mês."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    PASTA.mkdir(parents=True, exist_ok=True)
    arq_v, arq_g, arq_c, arq_r = PASTA / "folha_vereadores.csv", PASTA / "folha_gabinetes.csv", PASTA / "cargos_gabinetes.csv", PASTA / "referencias.csv"
    fv = pd.read_csv(arq_v, dtype=str).fillna("") if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "referencia", "nome", "lotacao", "vinculo", "folha", "valor", "admissao", "exoneracao"])
    fg = pd.read_csv(arq_g, dtype={"lotacao": str, "vinculo": str}) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "referencia", "lotacao", "vinculo", "pessoas", "custo"])
    fr = pd.read_csv(arq_r, dtype={"referencia": str}) if arq_r.exists() else pd.DataFrame(columns=["referencia", "ano", "mes", "linhas"])
    feitos = set(fr.referencia)
    refs = [(r, a, m) for r, a, m in referencias() if INICIO <= a * 100 + min(m, 12) <= ate]
    if not refs:
        raise RuntimeError("a lista de meses do portal veio vazia")
    ultimo = None
    for rotulo, a, m in sorted(refs, key=lambda x: (x[1], x[2])):
        if rotulo in feitos and a * 100 + min(m, 12) <= recentes:
            continue
        linhas = _folha_do_mes(rotulo)
        if not linhas:
            continue
        # vereadores: o bruto de cada linha (folha mensal, rescisão, 13º...)
        v_linhas = [{"ano": a, "mes": m, "referencia": rotulo, "nome": re.sub(r"\s+", " ", x["nome"]).strip(), "lotacao": x["lotacao"].strip(),
                     "vinculo": x["vinculo"].strip(), "folha": x["tipo_folha"].strip(), "valor": _valor(x["valor"]),
                     "admissao": x["admissao"], "exoneracao": x["exoneracao"]}
                    for x in linhas if normalizar_nome(x["cargo_funcao"]) == "VEREADOR"]
        # gabinetes: pessoas (folha mensal, sem repetir) e custo bruto (todas as folhas), por vínculo
        gab, pessoas, cargos = {}, {}, {}
        for x in linhas:
            lot = re.sub(r"\s+", " ", x["lotacao"]).strip()
            if not _eh_gabinete(lot) or normalizar_nome(x["cargo_funcao"]) == "VEREADOR":
                continue
            k = (lot, x["vinculo"].strip())
            gab[k] = gab.get(k, 0.0) + _valor(x["valor"])
            if "MENSAL" in normalizar_nome(x["tipo_folha"]):
                quem = (normalizar_nome(x["nome"]), str(x["matricula"]))
                pessoas.setdefault(k, set()).add(quem)
                cargos.setdefault((lot, _cargo(x["cargo_funcao"])), set()).add(quem)
        g_linhas = [{"ano": a, "mes": m, "referencia": rotulo, "lotacao": k[0], "vinculo": k[1], "pessoas": len(pessoas.get(k, ())), "custo": round(c, 2)}
                    for k, c in sorted(gab.items())]
        fv = pd.concat([x for x in (fv[fv.referencia.astype(str) != rotulo], pd.DataFrame(v_linhas)) if len(x)], ignore_index=True)
        fg = pd.concat([x for x in (fg[fg.referencia.astype(str) != rotulo], pd.DataFrame(g_linhas)) if len(x)], ignore_index=True)
        fr = pd.concat([x for x in (fr[fr.referencia.astype(str) != rotulo], pd.DataFrame([{"referencia": rotulo, "ano": a, "mes": m, "linhas": len(linhas)}])) if len(x)],
                       ignore_index=True)
        if not (gravar_csv(fv, arq_v) and gravar_csv(fg, arq_g) and gravar_csv(fr, arq_r)):
            ultimo = None
            break  # recusado por perda de cobertura (util.gravar_com): fica o que estava, e a folha é lida de novo
        if m <= 12 and (ultimo is None or a * 100 + m >= ultimo[0] * 100 + ultimo[1]):
            ultimo = (a, m, cargos)
        log(f"  São Luís: folha de {rotulo} ({len(linhas)} linhas, {len(v_linhas)} de vereador, {len(g_linhas)} gabinete × vínculo)")
    if ultimo:
        a, m, cargos = ultimo
        gravar_csv(pd.DataFrame([{"ano": a, "mes": m, "lotacao": k[0], "cargo": k[1], "pessoas": len(q)} for k, q in sorted(cargos.items())]), arq_c)


def lista():
    """Nome parlamentar, nome civil, partido, foto e página de cada vereador da legislatura (a lista do site da Câmara)."""
    verificar_prazo()
    r = _sessao().get(LISTA, timeout=90)
    r.raise_for_status()
    linhas = []
    for bloco in re.findall(r'<a href="(https://www\.cmsaoluis\.ma\.gov\.br/vereadores/[a-z0-9\-]+)"[^>]*>\s*<img src="([^"]+)" alt="([^"]*)"'
                            r'.*?class="sigla-partido">([^<]*)<.*?class="panel-title[^"]*">([^<]*)<', r.text, re.S):
        pagina, foto, civil, partido, nome = (html_lib.unescape(x).strip() for x in bloco)
        linhas.append({"nome": " ".join(nome.split()), "nome_civil": " ".join(civil.split()), "partido": partido, "foto": foto,
                       "pagina": pagina})
    df = pd.DataFrame(linhas, columns=["nome", "nome_civil", "partido", "foto", "pagina"]).drop_duplicates("pagina")
    if not 25 <= len(df) <= 45:  # página quebrada: fica a lista gravada
        log(f"  São Luís: a lista do site da Câmara veio com {len(df)} vereadores; fica a que estava gravada")
        return
    gravar_csv(df, PASTA / "site_vereadores.csv")
    log(f"  São Luís: {len(df)} vereadores na lista do site da Câmara")


def coletar():
    folha()
    try:
        lista()
    except Exception as e:  # noqa: BLE001 — a foto e a página são complemento: a folha segue
        log(f"  São Luís: a lista do site da Câmara não abriu ({type(e).__name__}); ficam as fotos e páginas já gravadas")


# ---------------------------------------------------------------- montagem
def _codigo(nome, t):
    if t is not None:
        return int(t["sq"])
    return int(hashlib.md5(normalizar_nome(nome).encode()).hexdigest()[:10], 16)


def _sem_defeito(nome):
    """"ANTONIO JOSï¿½ LIMA GARCEZ" (acento estragado na fonte) -> "ANTONIO JOS LIMA GARCEZ", para comparar."""
    return re.sub(r"\s+", " ", re.sub(r"ï¿½|\ufffd", "", nome or "")).strip()


_COMUNS = {"FILHO", "FILHA", "NETO", "JUNIOR", "SOBRINHO", "SILVA", "SANTOS", "OLIVEIRA", "COSTA", "SOUZA", "SOUSA", "LIMA", "PEREIRA",
           "FERREIRA", "BARBOSA", "MELO", "MACEDO", "CASTRO", "PINTO", "RAIMUNDO", "ANTONIO", "COLETIVO", "UNIDOS", "GABINETE"}


def _achar(nome, pessoas):
    """Código da pessoa por um nome (de urna, completo ou do gabinete, às vezes abreviado ou com erro de digitação):
    igual, compatível ou bem parecido; senão, uma palavra rara que só o nome de urna de uma pessoa tem ("JHONATAN",
    "EVANGELISTA"). pessoas: {código: {"nomes": [...], "apelidos": [...]}}."""
    opcoes = [(n, cod) for cod, p in pessoas.items() for n in p["nomes"] + p["apelidos"] if n]
    k = comum.chave_nome(nome)
    for teste in (lambda n: comum.chave_nome(n) == k, lambda n: comum.compativel(k, n)):
        achados = {cod for n, cod in opcoes if teste(n)}
        if len(achados) == 1:
            return achados.pop()
        if achados:
            return None  # mais de uma pessoa: melhor não chutar
    c = comum.achar_parecido(nome, opcoes, 0.9)
    if c is not None:
        return c
    for w in (w for w in k.split() if len(w) >= 5 and w not in _COMUNS):
        achados = {cod for cod, p in pessoas.items() for n in p["apelidos"] for x in comum.chave_nome(n).split() if x == w}
        if len(achados) == 1:
            return achados.pop()
    return None


def _nome_gabinete(lot):
    """"GAB. CO-VER. JHONATAN- PELO COLETIVO NS", "GAB V NATO JUNIOR", "GOV VER ANTONIO MARCOS SILVA" -> nome do vereador."""
    t = re.sub(r"\s+", " ", normalizar_nome(lot).replace(".", " ")).strip()
    t = re.sub(r"^((GABINETE|GAB|GOV|VER|V|CO-VER|CO)\s+)+", "", t)
    return re.split(r"\s*-\s+|\s+-\s*|-\s*PELO\b", t)[0].strip()


def _categoria(folha):
    f = normalizar_nome(folha)
    if "13" in f:
        return "decimo_terceiro"
    if "MENSAL" in f:
        return "salario"
    return "outros_rendimentos"  # rescisão, folha complementar, férias


def montar(tipos):
    if not (PASTA / "folha_vereadores.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    fv = pd.read_csv(PASTA / "folha_vereadores.csv", dtype={"referencia": str, "admissao": str, "exoneracao": str}).fillna("")
    fg = pd.read_csv(PASTA / "folha_gabinetes.csv") if (PASTA / "folha_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "referencia", "lotacao", "vinculo", "pessoas", "custo"])
    fc = pd.read_csv(PASTA / "cargos_gabinetes.csv") if (PASTA / "cargos_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    tse = comum.candidatos_tse("MA", "São Luís")
    tse_civil = {normalizar_nome(n): r for n, r in zip(tse.nome, tse.to_dict("records"))}
    fv = fv.assign(mes12=fv.mes.clip(upper=12))
    dup = fv.groupby(["ano", "mes"]).referencia.nunique()
    if (dup > 1).any():
        log(f"  São Luís: mais de uma folha publicada para o mesmo mês (somadas): {', '.join(f'{m:02d}/{a}' for (a, m) in dup[dup > 1].index)}")

    # pessoas: cada nome da folha, ligado ao TSE pelo nome completo
    pessoas, cod_folha = {}, {}
    for nome in sorted(set(fv.nome), key=lambda n: ("ï¿½" in n or "\ufffd" in n, n)):  # os nomes com acento estragado por último
        limpo = _sem_defeito(nome)
        t = tse_civil.get(normalizar_nome(nome))
        if t is None:
            achados = [r for r in tse.to_dict("records") if comum.compativel(limpo, r["nome"]) or comum.compativel(r["nome"], limpo)]
            t = achados[0] if len(achados) == 1 else None
        if t is None:
            i = comum.achar_parecido(limpo, [(n, i) for i, n in enumerate(tse.nome)], 0.9)
            t = tse.iloc[i].to_dict() if i is not None else None
        if t is None:  # "MAGNOLIA DE JESUS LIMA DIAS" x "MAGNOLIA LIMA DIAS CARNEIRO": o primeiro nome e mais dois iguais
            palavras = set(comum.chave_nome(limpo).split()) - {"DE", "DA", "DO", "DOS", "DAS", "E"}
            achados = [r for r in tse.to_dict("records") if comum.chave_nome(r["nome"]).split()[:1] == comum.chave_nome(limpo).split()[:1]
                       and len(palavras & set(comum.chave_nome(r["nome"]).split())) >= 3]
            t = achados[0] if len(achados) == 1 else None
        if t is None:  # o mesmo nome já visto, sem o acento estragado
            c = comum.achar_parecido(limpo, [(p["civil"], c) for c, p in pessoas.items()], 0.9)
            if c is not None:
                cod_folha[nome] = c
                continue
        cod = _codigo(limpo, t)
        pessoas.setdefault(cod, {"civil": nome, "tse": t, "nomes": [nome] + ([t["nome"]] if t is not None else []),
                                 "apelidos": [t["nome_urna"]] if t is not None else []})
        if nome not in pessoas[cod]["nomes"]:
            pessoas[cod]["nomes"].append(nome)
        cod_folha[nome] = cod
    sem = sorted(p["civil"] for p in pessoas.values() if p["tse"] is None)
    if sem:
        log(f"  São Luís: na folha como vereador e sem correspondência no TSE: {', '.join(sem)}")
    fv = fv.assign(codigo=fv.nome.map(cod_folha))

    # no cargo: os meses em que recebeu como vereador (a rescisão só conta no mês da saída)
    def no_cargo(r):
        if r.valor <= 0 or r.mes > 12:
            return False
        if "MENSAL" in normalizar_nome(r.folha):
            return True
        saida = re.match(r"\d{2}/(\d{2})/(\d{4})", r.exoneracao or "")
        return bool(saida) and int(saida.group(2)) * 100 + int(saida.group(1)) == int(r.ano) * 100 + int(r.mes)
    no_mes = {}
    for r in fv.itertuples():
        if no_cargo(r):
            no_mes.setdefault(int(r.codigo), set()).add(int(r.ano) * 100 + int(r.mes))
    ultimo_folha = int((fv.ano * 100 + fv.mes12).max())
    ultimo = min(ate, ultimo_folha)
    ganha = pd.DataFrame([{"ano": int(r.ano), "mes": int(r.mes12), "codigo": int(r.codigo), "categoria": "decimo_terceiro" if r.mes > 12 else _categoria(r.folha), "valor": float(r.valor)}
                          for r in fv.itertuples() if r.valor], columns=["ano", "mes", "codigo", "categoria", "valor"])
    # a data de saída (exoneração) informada na folha fecha o último período, se cair no último mês pago
    saidas = {}
    for c, e in zip(fv.codigo, fv.exoneracao):
        d = re.match(r"(\d{2})/(\d{2})/(\d{4})$", str(e).strip())
        if d:
            iso = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"
            saidas[int(c)] = max(saidas.get(int(c), ""), iso)
    linhas_m = []
    for c, ms in no_mes.items():
        periodos = comum.periodos_de_meses({am for am in ms if am <= ultimo}, ultimo)
        if not periodos:
            continue
        de, fim = periodos[-1]
        s = saidas.get(c, "")
        if not fim and s and int(s[:4]) * 100 + int(s[5:7]) == max(ms):
            periodos[-1] = (de, s)
        linhas_m += [{"codigo": c, "inicio": de, "fim": fim} for de, fim in periodos]
    mandatos = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])

    linhas_v = []
    for c, p in pessoas.items():
        t = p["tse"]
        linhas_v.append({"codigo": c, "nome": comum.titulo(t["nome_urna"]) if t is not None else comum.titulo(_sem_defeito(p["civil"])),
                         "nome_civil": comum.titulo(t["nome"] if t is not None else _sem_defeito(p["civil"])), "partido": _partido(t["partido"]) if t is not None else "",
                         "genero": t["genero"] if t is not None else "", "eleito": t["situacao"] if t is not None else "", "pagina": CFG["pagina"]})
    ver = pd.DataFrame(linhas_v)
    ver = _do_site(ver, pessoas)

    # gabinetes: o nome da lotação -> vereador; só nos meses em que ele estava no cargo (quando o titular se licencia,
    # o gabinete continua com o nome dele e não se sabe qual suplente o ocupa)
    lot_cod = {l: (None if "PRESIDENCIA" in normalizar_nome(l) else _achar(_nome_gabinete(l), pessoas)) for l in set(fg.lotacao) | set(fc.lotacao)}
    sem_g = sorted(l for l, c in lot_cod.items() if c is None)
    if sem_g:
        log(f"  São Luís: gabinetes sem vereador (não contados): {', '.join(sem_g)}")
    eq = fg.assign(codigo=fg.lotacao.map(lot_cod), pessoas=fg.pessoas.where(fg.mes <= 12, 0), mes=fg.mes.clip(upper=12))  # 13º: só o custo
    eq = eq[eq.codigo.notna()]
    fora = eq[[int(a) * 100 + int(m) not in no_mes.get(int(c), set()) for a, m, c in zip(eq.ano, eq.mes, eq.codigo)]]
    if len(fora):
        nomes_v = dict(zip(ver.codigo, ver.nome))
        quem = sorted({f"{nomes_v.get(int(c))} {int(m):02d}/{int(a)}" for a, m, c in zip(fora.ano, fora.mes, fora.codigo)})
        log(f"  São Luís: gabinetes em meses sem o titular no cargo, não contados (R$ {fora.custo.sum():,.2f}): {', '.join(quem)}")
    eq = eq.drop(fora.index)
    equipe = eq.groupby(["ano", "mes", "codigo"])[["pessoas", "custo"]].sum().reset_index().astype({"codigo": int})
    cargos = fc.assign(codigo=fc.lotacao.map(lot_cod))
    cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})
    ultimo_eq = f"{int(fc.mes.iloc[0]):02d}/{int(fc.ano.iloc[0])}" if len(fc) else ""

    sub = _subsidio(fv)
    cfg = dict(CFG, ultimo_mes=ultimo, equipe_em=ultimo_eq, subsidio=sub, salario_nota=_salario_nota(fv, sub),
               notas=["A verba indenizatória de exercício parlamentar (VIEP) fica de fora: o site da Câmara só publica relatórios "
                      "de empenho do ano, sem o valor de cada mês por vereador.",
                      "Quem estava no cargo em cada mês vem da folha de pagamento: os vereadores pagos naquele mês (titulares e suplentes que assumiram)."])
    return comum.montar(cfg, tipos, ver, mandatos, ganha=ganha, equipe=equipe, cargos=cargos)


def _do_site(ver, pessoas):
    """Página, foto e partido de hoje de cada vereador pela lista do site da Câmara (nome civil ou parlamentar)."""
    arq = PASTA / "site_vereadores.csv"
    if not arq.exists() or not len(ver):
        return ver
    site = pd.read_csv(arq).fillna("")
    fotos, ver = [], ver.copy()
    for r in site.itertuples():
        c = _achar(r.nome_civil, pessoas) or _achar(r.nome, pessoas)
        if c is None or c not in set(ver.codigo):
            log(f"  São Luís: na lista do site da Câmara e não na folha: {r.nome}")
            continue
        i = ver.index[ver.codigo == c][0]
        ver.at[i, "pagina"] = r.pagina
        if r.partido:
            ver.at[i, "partido"] = _partido(r.partido)
        if r.foto:
            fotos.append((int(c), r.foto))
    comum.fotos(COD, fotos)
    return ver


def _partido(p):
    """"PC do B" (TSE) -> "PCdoB", como nas outras cidades."""
    return "PCdoB" if normalizar_nome(p).replace(" ", "") == "PCDOB" else p


def _subsidio(fv):
    """Subsídio de cada mês: o valor mais comum da folha mensal dos vereadores, só quando muda."""
    m = fv[fv.folha.map(normalizar_nome).str.contains("MENSAL") & (fv.mes <= 12)]
    saida = []
    for (a, mes), g in m.groupby(["ano", "mes"]):
        v = round(float(g.valor.round(2).mode().iloc[0]), 2)
        if not saida or abs(saida[-1][1] - v) > 0.5:
            saida.append([int(a) * 100 + int(mes), v])
    return saida


def _salario_nota(fv, sub):
    valor = f" de {_br(sub[-1][1])} por mês" if sub else ""
    dobro = ""
    if sub:
        m = fv[fv.folha.map(normalizar_nome).str.contains("MENSAL") & (fv.mes <= 12)]
        if (m.valor.round(2) == round(sub[-1][1] * 2, 2)).any():
            dobro = "; o presidente da Câmara recebe o dobro"
    tem_13 = fv.folha.map(normalizar_nome).str.contains("13").any() or (fv.mes > 12).any()
    return (f"Valores brutos da folha de pagamento da Câmara. O subsídio é{valor}{dobro}. Nos meses de entrada e de saída, a folha paga só os dias no cargo."
            + ("" if tem_13 else " A folha publicada no portal não traz o 13º nem as férias dos vereadores."))


def _br(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
