"""Assembleia Legislativa de Mato Grosso (ALMT): deputado estadual por deputado estadual.

Fonte: Portal da Transparência da ALMT (https://almt.eloweb.net/portaltransparencia/1/servidores, sistema da Elotech;
o link "Informações Posteriores à Julho 2022" de https://www.al.mt.gov.br/transparencia/). O robô lê o que a página usa
(https://almt.eloweb.net/portaltransparencia-api/api/, sem cadastro; abre também de fora do Brasil):
- Deputados: a lista de servidores de cada ano com o cargo "DEPUTADO ESTADUAL" (servidores?cargo=DEPUTADO): matrícula,
  nome, lotação (o gabinete), admissão e exoneração. Cada suplente que assume ganha uma matrícula nova por período.
- Folha: os dados financeiros de cada matrícula (servidores/<matrícula>) e os proventos de cada mês e folha
  (servidores/vencimentos-descontos?tipoEvento=P): subsídio, auxílio saúde, 13º e outros. Descontos e líquido não são
  lidos nem guardados.
- Equipe: os servidores de cada ano lotados nos gabinetes ("GAB DEP ...") e os vencimentos de cada um no mês; só o
  número de pessoas e a soma por gabinete e mês são guardados (sem nomes).
- Subsídio: Lei 12.011/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
A verba indenizatória não é publicada por deputado (só as leis e resoluções em https://www.al.mt.gov.br/parlamento/verba-indenizatoria).
Quem está no cargo: as datas de admissão e exoneração de cada matrícula de deputado; o titular que se licencia sem
receber o subsídio (quando o suplente assume) fica fora nos meses sem subsídio na folha.
"""
import json
import re
import time
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "MT"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
API = "https://almt.eloweb.net/portaltransparencia-api/api"
PORTAL = "https://almt.eloweb.net/portaltransparencia/1/servidores"
PASTA = DADOS / "assembleias" / "mt"
C = CACHE / "assembleias" / "mt"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Mato Grosso", "uf": UF, "casa": "Assembleia Legislativa de Mato Grosso", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da ALMT (proventos: subsídio, auxílio saúde, 13º e outros), sem descontos. Os suplentes "
                     "recebem pelos dias no cargo."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Ressarcimento de despesas do mandato (Lei 9.493/2010 e Resolução 3.569/2013).",
    "verba_notas": ["A ALMT não publica a verba indenizatória por deputado: os valores ficam de fora."],
    "equipe_nota": ("Equipe: servidores lotados no gabinete do deputado (\"GAB DEP ...\") e a soma dos vencimentos deles no mês, antes "
                    "dos descontos. A lotação é a que a lista de servidores do ano mostra; quem trabalha para o deputado lotado em "
                    "outro setor (Mesa, lideranças) fica de fora."),
    "pagina": "https://www.al.mt.gov.br/parlamento/deputados",
    "notas": ["Quem está no cargo: as datas de admissão e exoneração de cada deputado na lista de servidores da ALMT. O titular "
              "licenciado sem subsídio fica fora nos meses em que o suplente assume.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": PORTAL, "equipe": PORTAL,
               "subsidio": "https://www.al.mt.gov.br/norma-juridica/urn:lex:br;mato.grosso:estadual:lei.ordinaria:2023-01-13;12011"},
}
COLS_DEP = ["ano", "matricula", "nome", "lotacao", "situacao", "admissao", "demissao"]
COLS_FOLHA = ["ano", "mes", "matricula", "nome", "tipo_folha", "folha", "rubrica", "valor"]


def _get(caminho, ano, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{API}/{caminho}", params=params, timeout=120,
                              headers={"entidade": "1", "exercicio": str(ano), "Accept": "application/json"})
            r.raise_for_status()
            dormir(0.3)
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(10)


def _lista(ano, **filtro):
    """Lista de servidores do ano (todas as páginas)."""
    saida, pagina = [], 0
    while True:
        d = _get("servidores", ano, dict({"entidade": 1, "exercicio": ano, "page": pagina, "size": 500}, **filtro))
        saida += d.get("content") or []
        if d.get("last", True):
            return saida
        pagina += 1


def _financeiro(mat, ano):
    """Dados financeiros de uma matrícula no ano: [(ano, mes, tipo_folha, folha, vencimentos)] (os descontos não são guardados)."""
    d = _get(f"servidores/{mat}", ano)
    return [(int(x["anoCompetencia"]), int(x["mesCompetencia"]), int(x.get("tipoFolha") or 0), (x.get("descricaoTipoFolha") or "").strip(),
             float(x.get("vencimentos") or 0)) for x in (d.get("dadosFinanceiros") or []) if x.get("anoCompetencia")]


def _proventos(mat, ano, mes, tipo):
    d = _get("servidores/vencimentos-descontos", ano, {"matricula": mat, "anoCompetencia": ano, "mesCompetencia": mes, "tipoEvento": "P",
                                                        "tipoFolha": tipo, "codigoCalculo": "", "entidadeOrigem": 1})
    return [((x.get("descricao") or "").strip(), float(x.get("valor") or 0)) for x in (d or [])]


def _anos():
    return list(range(INICIO // 100, int(time.strftime("%Y")) + 1))


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    (C / "equipe").mkdir(parents=True, exist_ok=True)
    try:
        _get("configuracoes-gerais", _anos()[-1])
    except Exception as e:  # noqa: BLE001
        log(f"  ALMT: o portal não abriu ({type(e).__name__}); fica o que já estava gravado")
        return
    hoje = time.localtime()
    recente = vc.menos_meses(hoje.tm_year * 100 + hoje.tm_mon, 3)  # meses que ainda podem mudar: lidos de novo
    # 1. deputados de cada ano
    arq_d, arq_f = PASTA / "deputados.csv", PASTA / "folha_deputados.csv"
    deps = pd.read_csv(arq_d, dtype=str).fillna("") if arq_d.exists() else pd.DataFrame(columns=COLS_DEP)
    for ano in _anos():
        if ano < hoje.tm_year and str(ano) in set(deps.ano):
            continue  # ano fechado e já lido
        novos = [{"ano": str(ano), "matricula": str(x["matricula"]), "nome": " ".join((x.get("nome") or "").split()),
                  "lotacao": " ".join((x.get("descricaoLotacao") or "").split()), "situacao": x.get("situacao") or "",
                  "admissao": x.get("dataAdmissao") or "", "demissao": x.get("dataDemissao") or ""}
                 for x in _lista(ano, cargo="DEPUTADO") if "DEPUTADO" in normalizar_nome(x.get("descricaoCargo") or "")]
        if len(novos) >= 20:
            deps = pd.concat([deps[deps.ano != str(ano)], pd.DataFrame(novos)])
    gravar_csv(deps.sort_values(["ano", "nome", "matricula"]), arq_d)
    # 2. folha de cada deputado: dados financeiros do ano e proventos de cada mês e folha
    fol = pd.read_csv(arq_f, dtype={"matricula": str}) if arq_f.exists() else pd.DataFrame(columns=COLS_FOLHA)
    feitos = {(int(a), int(m), str(x), int(t)) for a, m, x, t in zip(fol.ano, fol.mes, fol.matricula, fol.tipo_folha)}
    lidos = {(str(x), int(a)) for x, a in zip(fol.matricula, fol.ano)}
    # o que já foi lido só é pedido de novo no ano corrente, e no máximo uma vez por dia
    rev = not arq_f.exists() or time.time() - arq_f.stat().st_mtime > 86400
    pedidos = [(r.matricula, r.nome, int(r.ano)) for r in deps.itertuples()
               if (r.matricula, int(r.ano)) not in lidos or (rev and int(r.ano) >= hoje.tm_year)]

    def um(item):
        mat, nome, ano = item
        linhas = []
        for a, m, tipo, folha, venc in _financeiro(mat, ano):
            am = a * 100 + m
            if am < INICIO or venc <= 0 or ((a, m, mat, tipo) in feitos and (am < recente or not rev)):
                continue
            itens = _proventos(mat, a, m, tipo)
            soma = sum(v for _, v in itens)
            for rub, v in itens:
                linhas.append({"ano": a, "mes": m, "matricula": mat, "nome": nome, "tipo_folha": tipo, "folha": folha, "rubrica": rub, "valor": v})
            if abs(venc - soma) >= 0.01:  # o que o detalhe não explica fica numa linha à parte
                linhas.append({"ano": a, "mes": m, "matricula": mat, "nome": nome, "tipo_folha": tipo, "folha": folha,
                               "rubrica": "OUTROS PROVENTOS (SEM DETALHE)", "valor": round(venc - soma, 2)})
        return linhas
    res, estado = [], {"fol": fol, "gravados": 0}

    def gravar():  # grava a cada 10 matrículas (e no fim), para a próxima rodada continuar de onde parou
        novos = pd.DataFrame(res[estado["gravados"]:])
        if not len(novos):
            return
        f = estado["fol"]
        chave = set(zip(novos.ano, novos.mes, novos.matricula.astype(str), novos.tipo_folha))
        f = pd.concat([f[[k not in chave for k in zip(f.ano, f.mes, f.matricula.astype(str), f.tipo_folha)]], novos])
        gravar_csv(f.sort_values(["ano", "mes", "nome", "matricula", "tipo_folha", "rubrica"]), arq_f)
        estado.update(fol=f, gravados=len(res))
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for i, r in enumerate(ex.map(um, pedidos)):
                res.extend(r)
                if i % 10 == 9:
                    gravar()
    finally:
        gravar()
        log(f"  ALMT: {deps.matricula.nunique()} matrículas de deputado; folha, {len(res)} linhas novas")
    _coletar_equipe(hoje, recente)


def _gabinete(lot):
    return normalizar_nome(lot).startswith("GAB DEP ")


def _coletar_equipe(hoje, recente):
    """Servidores lotados nos gabinetes: vencimentos de cada um por mês (cache sem nomes) -> equipe.csv e equipe_cargos.csv."""
    lotados = []
    for ano in _anos():
        arq = C / f"lotados_{ano}.json"
        if arq.exists() and (ano < hoje.tm_year or time.time() - arq.stat().st_mtime < 20 * 86400):
            lista = json.loads(arq.read_text(encoding="utf-8"))
        else:
            lista = [{"matricula": str(x["matricula"]), "lotacao": " ".join((x.get("descricaoLotacao") or "").split()),
                      "cargo": " ".join((x.get("descricaoCargo") or "").split()), "situacao": x.get("situacao") or "",
                      "admissao": x.get("dataAdmissao") or "", "demissao": x.get("dataDemissao") or ""}
                     for x in _lista(ano, lotacao="GAB DEP") if _gabinete(x.get("descricaoLotacao") or "")
                     and "DEPUTADO" not in normalizar_nome(x.get("descricaoCargo") or "")]
            arq.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
        lotados += [dict(x, ano=ano) for x in lista]
    # vencimentos de cada servidor no ano (só matrícula, mês e valor; sem nome)
    def precisa(x):
        arq = C / "equipe" / f"{x['ano']}_{x['matricula']}.json"
        if not arq.exists():
            return True
        if x["ano"] < hoje.tm_year:
            return False
        dem = x["demissao"][:7].replace("-", "")
        if dem and int(dem) < recente:
            return False  # saiu há mais de 3 meses: não muda mais
        return time.time() - arq.stat().st_mtime > 20 * 86400

    fila = [x for x in lotados if precisa(x)]

    def um(x):
        fin = _financeiro(x["matricula"], x["ano"])
        (C / "equipe" / f"{x['ano']}_{x['matricula']}.json").write_text(json.dumps(fin), encoding="utf-8")
    feitos = 0
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for _ in ex.map(um, fila):
                feitos += 1
    finally:
        log(f"  ALMT: equipe, {feitos} de {len(fila)} servidores de gabinete lidos agora ({len(lotados)} no total)")
        linhas = {}
        for x in lotados:
            arq = C / "equipe" / f"{x['ano']}_{x['matricula']}.json"
            if not arq.exists():
                continue
            por_mes = {}
            for a, m, tipo, folha, venc in json.loads(arq.read_text(encoding="utf-8")):
                if a * 100 + m < INICIO or a != x["ano"]:
                    continue
                por_mes.setdefault(m, [0.0, False])
                por_mes[m][0] += venc
                por_mes[m][1] |= tipo == 1 and venc > 0
            for m, (v, normal) in por_mes.items():
                k = (x["ano"], m, x["lotacao"])
                linhas.setdefault(k, [0, 0.0])
                linhas[k][0] += 1 if normal else 0
                linhas[k][1] += v
        eq = pd.DataFrame([{"ano": a, "mes": m, "gabinete": g, "pessoas": p, "custo": round(c, 2)} for (a, m, g), (p, c) in linhas.items()])
        if len(eq):
            gravar_csv(eq.sort_values(["ano", "mes", "gabinete"]), PASTA / "equipe.csv")
        ult = max(x["ano"] for x in lotados) if lotados else None
        cargos = pd.DataFrame([x for x in lotados if x["ano"] == ult and normalizar_nome(x["situacao"]) == "ATIVO"])
        if len(cargos):  # a lista do ano como estava quando foi lida (ano e mês da leitura: o "equipe em" do site)
            lida = time.localtime((C / f"lotados_{ult}.json").stat().st_mtime) if (C / f"lotados_{ult}.json").exists() else hoje
            gravar_csv(cargos.groupby(["lotacao", "cargo"]).size().reset_index(name="pessoas").rename(columns={"lotacao": "gabinete"})
                       .assign(ano=lida.tm_year, mes=lida.tm_mon), PASTA / "equipe_cargos.csv")


_PREFIXOS = re.compile(r"^(GAB(INETE)?\s+)?(DO\s+)?(DEP(UTADO|UTADA)?\.?\s+)", re.I)


def _sem_prefixo(lot):
    return normalizar_nome(_PREFIXOS.sub("", " ".join((lot or "").replace('"', " ").split()))).strip()


def _categoria(rubrica):
    u = normalizar_nome(rubrica)
    if "13" in u or "NATALIN" in u or "DECIMO" in u:
        return "decimo_terceiro"
    if "SUBSIDIO" in u:
        return "salario"
    if "AUXILIO" in u or "ALIMENTA" in u:
        return "auxilios"
    return "outros_rendimentos"


def _periodos_exatos(intervalos, meses_fora, ultimo_dado):
    """[(início, fim ou None)] de cada matrícula -> períodos no cargo (texto AAAA-MM-DD), tirando os meses inteiros em `meses_fora`."""
    dias = []
    for ini, fim in intervalos:
        d = max(ini, date(INICIO // 100, INICIO % 100, 1))
        ate = fim or date.today()
        while d <= ate:
            if d.year * 100 + d.month not in meses_fora:
                dias.append(d)
            d += timedelta(days=1)
    dias = sorted(set(dias))
    saida = []
    for d in dias:
        if saida and saida[-1][1] + timedelta(days=1) == d:
            saida[-1][1] = d
        else:
            saida.append([d, d])
    aberto = any(f is None for _, f in intervalos)
    res = []
    for i, (a, b) in enumerate(saida):
        ultimo = i == len(saida) - 1
        res.append((a.isoformat(), "" if (ultimo and aberto and b.year * 100 + b.month >= ultimo_dado) else b.isoformat()))
    return res


def _partido(civil, partidos):
    """Partido da candidatura de 2026 pelo nome civil; se o nome mudou (sobrenome a mais ou a menos), o único compatível."""
    if civil in partidos:
        return partidos[civil]
    achados = {p for n, p in partidos.items() if vc.compativel(n, civil) or vc.compativel(civil, n)}
    return achados.pop() if len(achados) == 1 else ""


def montar(tipos):
    arq_d, arq_f = PASTA / "deputados.csv", PASTA / "folha_deputados.csv"
    if not arq_d.exists():
        return None
    deps = pd.read_csv(arq_d, dtype=str).fillna("")
    fol = pd.read_csv(arq_f, dtype={"matricula": str}).fillna({"rubrica": ""}) if arq_f.exists() else pd.DataFrame(columns=COLS_FOLHA)
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    fol["am"] = fol.ano.astype(int) * 100 + fol.mes.astype(int)
    ultimo_dado = int(fol[fol.tipo_folha.astype(int) == 1].am.max()) if len(fol) else ultimo
    fol = fol[fol.am <= ultimo_dado]
    deps["civil"] = deps.nome.map(normalizar_nome)
    ver, mandatos, ganha, cod_civil = [], [], [], {}
    for civil, g in deps.groupby("civil"):
        lot = g.sort_values("ano").lotacao.iloc[-1]
        urna = _sem_prefixo(lot)
        t = por_civil.get(civil) or comum.achar(urna, tse) or comum.achar(civil, tse) or {}
        codigo = comum.codigo_de(civil, t)
        cod_civil[civil] = codigo
        ver.append({"codigo": codigo, "nome": vc.titulo(t.get("urna") or urna or civil), "nome_civil": vc.titulo(t.get("nome") or civil),
                    "partido": _partido(normalizar_nome(t.get("nome") or civil), partidos) or _partido(civil, partidos),
                    "genero": t.get("genero") or ("F" if feminino(civil) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        # períodos: admissão e exoneração de cada matrícula
        ints = {}
        for r in g.itertuples():
            ini = date.fromisoformat(r.admissao[:10]) if r.admissao else date(INICIO // 100, 1, 1)
            fim = date.fromisoformat(r.demissao[:10]) if r.demissao else None
            ints[r.matricula] = (ini, fim)
        fg = fol[fol.matricula.isin(set(g.matricula))]
        sub = fg[(fg.tipo_folha.astype(int) == 1) & fg.rubrica.map(lambda x: "SUBSIDIO" in normalizar_nome(x)) & (fg.valor > 0)]
        com_sub = set(sub.am)
        # mês inteiro sem subsídio na folha normal, com a folha do mês já publicada: licenciado (o suplente assumiu)
        fora = {am for am in {a * 100 + m for a, m in vc.meses(INICIO, ultimo_dado)} if am not in com_sub}
        per = _periodos_exatos(list(ints.values()), fora, ultimo_dado)
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
        for r in fg.itertuples():
            ganha.append({"ano": int(r.ano), "mes": int(r.mes), "codigo": codigo, "categoria": _categoria(r.rubrica), "valor": float(r.valor)})
    # equipe: o gabinete ("GAB DEP X") é de quem tem a mesma lotação; senão, do deputado com o nome de urna X
    equipe = cargos = None
    lot_cod = {}
    for r in deps.itertuples():
        lot_cod.setdefault(_sem_prefixo(r.lotacao), cod_civil[r.civil])
    urna_cod = {normalizar_nome(v["nome"]): v["codigo"] for v in ver}
    pal = {v["codigo"]: set(comum._palavras(v["nome"])) | set(comum._palavras(v["nome_civil"])) for v in ver}

    def dono(gab):
        x = _sem_prefixo(gab)
        if x in lot_cod:
            return lot_cod[x]
        if x in urna_cod:
            return urna_cod[x]
        p = set(comum._palavras(x))  # o único deputado com mais palavras do nome em comum (fora títulos)
        pontos = {c: len(p & ps) for c, ps in pal.items()}
        melhor = max(pontos.values(), default=0)
        quem = [c for c, n in pontos.items() if n == melhor]
        return quem[0] if melhor >= 1 and len(quem) == 1 else None
    if (PASTA / "equipe.csv").exists():
        eq = pd.read_csv(PASTA / "equipe.csv")
        eq["codigo"] = eq.gabinete.map(dono)
        sem = sorted(set(eq[eq.codigo.isna()].gabinete))
        if sem:
            log(f"  ALMT: gabinetes sem deputado: {sem}")
        eq = eq.dropna(subset=["codigo"])
        eq = eq[eq.ano * 100 + eq.mes <= ultimo_dado]
        equipe = pd.DataFrame({"ano": eq.ano, "mes": eq.mes, "codigo": eq.codigo.astype(int), "pessoas": eq.pessoas, "custo": eq.custo})
    equipe_em = ""
    if (PASTA / "equipe_cargos.csv").exists():
        cg = pd.read_csv(PASTA / "equipe_cargos.csv")
        cg["codigo"] = cg.gabinete.map(dono)
        cg = cg.dropna(subset=["codigo"])
        cargos = cg.groupby([cg.codigo.astype(int), "cargo"]).pessoas.sum().reset_index().rename(columns={"codigo": "codigo"})
        # o mês da lista de servidores lida (sem ele, nos arquivos antigos, o último mês da equipe)
        am = int(cg.ano.max()) * 100 + int(cg[cg.ano == cg.ano.max()].mes.max()) if "mes" in cg and len(cg) else \
            (int((equipe.ano * 100 + equipe.mes).max()) if equipe is not None and len(equipe) else 0)
        am = min(am, ultimo_dado) if am else 0
        equipe_em = f"{am % 100:02d}/{am // 100}" if am else ""
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), equipe_em=equipe_em)
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]), equipe=equipe, cargos=cargos)
