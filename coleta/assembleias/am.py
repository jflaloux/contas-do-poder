"""Assembleia Legislativa do Amazonas (Aleam): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Aleam; só abre de dentro do Brasil, então este robô roda no Mac):
- CEAP (Cota para o Exercício da Atividade Parlamentar): a página "Controle de Cota Parlamentar"
  (https://www.aleam.gov.br/transparencia/controle-de-cota-parlamentar/), um formulário (ano, mês, parlamentar), e o CSV
  que o botão "Exportar para CSV" da página baixa (createCeap.php): o resumo do mês (saldo anterior, verba creditada,
  despesa reembolsável, saldo) e cada despesa: lote, nota, emissão, beneficiário com o CNPJ, verba, valor bruto, glosa e
  valor líquido. O CPF de beneficiário pessoa física não é guardado. A página HTML do formulário traz o mesmo (e os dados
  do cadastro de cada CNPJ), mas cada consulta leva ~10 s; o CSV sai em menos de 1 s.
- Folha: a "Consulta de Vencimentos Nominal" não devolve resultado para nenhuma busca (testado em 01/10/2026); o salário
  é o subsídio da lei: 75% do subsídio do deputado federal (Lei 4.729/2018), R$ 34.774,64 desde fev/2025, valor
  ratificado pela Lei 8.161/2026.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os meses em que a consulta da CEAP traz o resumo do deputado (com verba creditada ou despesa).
"""
import csv
import html as H
import io
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "AM"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://www.aleam.gov.br/transparencia/"
PAG_CEAP = f"{SITE}controle-de-cota-parlamentar/"
PASTA = DADOS / "assembleias" / "am"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Amazonas", "uf": UF, "casa": "Assembleia Legislativa do Amazonas", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei, proporcional aos meses no cargo: 75% do subsídio do deputado federal (Lei 4.729/2018), "
                     "R$ 34.774,64 desde fev/2025, valor ratificado pela Lei 8.161/2026. A consulta de vencimentos nominal da Aleam não "
                     "devolve resultado, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (CEAP)",
    "verba_mes": {"2025": 49849.65, "2026": 49849.65},
    "verba_regra": ("Valor mensal creditado a cada gabinete (R$ 49.849,65) para despesas do mandato, reembolsadas com nota fiscal; o saldo "
                    "passa para o mês seguinte (Resolução Legislativa 460/2009)."),
    "verba_notas": ["A Aleam publica cada despesa da CEAP: beneficiário, verba, documento, data, valor bruto, glosa e valor reembolsado, com o "
                    "CNPJ. Aqui entra o valor reembolsado (líquido da glosa), no mês da consulta.",
                    "Em alguns meses, a despesa reembolsável do resumo é maior que a soma das despesas listadas na página; aqui vale o resumo, e "
                    "a diferença aparece como \"Diferença entre o resumo do mês e as despesas listadas\"."],
    "pagina": "https://www.aleam.gov.br/deputados/",
    "notas": ["Quem está no cargo: os meses em que a consulta da CEAP traz o resumo do deputado (verba creditada ou despesa).",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": PAG_CEAP, "subsidio": "https://sapl.al.am.leg.br/media/sapl/public/normajuridica/2026/14731/8161.pdf",
               "lei_subsidio": "https://sapl.al.am.leg.br/media/sapl/public/normajuridica/2018/10302/lei_4729.pdf"},
}
RESUMO = {"SALDO ANTERIOR": "saldo_anterior", "VERBA CREDITADA": "verba_creditada", "TOTAL DISPONIVEL": "total_disponivel",
          "DESPESA REEMBOLSAVEL": "despesa_reembolsavel", "SALDO": "saldo"}


EXPORTA = f"{SITE}wp-content/themes/transparencia/createCeap.php"
NOMES_MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _get(url, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=120, **kw)
            if r.status_code == 400 and "Nenhum dado" in r.text:
                dormir(1)
                return None
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


def _parlamentares(t):
    """Lista do formulário (a de 2024 em diante): [(id, nome)]."""
    i = t.find('name="dados"')
    j = t.find("</select>", i)
    return [(int(v), " ".join(H.unescape(n).split())) for v, n in re.findall(r'<option value="(\d+)"[^>]*>([^<]+)<', t[i:j])] if i >= 0 else []


CPF_NO_NOME = re.compile(r"\s*(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")

def _exportacao(texto):
    """CSV que o botão "Exportar para CSV" da página baixa -> (nome civil, {resumo}, [despesas])."""
    resumo, despesas, civil, cab = {}, [], "", None
    for l in csv.reader(io.StringIO(texto), delimiter=";"):
        if not l or not any(x.strip() for x in l):
            continue
        k = normalizar_nome(l[0])
        if cab is None:
            if k.startswith("DEPUTADO"):
                civil = " ".join(l[1].split()) if len(l) > 1 else ""
            elif k == "SALDO DISPONIVEL":
                resumo["saldo"] = num(l[1])
            elif k in RESUMO:
                resumo[RESUMO[k]] = num(l[1])
            elif k == "LOTE":
                cab = [normalizar_nome(x) for x in l]
            continue
        d = dict(zip(cab, l))
        if not d.get("VAL LIQUIDO", "").strip():
            continue
        benef = " ".join(d.get("BENEFICIARIO", "").split())
        m = re.match(r"^([\d./*-]{11,})\s*-\s*(.*)$", benef)
        doc, nome = (m.group(1), m.group(2)) if m else ("", benef)
        nome = CPF_NO_NOME.sub("", nome).strip()  # o nome de MEI traz o CPF do dono ("FULANA DA SILVA 12345678901"): não é guardado
        despesas.append({"lote": d.get("LOTE", "").strip(), "documento": d.get("NF NRO.", "").strip(), "emissao": d.get("EMISSAO", "").strip(),
                         "verba": " ".join(d.get("VERBA/DESCRICAO", "").split()), "detalhamento": " ".join(d.get("DETALHAMENTO", "").split()),
                         "beneficiario": nome.strip(), "cnpj_cpf": vc.mascarar(doc), "valor_bruto": num(d.get("VAL BRUTO", "0")),
                         "glosa": num(d.get("GLOSA", "0")), "valor": num(d.get("VAL LIQUIDO", "0"))})
    return civil, resumo, despesas


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # de fora do Brasil o portal não responde: desiste logo (o site usa o que já está gravado)
        t = _sessao().get(PAG_CEAP, timeout=30).text
    except Exception as e:  # noqa: BLE001
        log(f"  Aleam: o portal não abriu ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
        return
    lista = _parlamentares(t)
    if len(lista) < 20:
        raise RuntimeError(f"Aleam: só {len(lista)} parlamentares no formulário da CEAP (o leiaute mudou?)")
    meses = _meses()
    arq_r, arq_d, arq_p = PASTA / "ceap_resumo.csv", PASTA / "ceap_despesas.csv", PASTA / "parlamentares.csv"
    res = pd.read_csv(arq_r) if arq_r.exists() else pd.DataFrame(columns=["ano", "mes", "id", "nome", "achou"])
    desp = pd.read_csv(arq_d, dtype={"cnpj_cpf": str, "documento": str}) if arq_d.exists() else pd.DataFrame(columns=["ano", "mes", "id"])
    par = pd.read_csv(arq_p).fillna("") if arq_p.exists() else pd.DataFrame(columns=["id", "nome", "nome_civil", "visto_em"])
    hoje = time.strftime("%Y-%m-%d")
    # quem está no formulário hoje, mais quem já apareceu antes, mais os outros números até 5 depois do maior: o suplente que
    # assume no lugar de um deputado tem número próprio e não aparece na lista do formulário (em 2025-2026, os números 37 e 38)
    par = par[(par.id.astype(int) > 0) & (par.nome != "(sondagem)")] if len(par) else par
    res = res[res.id.astype(int) > 0] if len(res) else res
    ids = {i: n for i, n in lista}
    for i, n in zip(par.id, par.nome):
        ids.setdefault(int(i), n)
    todos = sorted(set(ids) | set(range(1, max(ids) + 6)))
    # os dois últimos meses são pedidos de novo, uma vez por dia (a coleta em partes não repete o que acabou de pedir)
    lido = res.lido_em.fillna("").astype(str) if "lido_em" in res else pd.Series([""] * len(res))
    feitos = {(int(a), int(m), int(i)): l for a, m, i, l in zip(res.ano, res.mes, res.id, lido)}
    pedir = [(am, i) for am in meses for i in todos
             if (am // 100, am % 100, i) not in feitos or (am >= meses[-2] and feitos[(am // 100, am % 100, i)] < hoje)]

    def um(item):
        am, i = item
        r = _get(EXPORTA, params={"parlamentar": str(i), "parlamentarJaneiro": "", "mes": NOMES_MESES[am % 100 - 1], "ano": str(am // 100), "formato": "csv"})
        return am, i, (_exportacao(r.content.decode("utf-8-sig", errors="replace")) if r is not None else None)
    total = 0
    # em lotes, gravando depois de cada lote (a coleta pode rodar em partes curtas)
    with ThreadPoolExecutor(SIMULTANEOS) as ex:
        for k in range(0, len(pedir), SIMULTANEOS * 10):
            verificar_prazo()
            lote = list(ex.map(um, pedir[k:k + SIMULTANEOS * 10]))
            res, desp, par = _gravar(lote, ids, res, desp, par, hoje)
            total += len(lote)
    log(f"  Aleam: CEAP de {total} de {len(pedir)} deputados e meses pedida agora; {int(res.achou.sum()) if len(res) else 0} com resumo")


def _csv(df, arq):
    gravar_csv(df, arq)


def _gravar(resultados, ids, res, desp, par, hoje):
    arq_r, arq_d, arq_p = PASTA / "ceap_resumo.csv", PASTA / "ceap_despesas.csv", PASTA / "parlamentares.csv"
    if True:
        novos_r, novos_d, nomes = [], [], {}
        for am, i, p in resultados:
            if p is None:  # sem resultado no mês: guarda para não pedir de novo
                novos_r.append({"ano": am // 100, "mes": am % 100, "id": i, "nome": ids.get(i, ""), "achou": 0, "lido_em": hoje})
                continue
            civil, resumo, despesas = p
            nome = ids.get(i) or vc.titulo(civil)
            novos_r.append({"ano": am // 100, "mes": am % 100, "id": i, "nome": nome, "achou": 1, **resumo, "lido_em": hoje})
            for d in despesas:
                novos_d.append({"ano": am // 100, "mes": am % 100, "id": i, **d})
            nomes[i] = (nome, civil or nomes.get(i, ("", ""))[1])
            soma = round(sum(d["valor"] for d in despesas), 2)
            if abs(soma - resumo.get("despesa_reembolsavel", soma)) >= 0.01:
                log(f"  Aleam: {nome} {am % 100:02d}/{am // 100}: despesas somam {soma:.2f} e o resumo diz {resumo.get('despesa_reembolsavel'):.2f}")
        if novos_r:
            nr = pd.DataFrame(novos_r)
            chave = set(zip(nr.ano, nr.mes, nr.id))
            res = pd.concat([res[[k not in chave for k in zip(res.ano, res.mes, res.id)]], nr]) if len(res) else nr
            _csv(res.sort_values(["ano", "mes", "id"]), arq_r)
            nd = pd.DataFrame(novos_d, columns=["ano", "mes", "id", "lote", "documento", "emissao", "verba", "detalhamento", "beneficiario", "cnpj_cpf",
                                               "valor_bruto", "glosa", "valor"])
            desp = desp[[k not in chave for k in zip(desp.ano, desp.mes, desp.id)]] if len(desp) else desp
            desp = pd.concat([desp, nd]) if len(desp) and len(nd) else (nd if not len(desp) else desp)
            _csv(desp.sort_values(["ano", "mes", "id", "emissao", "documento"]), arq_d)
        for i, (nome, civil) in nomes.items():
            antes = par[par.id == i]
            civil = civil or (antes.nome_civil.iloc[0] if len(antes) else "")
            par = pd.concat([par[par.id != i], pd.DataFrame([{"id": i, "nome": nome, "nome_civil": civil, "visto_em": hoje}])])
        if nomes or len(par):
            _csv(par.sort_values("id"), arq_p)
    return res, desp, par


def _partido(nome, partidos):
    """Partido da candidatura de 2026 (comum.partido_2026) pelo nome civil: igual; igual sem os espaços ("D ANGELO" e
    "DANGELO"); ou o único candidato de 2026 com o mesmo primeiro nome e todas as palavras (pelo menos três) dentro do nome
    de 2022 (quem tirou um sobrenome: "JANAINA LIMA ARAUJO" e "JANAINA LIMA ARAUJO RAMOS")."""
    n = normalizar_nome(nome)
    if not n:
        return ""
    if n in partidos:
        return partidos[n]
    juntos = [v for k, v in partidos.items() if k.replace(" ", "") == n.replace(" ", "")]
    if len(juntos) == 1:
        return juntos[0]
    w = n.split()
    dentro = [v for k, v in partidos.items() if len(k.split()) >= 3 and k.split()[0] == w[0] and set(k.split()) <= set(w)]
    return dentro[0] if len(dentro) == 1 else ""


_TIPOS = [(r"INFORMATIVO|FOLDER|BANNER", "Divulgação do mandato"), (r"FILMAGEM|FOTOGR", "Fotografia e filmagem"),
          (r"EXPEDIENTE", "Material de escritório"), (r"FRETAMENTO|TAXI A[EÉ]REO|AERONAVE|EMBARCA", "Fretamento de aviões e barcos"), (r"COMBUST|LUBRIFIC", "Combustível"),
          (r"LOCA[CÇ][AÃ]O DE VE[IÍ]C|VE[IÍ]CULO", "Aluguel de carros"), (r"JUR[IÍ]DIC", "Consultoria jurídica"),
          (r"CONSULTORIA|ASSESSORIA|PESQUISA", "Consultorias e assessorias"), (r"DIVULGA|PUBLICIDADE|M[IÍ]DIA", "Divulgação do mandato"),
          (r"IM[OÓ]VE|ESCRIT[OÓ]RIO|ALUGUEL", "Escritório (aluguel e contas)"), (r"TELEF|INTERNET", "Telefone e internet"),
          (r"PASSAGE|A[EÉ]RE", "Passagens"), (r"HOSPEDA|HOTEL", "Hospedagem e diárias"), (r"ALIMENTA|REFEI", "Alimentação"),
          (r"GR[AÁ]FIC|IMPRESS", "Material gráfico (arte e impressão)")]


def _tipo(verba):
    u = normalizar_nome(verba)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(verba)


def montar(tipos):
    arq_r = PASTA / "ceap_resumo.csv"
    if not arq_r.exists():
        return None
    res = pd.read_csv(arq_r)
    res = res[res.achou == 1].copy()
    desp = pd.read_csv(PASTA / "ceap_despesas.csv", dtype={"cnpj_cpf": str}).fillna({"cnpj_cpf": "", "beneficiario": "", "verba": ""}) \
        if (PASTA / "ceap_despesas.csv").exists() else pd.DataFrame(columns=["ano", "mes", "id", "verba", "beneficiario", "cnpj_cpf", "valor"])
    par = pd.read_csv(PASTA / "parlamentares.csv").fillna("") if (PASTA / "parlamentares.csv").exists() else pd.DataFrame(columns=["id", "nome", "nome_civil"])
    civis = {int(i): c for i, c in zip(par.id, par.nome_civil) if c}
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(v["nome"]): v for v in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    res["am"] = res.ano * 100 + res.mes
    for c in ("verba_creditada", "despesa_reembolsavel"):
        res[c] = pd.to_numeric(res.get(c), errors="coerce").fillna(0.0)
    ativo = res[(res.verba_creditada > 0.005) | (res.despesa_reembolsavel > 0.005)]
    if not len(ativo):
        return None
    ultimo_dado = int(ativo.am.max())
    ver, mandatos, cods = [], [], {}
    for i, g in ativo.groupby("id"):
        nome = g.sort_values("am").nome.iloc[-1]
        civil = civis.get(int(i), "")
        t = por_civil.get(normalizar_nome(civil)) or comum.achar(nome, tse) or comum.achar(re.sub(r"[’']", " ", nome), tse) or {}
        if t.get("urna") and normalizar_nome(nome) == normalizar_nome(civil):  # suplente fora da lista do formulário: o nome de urna
            nome = vc.titulo(t["urna"])
        codigo = comum.codigo_de(nome, t)
        cods[int(i)] = codigo
        nc = t.get("nome") or civil or nome
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(nc),
                    "partido": _partido(nc, partidos) or _partido(civil, partidos),
                    "genero": t.get("genero") or ("F" if feminino(civil or nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_g = sorted(set(g.am))
        per = comum.periodos(meses_g, ultimo_dado, ultimo, folga=1)
        if meses_g[-1] < ultimo_dado:
            per = [(a, f or f"{meses_g[-1] // 100}-{meses_g[-1] % 100:02d}-28") for a, f in per]
        for a, f in per:
            mandatos.append({"codigo": codigo, "inicio": a, "fim": f})
    d = desp[(desp.valor.abs() >= 0.005)]
    d = d.assign(codigo=d.id.map(cods)).dropna(subset=["codigo"])
    despesas = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.codigo.astype(int), "tipo": d.verba.map(_tipo),
                             "fornecedor": d.beneficiario, "cnpj_cpf": d.cnpj_cpf, "valor": d.valor})
    # em alguns meses, a despesa reembolsável do resumo é maior que a soma das despesas listadas: vale o resumo, e a diferença
    # entra sem fornecedor
    soma = d.groupby(["ano", "mes", "id"]).valor.sum()
    dif = []
    for r in ativo.itertuples():
        x = round(r.despesa_reembolsavel - float(soma.get((r.ano, r.mes, r.id), 0.0)), 2)
        if abs(x) >= 0.01 and int(r.id) in cods:
            dif.append({"ano": r.ano, "mes": r.mes, "codigo": cods[int(r.id)], "tipo": "Diferença entre o resumo do mês e as despesas listadas",
                        "fornecedor": "", "cnpj_cpf": "", "valor": x})
    if dif:
        despesas = pd.concat([despesas, pd.DataFrame(dif)])
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=despesas)
