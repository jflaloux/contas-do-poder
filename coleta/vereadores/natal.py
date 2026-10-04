"""Câmara Municipal de Natal: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro):
- Mandatos: SAPL, https://sapl.natal.rn.leg.br/api/ — o robots.txt pede 60 s entre pedidos (2 pedidos por semana).
  As datas dos suplentes no SAPL são as da legislatura inteira; quem de fato exerceu em cada mês sai da lista da cota.
- Cota para o Exercício da Atividade Parlamentar, nota por nota (fornecedor, CNPJ, nº da nota, valor ressarcido):
  https://www.cmnat.rn.gov.br/consulta/consultar_vereador/?mes_id=&ano= (quem teve cota no mês, JSON) e
  POST https://www.cmnat.rn.gov.br/consulta/verbas_geral (notas de um vereador num mês, tabela HTML)
- Subsídio: R$ 26.000 desde jan/2025 (a folha da Câmara fica num servidor fora do ar para quem está fora da rede dela).
- Nome completo, partido e gênero: TSE (eleição de 2024).
"""
import html as html_lib
import json
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import _sessao, cache_valido, gravar_csv, log, verificar_prazo
from . import comum, sapl

COD = 2408102
INICIO = 202501
BASE_SAPL = "https://sapl.natal.rn.leg.br"
SITE = "https://www.cmnat.rn.gov.br"
PASTA = DADOS / "municipios" / "natal"
C = CACHE / "cmnat"
REBAIXAR = 3
CFG = {
    "cod": COD, "n": "Natal", "uf": "RN", "casa": "Câmara Municipal de Natal", "vagas": 29, "inicio": INICIO,
    "subsidio": [[202501, 26000.0]],  # Lei Promulgada nº 761/2023, art. 2º (legislatura 2025-2028)
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar", "verba_mes": {"2025": 22000.0, "2026": 22000.0},
    "verba_regra": "Reembolso com nota fiscal.",
    "verba_notas": ["As notas entram no mês de referência da prestação de contas."],
    "salario_nota": "A folha de pagamento nominal da Câmara não abre de fora da rede dela, por isso 13º e outros pagamentos não aparecem aqui.",
    "credito_foto": "Câmara Municipal de Natal", "pagina": "https://www.cmnat.rn.gov.br/vereadores",
    "notas": ["Sem a folha de pagamento, quem estava no cargo em cada mês vem da prestação de contas da cota: todo mês ela lista os 29 vereadores em exercício (titulares e suplentes que assumiram)."],
    "fontes": {"mandatos": f"{BASE_SAPL}/api/parlamentares/mandato/", "cota": f"{SITE}/verbas-2026",
               "subsidio": "https://sapl.natal.rn.leg.br/media/sapl/public/normajuridica/2023/1549/lp_761.23_integral.pdf"},
}


def _pedir(metodo, url, arquivo=None, dias=None, **kw):
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_text(encoding="utf-8")
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=90, **kw)
            r.raise_for_status()
            texto = r.text
            break
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(10)
    time.sleep(1.5)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(texto, encoding="utf-8")
    return texto


def _valor(t):
    t = re.sub(r"[^\d,]", "", t or "")
    return float(t.replace(",", ".")) if t else 0.0


def cota():
    """Notas da cota, mês a mês. Os meses antigos que já estão em dados/municipios/natal/ não são baixados de novo."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq_n, arq_m = PASTA / "cota_notas.csv", PASTA / "cota_meses.csv"
    velhas_n = pd.read_csv(arq_n, dtype={"cnpj_cpf": str}) if arq_n.exists() else pd.DataFrame()
    velhas_m = pd.read_csv(arq_m) if arq_m.exists() else pd.DataFrame(columns=["ano", "mes"])
    feitos = set(velhas_m.ano * 100 + velhas_m.mes) if len(velhas_m) else set()
    notas, ativos = [], []
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            notas += velhas_n[(velhas_n.ano * 100 + velhas_n.mes) == am].to_dict("records") if len(velhas_n) else []
            ativos += velhas_m[(velhas_m.ano * 100 + velhas_m.mes) == am].to_dict("records")
            continue
        dias = 5 if am > recentes else None
        lista = json.loads(_pedir("GET", f"{SITE}/consulta/consultar_vereador/", C / f"lista_{am}.json", dias, params={"mes_id": m, "ano": a}) or "{}").get("despesas") or []
        for v in lista:
            nome = v["nome"].strip()
            ativos.append({"ano": a, "mes": m, "id_cota": v["id"], "nome": nome})
            t = _pedir("POST", f"{SITE}/consulta/verbas_geral", C / f"notas_{am}_{v['id']}.html", dias,
                       data={"control": "consultar_vereador", "ano": a, "mes_id": m, "vereador_id": v["id"]})
            for linha in re.findall(r"<tr.*?</tr>", t, re.S):
                cel = [re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td.*?</td>", linha, re.S)]
                if len(cel) < 8 or not re.match(r"\d{2}/\d{2}/\d{4}", cel[0]):
                    continue
                notas.append({"ano": a, "mes": m, "id_cota": v["id"], "nome": nome, "data": cel[0], "item": cel[2], "fornecedor": cel[3],
                              "cnpj_cpf": comum.mascarar(cel[4]), "documento": cel[5], "valor": _valor(cel[7])})
    PASTA.mkdir(parents=True, exist_ok=True)
    if gravar_csv(pd.DataFrame(notas), arq_n):
        gravar_csv(pd.DataFrame(ativos), arq_m)
    log(f"  Natal: {len(notas)} notas da cota")


def lista_site():
    """Nome, página, foto e partido de cada vereador, pela página da Câmara (o SAPL pede 60 s entre pedidos)."""
    verificar_prazo()
    t = _sessao().get(f"{SITE}/vereadores", timeout=90).text
    linhas = []
    for foto, pagina, nome, partido in re.findall(r'url\(([^)]+)\).*?<a href="([^"]+/vereadores/\d+)".*?<h3[^>]*>(.*?)<span>(.*?)</span>', t, re.S):
        linhas.append({"pagina": pagina, "foto": foto.strip("'\" "), "nome": html_lib.unescape(nome).strip(), "partido": html_lib.unescape(partido).strip()})
    df = pd.DataFrame(linhas).drop_duplicates("pagina")
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df, PASTA / "site_vereadores.csv")
    log(f"  Natal: {len(df)} vereadores na página da Câmara")
    return df


def coletar():
    lista_site()
    leg = sapl.legislatura_atual(BASE_SAPL, pausa=60)
    mand = sapl.mandatos(BASE_SAPL, leg["id"], pausa=60)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(mand, PASTA / "mandatos.csv")
    cota()


def montar(tipos):
    if not (PASTA / "mandatos.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    mand = pd.read_csv(PASTA / "mandatos.csv").fillna("")
    notas = pd.read_csv(PASTA / "cota_notas.csv", dtype={"cnpj_cpf": str}).fillna({"cnpj_cpf": "", "fornecedor": ""}) if (PASTA / "cota_notas.csv").exists() else None
    ativos = pd.read_csv(PASTA / "cota_meses.csv") if (PASTA / "cota_meses.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome"])
    tse = comum.candidatos_tse("RN", "Natal")
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else pd.DataFrame(columns=["pagina", "foto", "nome", "partido"])
    site_op = [(n, i) for i, n in enumerate(site.nome)]
    linhas_v, fotos = [], []
    for pid, g in mand.groupby("parlamentar"):
        nome = g.nome.iloc[0]
        t = comum.achar_no_tse(nome, tse)
        i = comum.achar_parecido(nome, site_op, 0.9) if site_op else None
        s = site.iloc[i] if i is not None else None
        if s is not None and s["foto"]:
            fotos.append((int(pid), s["foto"]))
        linhas_v.append({"codigo": int(pid), "nome": comum.titulo(nome), "nome_civil": comum.titulo(t["nome"]) if t is not None else "",
                         "partido": (s["partido"] if s is not None and s["partido"] else "") or (t["partido"] if t is not None else ""),
                         "genero": t["genero"] if t is not None else "",
                         "eleito": "eleito" if g.titular.astype(str).eq("True").any() else "suplente",
                         "pagina": s["pagina"] if s is not None else f"{BASE_SAPL}/parlamentar/{int(pid)}",
                         "_k": comum.chave_nome(nome)})
    comum.fotos(COD, fotos)
    ver = pd.DataFrame(linhas_v)
    por_nome = {k: c for k, c in zip(ver._k, ver.codigo)}

    def codigo_de(nome):
        k = comum.chave_nome(nome)
        if k in por_nome:
            return por_nome[k]
        achados = [c for kk, c in por_nome.items() if set(k.split()) <= set(kk.split()) or set(kk.split()) <= set(k.split())]
        if len(achados) == 1:
            return achados[0]
        return comum.achar_parecido(nome, list(por_nome.items()) and [(kk, c) for kk, c in por_nome.items()], 0.9)
    ativos["codigo"] = ativos.nome.map(codigo_de)
    sem = sorted(set(ativos[ativos.codigo.isna()].nome))
    if sem:
        log(f"  Natal: na cota e não no SAPL: {', '.join(sem)}")
    ultimo_cota = int((ativos.ano * 100 + ativos.mes).max()) if len(ativos) else ate
    # no cargo: os meses em que o vereador aparece na lista da cota (29 por mês, o número de cadeiras: quem se
    # licencia sai da lista e o suplente entra). Sem a lista, o período do SAPL.
    linhas_m = []
    for r in ver.itertuples():
        meses_cota = set(ativos[ativos.codigo == r.codigo].ano * 100 + ativos[ativos.codigo == r.codigo].mes)
        if len(ativos):
            for de, fim in comum.periodos_de_meses(meses_cota, ultimo_cota):
                linhas_m.append({"codigo": r.codigo, "inicio": de, "fim": fim})
        else:
            for m in mand[mand.parlamentar == r.codigo].itertuples():
                fim = str(m.fim or "")[:10]
                linhas_m.append({"codigo": r.codigo, "inicio": m.inicio, "fim": fim if fim and fim < comum.hoje_iso() else ""})
    mandatos_df = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])
    despesas = None
    if notas is not None and len(notas):
        notas = notas.assign(codigo=notas.nome.map(codigo_de), tipo=notas.item.map(comum.tipo_curto))
        despesas = notas[notas.codigo.notna()].astype({"codigo": int})[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo_cota))
    return comum.montar(cfg, tipos, ver.drop(columns=["_k"]), mandatos_df, despesas=despesas)
