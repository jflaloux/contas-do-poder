"""Assembleia Legislativa do Rio Grande do Sul (ALRS): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da ALRS, transparencia.al.rs.gov.br; só abre de dentro do Brasil, então este robô roda no Mac):
- Cotas ("Gastos | Cotas"): o que a página /parlamentares/gastos usa: a lista de gabinetes de cada mês
  (/ajax-gastosParlamentaresListarGabinete) e a página de cada gabinete e mês (/parlamentares/gastos/pesquisa), com as
  despesas por rubrica (sem fornecedor).
- Folha: a consulta "Remuneração de Servidores e Parlamentares" (/pessoal/remuneracao-servidores-parlamentares): a busca
  pelo nome completo dá o número funcional e /ajax-remuneracaoModal, os valores do mês (remuneração bruta, parcelas
  indenizatórias, abono, terço de férias, 13º). Descontos e líquido não são guardados.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os meses na folha como deputado (o titular licenciado sai da folha, mas o gabinete continua na lista de
cotas); para quem a busca da folha não acha, os meses com gabinete na lista. Quem está no cargo hoje: a lista de deputados
do site da ALRS (https://ww4.al.rs.gov.br/deputados, que lê LISTA): o suplente pode estar na folha do mês em que o titular
voltou.
"""
import html as H
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "RS"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://transparencia.al.rs.gov.br"
PASTA = DADOS / "assembleias" / "rs"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Rio Grande do Sul", "uf": UF, "casa": "Assembleia Legislativa do Rio Grande do Sul", "vagas": 55, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da ALRS (remuneração bruta, parcelas indenizatórias como vale-refeição e auxílio-saúde, terço de "
                     "férias e 13º), sem descontos."),
    "verba_nome": "Cota para o exercício da atividade parlamentar",
    "verba_regra": "Valor mensal por gabinete para despesas do mandato (Resoluções de Mesa 419/2001, 784/2007 e 1.352/2015); o saldo passa para o mês seguinte.",
    "verba_notas": ["A ALRS publica as despesas da cota por gabinete, mês e rubrica, sem fornecedor nem CNPJ.",
                    "A cota fica no gabinete do titular: quando ele se licencia (para ser secretário, por exemplo), as despesas do mês "
                    "continuam no nome do gabinete dele, e o suplente que assume aparece sem cota."],
    "pagina": "https://ww4.al.rs.gov.br/deputados",
    "notas": ["Quem está no cargo: os meses na folha como deputado; para quem a busca da folha não acha pelo nome, os meses com "
              "gabinete na lista de cotas. Sem folha, o salário é o subsídio da lei. Quem está no cargo hoje: a lista de deputados "
              "do site da ALRS.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": f"{SITE}/parlamentares/gastos", "folha": f"{SITE}/pessoal/remuneracao-servidores-parlamentares"},
}


def _pedir(metodo, caminho, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, SITE + caminho, timeout=90, **kw)
            r.raise_for_status()
            dormir(1)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _nome_gabinete(t):
    return re.sub(r"\s+\d{2}$", "", re.sub(r"^Gabinete\s+(?:da\s+|do\s+)?Dep(?:utad[oa])?\.?\s*", "", " ".join(t.split()), flags=re.I)).strip()


ITEM = re.compile(r"([A-Za-zÀ-ú][^:]*?):\s*-\s*R\$\s*([\d.]+,\d{2})\s*-\s*R\$\s*[\d.]+,\d{2}")


def _gastos(t):
    texto = " ".join(H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())
    i, f = texto.find("4- Despesas do Mês"), texto.find("5- Outros Créditos")
    if i < 0:
        return None
    seg = texto[i:f if f > i else None]
    j = seg.find(" Total ")
    seg = seg[j + 7:] if j >= 0 else seg
    return [(r.strip(), num(v)) for r, v in ITEM.findall(seg) if r.strip() != "Total"]


def _tse(nome, tse):
    """Candidato de 2022 pelo nome parlamentar; o site tira o apóstrofo ("Kaká dÁvila" é "KAKÁ D'ÁVILA" no TSE)."""
    return comum.achar(nome, tse) or comum.achar(re.sub(r"\b([dD])([AÁEÉIÍOÓUÚ])", r"\1 \2", nome), tse) or {}


LISTA = "https://ww4.al.rs.gov.br:5000/listarDestaqueDeputados"  # o que a página https://ww4.al.rs.gov.br/deputados usa


def _em_exercicio():
    """Nomes da lista de deputados do site da ALRS (quem está em exercício hoje)."""
    verificar_prazo()
    d = _sessao().get(LISTA, timeout=60).json()
    lista = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
    return [x.get("nomeDeputado", "") for x in lista]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # de fora do Brasil o portal não responde: desiste logo (o site usa o que já está gravado)
        _sessao().get(SITE + "/ajax-gastosParlamentaresListarMes?ano=2025", timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  ALRS: o portal não abriu ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
        return
    try:
        comum.gravar_em_exercicio(PASTA, _em_exercicio(), CFG["vagas"], "https://ww4.al.rs.gov.br/deputados")
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — sem a lista, fica a que já estava gravada
        log(f"  ALRS: a lista de deputados não abriu ({type(e).__name__}); fica a já gravada")
    meses = _meses()
    arq_g, arq_v, arq_f, arq_id = PASTA / "gabinetes.csv", PASTA / "cota_rubricas.csv", PASTA / "folha_deputados.csv", PASTA / "funcionais.csv"
    gab = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "codigo", "nome"])
    cot = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "codigo", "rubrica", "valor"])
    fol = pd.read_csv(arq_f, dtype={"id_funcional": str}) if arq_f.exists() else pd.DataFrame(columns=["ano", "mes", "id_funcional"])
    ids = pd.read_csv(arq_id, dtype={"id_funcional": str}).fillna("") if arq_id.exists() else pd.DataFrame(columns=["nome", "nome_busca", "id_funcional", "cargo"])
    ids["id_funcional"] = ids.id_funcional.astype(str).str.replace(r"\.0$", "", regex=True)
    # os dois últimos meses são pedidos de novo, mas só uma vez por dia (a coleta em partes não repete o que acabou de pedir)
    velho = lambda arq: not arq.exists() or time.time() - arq.stat().st_mtime > 86400
    rev_g, rev_v, rev_f = velho(arq_g), velho(arq_v), velho(arq_f)
    if True:
        # 1. gabinetes de cada mês
        feitos = set(zip(gab.ano, gab.mes))
        for am in meses:
            if (am // 100, am % 100) in feitos and (am < meses[-2] or not rev_g):
                continue
            lista = _pedir("GET", f"/ajax-gastosParlamentaresListarGabinete?ano={am // 100}&mes={am % 100}").json().get("lista") or []
            novos = [{"ano": am // 100, "mes": am % 100, "codigo": int(x["codProponente"]), "nome": _nome_gabinete(x["nomeCota"])}
                     for x in lista if re.match(r"Gabinete\s+(da\s+|do\s+)?Dep", x["nomeCota"], flags=re.I)]
            if novos:
                gab = pd.concat([gab[~((gab.ano == am // 100) & (gab.mes == am % 100))], pd.DataFrame(novos)])
        gab.sort_values(["ano", "mes", "nome"]).to_csv(arq_g, index=False)
        # 2. cota de cada gabinete e mês
        feitos = set(zip(cot.ano, cot.mes, cot.codigo))
        pedir = [(int(a), int(m), int(c)) for a, m, c in zip(gab.ano, gab.mes, gab.codigo)
                 if (a, m, c) not in feitos or (a * 100 + m >= meses[-2] and rev_v)]

        def cota(item):
            a, m, c = item
            linhas = _gastos(_pedir("GET", "/parlamentares/gastos/pesquisa", params={"ano": a, "mes": m, "solicitante": c}).text)
            if linhas is None:  # página sem o quadro de despesas: guarda o mês vazio para não pedir de novo
                return [{"ano": a, "mes": m, "codigo": c, "rubrica": "", "valor": 0.0}]
            return [{"ano": a, "mes": m, "codigo": c, "rubrica": r, "valor": v} for r, v in linhas] or [{"ano": a, "mes": m, "codigo": c, "rubrica": "", "valor": 0.0}]
        res = []
        try:
            with ThreadPoolExecutor(SIMULTANEOS) as ex:
                for r in ex.map(cota, pedir):
                    res.append(r)
        finally:
            novos = pd.DataFrame([x for r in res for x in r])
            if len(novos):
                chave = set(zip(novos.ano, novos.mes, novos.codigo))
                cot = pd.concat([cot[[k not in chave for k in zip(cot.ano, cot.mes, cot.codigo)]], novos])
                cot.sort_values(["ano", "mes", "codigo", "rubrica"]).to_csv(arq_v, index=False)
            log(f"  ALRS: cotas de {len(res)} de {len(pedir)} gabinetes e meses pedidas agora")
        # 3. número funcional de cada deputado (busca pelo nome completo do TSE) e a folha de cada mês
        tse = comum.tse_2022(UF)
        nomes = sorted(set(gab.nome))
        # eleitos que nunca aparecem na lista de cotas (em 2025-2026, dez deputados, vários deles secretários de Estado em
        # parte do período): procurados na folha pelo nome do TSE, em todos os meses
        achados_tse = {(_tse(n, tse) or {}).get("sq") for n in nomes}
        extras = {vc.titulo(v["urna"]): v for v in tse.values() if v["eleito"] == "eleito" and v["sq"] not in achados_tse}
        nomes += sorted(extras)
        conhecidos = set(ids[ids.id_funcional.astype(str) != ""].nome)
        meses_de_gab = {n: sorted(set(g.ano * 100 + g.mes)) for n, g in gab.groupby("nome")}
        try:
            for n in nomes:
                if n in conhecidos:
                    continue
                ids = ids[ids.nome != n]
                t = extras.get(n) or _tse(n, tse)
                escolhido, cargo, busca = "", "", ""
                # a busca pede o nome completo exato, sem acento ("ADAO PRETTO FILHO"), num mês em que a pessoa está na folha
                ms = [m for m in meses_de_gab.get(n, []) if m <= meses[-2]] or [meses[-2]]
                tentar_meses = list(dict.fromkeys([ms[-1], ms[0], ms[len(ms) // 2]]))
                sem_titulo = " ".join(w for w in re.sub(r"[^A-Z ]", " ", normalizar_nome(n)).split() if w not in ("PROF", "PROFESSOR", "PROFESSORA", "DR", "DRA", "DELEGADO", "DELEGADA", "CAPITAO"))
                for busca, ult in ((b, m) for m in tentar_meses for b in dict.fromkeys([normalizar_nome(t.get("nome") or ""), normalizar_nome(n), sem_titulo]) if b):
                    r = _pedir("GET", "/pessoal/remuneracao-servidores-parlamentares/pesquisa",
                               params={"ano": ult // 100, "mes": ult % 100, "status": "ativo", "nome": busca})
                    achados = re.findall(r'data-idfuncional="(\d+)"', r.text)
                    for idf in achados[:5]:
                        j = _pedir("POST", "/ajax-remuneracaoModal", data={"idFuncional": idf, "ano": ult // 100, "mes": ult % 100, "situacao": "ativo"}).json()
                        s_ = ((j.get("servidores") or [{}])[0] if isinstance(j, dict) else {}) or {}
                        if "DEPUTAD" in normalizar_nome(s_.get("cargoFuncao", "")):
                            escolhido, cargo = idf, s_.get("cargoFuncao", "")
                            break
                    if escolhido:
                        break
                ids = pd.concat([ids, pd.DataFrame([{"nome": n, "nome_busca": busca, "id_funcional": escolhido, "cargo": cargo}])])
        finally:
            ids.to_csv(arq_id, index=False)
        feitos = set(zip(fol.ano, fol.mes, fol.id_funcional.astype(str)))
        quem = [(n, str(i)) for n, i in zip(ids.nome, ids.id_funcional) if str(i)]
        meses_de = {n: sorted(set(g.ano * 100 + g.mes)) for n, g in gab.groupby("nome")}
        for n in extras:
            meses_de[n] = [m for m in meses if m <= meses[-2]]
        pedir = [(am, n, i) for n, i in quem for am in meses_de.get(n, []) if (am // 100, am % 100, i) not in feitos or (am >= meses[-2] and rev_f)]

        def folha(item):
            am, n, i = item
            j = _pedir("POST", "/ajax-remuneracaoModal", data={"idFuncional": i, "ano": am // 100, "mes": am % 100, "situacao": "ativo"}).json()
            s = (j.get("servidores") or [None])[0] if isinstance(j, dict) else None
            if not s:
                return None
            v = lambda k: num((s.get(k) or "0").replace("R$", "").replace("-", "").strip() or "0")
            return {"ano": am // 100, "mes": am % 100, "id_funcional": i, "nome": n, "cargo": s.get("cargoFuncao", ""),
                    "bruta": v("remuneracaoTotalBruta"), "indenizatorias": v("parcelasIndenizatorias"), "abono": v("abonoPermanencia"),
                    "ferias": v("tercoFerias"), "decimo": v("gratificacaoNatalina")}
        res = []
        try:
            with ThreadPoolExecutor(SIMULTANEOS) as ex:
                for r in ex.map(folha, pedir):
                    res.append(r)
        finally:
            novos = pd.DataFrame([r for r in res if r])
            if len(novos):
                chave = set(zip(novos.ano, novos.mes, novos.id_funcional.astype(str)))
                fol = pd.concat([fol[[k not in chave for k in zip(fol.ano, fol.mes, fol.id_funcional.astype(str))]], novos])
                fol.sort_values(["ano", "mes", "nome"]).to_csv(arq_f, index=False)
            log(f"  ALRS: folha de {len(res)} de {len(pedir)} deputados e meses pedida agora")


_TIPOS = [(r"VE[IÍ]CULO PARTICULAR", "Uso de carro próprio (indenização)"), (r"LOCA[CÇ][AÃ]O DE VE[IÍ]C|VE[IÍ]CULO", "Aluguel de carros"),
          (r"COMBUST", "Combustível"), (r"TELEF", "Telefone e internet"), (r"IMPRESS|GR[AÁ]FIC", "Material gráfico (arte e impressão)"),
          (r"EXPEDIENTE|MATERIA", "Material de escritório"), (r"CORREIO|POSTA", "Correios"), (r"DI[AÁ]RIA|HOSPEDA", "Hospedagem e diárias"),
          (r"PASSAGE|A[EÉ]RE", "Passagens"), (r"DIVULGA|PUBLICIDADE|M[IÍ]DIA", "Divulgação do mandato")]


def _tipo(rubrica):
    u = normalizar_nome(rubrica)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(rubrica)


def montar(tipos):
    arq_g = PASTA / "gabinetes.csv"
    if not arq_g.exists():
        return None
    gab = pd.read_csv(arq_g)
    cot = pd.read_csv(PASTA / "cota_rubricas.csv").fillna({"rubrica": ""}) if (PASTA / "cota_rubricas.csv").exists() else pd.DataFrame(columns=["ano", "mes", "codigo", "rubrica", "valor"])
    fol = pd.read_csv(PASTA / "folha_deputados.csv", dtype={"id_funcional": str}) if (PASTA / "folha_deputados.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome"])
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    gab["am"] = gab.ano * 100 + gab.mes
    fol = fol[fol.cargo.fillna("").map(normalizar_nome).str.contains("DEPUTAD")] if len(fol) else fol
    fol_meses = {n: sorted(set(g.ano * 100 + g.mes)) for n, g in fol.groupby("nome")} if len(fol) else {}
    # o mês a mês vai até o último mês com folha publicada (a lista de gabinetes e a cota saem antes)
    ultimo_dado = int((fol.ano * 100 + fol.mes).max()) if len(fol) else int(gab.am.max())
    gab = gab[gab.am <= ultimo_dado]
    ver, mandatos, cod_nome, cod_gab = [], [], {}, {}
    for nome in sorted(set(gab.nome) | set(fol_meses)):  # também quem está na folha e nunca aparece na lista de cotas
        g = gab[gab.nome == nome]
        if not len(g) and not [m for m in fol_meses.get(nome, []) if m <= ultimo_dado]:
            continue
        t = _tse(nome, tse)
        codigo = comum.codigo_de(nome, t)
        cod_nome[nome] = codigo
        for c in g.codigo.unique():
            cod_gab[int(c)] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome") or nome),
                    "partido": partidos.get(normalizar_nome(t.get("nome") or ""), ""),
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        # no cargo: os meses na folha como deputado (o titular licenciado sai da folha, mas o gabinete continua na lista
        # de cotas); quem não aparece na busca da folha fica com os meses da lista de gabinetes
        meses_g = [m for m in fol_meses.get(nome, []) if m <= ultimo_dado] or sorted(set(g.am))
        per = comum.periodos(meses_g, ultimo_dado, ultimo, folga=1)
        fim = max(meses_g)
        if fim < ultimo_dado:
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    lista, atual = comum.ler_em_exercicio(PASTA), None  # quem está no cargo hoje; a folha diz desde quando
    if lista:
        atual = comum.casar_em_exercicio(lista, ver, UF)
        mandatos = comum.aplicar_hoje(mandatos, atual, ultimo_dado, folga=1)
    ganha = []
    for r in fol.itertuples():
        c = cod_nome.get(r.nome)
        if c is None or "DEPUTAD" not in normalizar_nome(r.cargo):
            continue
        for cat, v in (("salario", r.bruta), ("auxilios", r.indenizatorias), ("outros_rendimentos", r.abono + r.ferias), ("decimo_terceiro", r.decimo)):
            if abs(v) >= 0.005:
                ganha.append({"ano": r.ano, "mes": r.mes, "codigo": c, "categoria": cat, "valor": round(v, 2)})
    d = cot[(cot.rubrica != "") & (cot.valor.abs() >= 0.005)]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.codigo.map(cod_gab), "tipo": d.rubrica.map(_tipo), "fornecedor": "",
                         "cnpj_cpf": "", "valor": d.valor}).dropna(subset=["codigo"])
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), fora_hoje=comum.fora_hoje(atual))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]), despesas=desp)
