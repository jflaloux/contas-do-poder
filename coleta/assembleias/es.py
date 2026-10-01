"""Assembleia Legislativa do Espírito Santo (Ales): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Ales; o portal só abre de dentro do Brasil, então este robô roda no Mac):
- Cotas parlamentares por gabinete e mês (diárias, passagens e os reembolsos por rubrica, sem fornecedor): o que a
  página https://www.al.es.gov.br/Transparencia/CotasParlamentares usa (Transparencia/Api/CotasParlamentaresNovoTable/
  <mês inicial>/<mês final>/<ano>/<gabinete>/<inativos>), mais as listas de gabinetes (SetoresAtivosDiv, SetoresTodosDiv).
- Subsídio: Lei 11.766/2022, R$ 34.774,64 desde 01/02/2025 (tabela "Estrutura remuneratória - Deputados" da Ales).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE (a página da cota
  mostra o partido de hoje, que só vale para quem está no cargo).
Quem está no cargo hoje: a lista de gabinetes ativos. Desde quando: os meses com gasto na cota.
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

UF = "ES"
COD = comum.CODIGOS_UF[UF]
INICIO = 202502
SITE = "https://www.al.es.gov.br"
PASTA = DADOS / "assembleias" / "es"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Espírito Santo", "uf": UF, "casa": "Assembleia Legislativa do Espírito Santo", "vagas": 30, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 11.766/2022), proporcional aos meses no cargo. O período começa em fev/2025, quando "
                     "passou a valer esse valor (a tabela de antes não está publicada). A Ales não publica a folha dos deputados, por "
                     "isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Cota parlamentar",
    "verba_regra": "Valor mensal por gabinete para diárias, passagens e reembolso de despesas do mandato (Ato da Mesa 6.226/2025).",
    "verba_notas": ["A Ales publica a cota por gabinete, mês e rubrica (diárias, passagens, divulgação, consultorias, aluguel), sem "
                    "fornecedor nem CNPJ."],
    "pagina": f"{SITE}/Deputado/Lista",
    "notas": ["Quem está no cargo hoje: a lista de gabinetes ativos da Ales. Desde quando: os meses com gasto na cota.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": f"{SITE}/Transparencia/CotasParlamentares", "subsidio": f"{SITE}/Transparencia/EstruturaRemuneratoria"},
}


def _get(caminho):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(SITE + caminho, timeout=90)
            r.raise_for_status()
            dormir(1)
            return r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _setores(caminho):
    return [(int(a), re.sub(r"^Gab\.?\s*Dep\.?\s*", "", " ".join(H.unescape(b).split()), flags=re.I)) for a, b in
            re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)', _get(caminho)) if a != "0"]


LINHA = re.compile(r"([A-Za-zÀ-ú][^$]*?)\s+(\d+|-)\s+R\$\s*(-?[\d.]+,\d{2})")


def _tabela(t):
    """HTML da cota -> (nome civil, partido, [(rubrica, quantidade, valor)], total)."""
    texto = " ".join(H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())
    civil = re.search(r"Nome Civil:\s*(.+?)\s+Partido:", texto)
    partido = re.search(r"Partido:\s*(.+?)\s+Telefone", texto)
    i = texto.find("Produto Quantidade Valor Solicitado")
    if i < 0:
        return (civil.group(1) if civil else ""), (partido.group(1) if partido else ""), [], None
    corpo = texto[i + len("Produto Quantidade Valor Solicitado"):]
    tot = re.search(r"Total:\s*R\$\s*(-?[\d.]+,\d{2})", corpo)
    corpo = corpo[:tot.start()] if tot else corpo
    linhas = [(re.sub(r"^Reembolso das Despesas\s+", "", r.strip()), q, num(v)) for r, q, v in LINHA.findall(corpo)]
    return (civil.group(1) if civil else ""), (partido.group(1) if partido else ""), linhas, (num(tot.group(1)) if tot else None)


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # de fora do Brasil o portal não responde: desiste logo (o site usa o que já está gravado)
        _sessao().get(SITE + "/Transparencia/SetoresAtivosDiv", timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Ales: o portal não abriu ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
        return
    ativos = _setores("/Transparencia/SetoresAtivosDiv")
    todos = _setores("/Transparencia/SetoresTodosDiv")
    if len(ativos) >= 25:
        pd.DataFrame(ativos, columns=["gabinete", "nome"]).assign(visto_em=time.strftime("%Y-%m-%d")).to_csv(PASTA / "gabinetes_ativos.csv", index=False)
    meses = _meses()
    arq = PASTA / "cota_rubricas.csv"
    feito = pd.read_csv(arq).fillna("") if arq.exists() else pd.DataFrame(columns=["ano", "mes", "gabinete"])
    arq_anos = PASTA / "gabinetes_com_cota.csv"  # gabinete e ano com algum gasto (para não pedir mês a mês quem não estava lá)
    anos = pd.read_csv(arq_anos) if arq_anos.exists() else pd.DataFrame(columns=["gabinete", "ano", "total"])
    ativos_ids = {g for g, _ in ativos}
    if True:
        vistos = set(zip(anos.gabinete, anos.ano))
        recente = time.time() - arq_anos.stat().st_mtime < 7 * 86400 if arq_anos.exists() else False
        faltam = [(g, a) for g, _ in todos for a in sorted({m // 100 for m in meses})
                  if (g, a) not in vistos or (a == meses[-1] // 100 and not recente)]
        def ano_de(item):
            g, a = item
            ult = max(m % 100 for m in meses if m // 100 == a)
            _, _, linhas, total = _tabela(_get(f"/Transparencia/Api/CotasParlamentaresNovoTable/{1 if a > INICIO // 100 else INICIO % 100}/{ult}/{a}/{g}/true"))
            return g, a, (total if total is not None else sum(v for _, _, v in linhas))
        novos = []
        try:
            with ThreadPoolExecutor(SIMULTANEOS) as ex:
                for r in ex.map(ano_de, faltam):
                    novos.append(r)
        finally:
            if novos:
                anos = pd.concat([anos[[k not in {(g, a) for g, a, _ in novos} for k in zip(anos.gabinete, anos.ano)]],
                                  pd.DataFrame(novos, columns=["gabinete", "ano", "total"])])
                anos.sort_values(["gabinete", "ano"]).to_csv(arq_anos, index=False)
        com_gasto = {(int(g), int(a)) for g, a, t in zip(anos.gabinete, anos.ano, anos.total) if t and float(t) > 0}
        nomes = dict(todos)
        pedir = []
        for am in meses:
            for g, _ in todos:
                if (g, am // 100) not in com_gasto and g not in ativos_ids:
                    continue
                ja = ((feito.ano == am // 100) & (feito.mes == am % 100) & (feito.gabinete == g)).any() if len(feito) else False
                if ja and am < meses[-2]:
                    continue
                pedir.append((am, g))

        def mes_de(item):
            am, g = item
            civil, partido, linhas, total = _tabela(_get(f"/Transparencia/Api/CotasParlamentaresNovoTable/{am % 100}/{am % 100}/{am // 100}/{g}/true"))
            return [{"ano": am // 100, "mes": am % 100, "gabinete": g, "deputado": nomes.get(g, ""), "nome_civil": civil, "partido_hoje": partido,
                     "rubrica": r, "quantidade": q, "valor": v, "total_pagina": total} for r, q, v in linhas] or \
                   [{"ano": am // 100, "mes": am % 100, "gabinete": g, "deputado": nomes.get(g, ""), "nome_civil": civil, "partido_hoje": partido,
                     "rubrica": "", "quantidade": "", "valor": 0.0, "total_pagina": total}]
        resultados = []
        try:
            with ThreadPoolExecutor(SIMULTANEOS) as ex:
                for r in ex.map(mes_de, pedir):
                    resultados.append(r)
        finally:
            if resultados:
                novos = pd.DataFrame([x for r in resultados for x in r])
                chave = set(zip(novos.ano, novos.mes, novos.gabinete))
                if len(feito):
                    feito = feito[[k not in chave for k in zip(feito.ano, feito.mes, feito.gabinete)]]
                feito = pd.concat([feito, novos])
                feito.sort_values(["ano", "mes", "gabinete", "rubrica"]).to_csv(arq, index=False)
            log(f"  Ales: {len(resultados)} de {len(pedir)} meses de gabinete pedidos agora; {len(feito)} linhas")


_TIPOS = [(r"DEVOLU", "Devolução de diárias"), (r"DI[AÁ]RIAS INTERNACIONAIS", "Diárias internacionais"), (r"DI[AÁ]RIA", "Hospedagem e diárias"),
          (r"PASSAGE", "Passagens"), (r"CONSULTORIA", "Consultorias e assessorias"), (r"DIVULGA", "Divulgação do mandato"),
          (r"EQUIPAMENTO", "Aluguel de móveis e equipamentos"), (r"IM[OÓ]VEL", "Escritório (aluguel e contas)"), (r"SOFTWARE", "Site e sistemas")]


def _tipo(rubrica):
    u = normalizar_nome(rubrica)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(rubrica)


def montar(tipos):
    arq = PASTA / "cota_rubricas.csv"
    if not arq.exists():
        return None
    v = pd.read_csv(arq).fillna({"rubrica": "", "nome_civil": "", "partido_hoje": "", "deputado": ""})
    v["deputado"] = v.deputado.str.replace(r"^Gab\.?\s*Dep\.?\s*", "", regex=True, flags=re.I)
    v["am"] = v.ano * 100 + v.mes
    com_tabela = v[v.rubrica != ""]
    if not len(com_tabela):
        return None
    ultimo_dado = int(com_tabela.am.max())  # o mês corrente aparece sem tabela até a Ales publicar
    ativos = set(pd.read_csv(PASTA / "gabinetes_ativos.csv").gabinete) if (PASTA / "gabinetes_ativos.csv").exists() else set()
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ver, mandatos, cods = [], [], {}
    for gab, g in com_tabela.groupby("gabinete"):
        nome = g.deputado.iloc[-1]
        civil = next((c for c in reversed(list(g.nome_civil)) if c), "")
        t = por_civil.get(normalizar_nome(civil)) or comum.achar(nome, tse) or {}
        codigo = comum.codigo_de(nome, t)
        cods[gab] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome") or civil or nome),
                    "partido": partidos.get(normalizar_nome(t.get("nome") or civil), ""),
                    "genero": t.get("genero") or ("F" if feminino(civil or nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        # no cargo: os meses em que a página da cota tem a tabela do gabinete (sem tabela = fora, como o titular licenciado)
        per = comum.periodos(sorted(set(g.am)), ultimo_dado, ultimo, folga=1)
        if gab not in ativos:
            fim = int(g.am.max())
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    d = com_tabela[com_tabela.valor.abs() >= 0.005]
    sinal = [-1 if "DEVOLU" in normalizar_nome(r) else 1 for r in d.rubrica]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.gabinete.map(cods), "tipo": d.rubrica.map(_tipo), "fornecedor": "",
                         "cnpj_cpf": "", "valor": d.valor * sinal})
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp)
