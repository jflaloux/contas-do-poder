"""Assembleia Legislativa de Goiás (Alego): deputado estadual por deputado estadual.

Fontes (o que o Portal da Transparência da Alego, https://transparencia.al.go.leg.br/, usa; sem cadastro):
- Meses publicados da verba indenizatória: .../api/transparencia/verbas_indenizatorias/periodos
- Deputados com prestação no mês: .../verbas_indenizatorias/deputados?ano=AAAA&mes=M
- Prestação de um deputado no mês, por grupo e subgrupo, nota a nota (fornecedor, CNPJ/CPF, data, número, valor
  apresentado e indenizado): .../verbas_indenizatorias/exibir?ano=AAAA&mes=M&deputado_id=N
- Subsídio: Lei 17.253/2011, com a redação da Lei 21.780/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde
  fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022).
Quem esteve no cargo em cada mês sai da lista de deputados com prestação no mês. Entra o valor indenizado. Quem está no
cargo hoje: a página "Deputados em Exercício" do site da Alego (https://portal.al.go.leg.br/deputados/em-exercicio), menos
quem tem afastamento em aberto em "Deputados fora do exercício" (/deputados/fora-exercicio: licença, falecimento, com a
data). A página dos em exercício continua com quem está licenciado; a dos afastamentos diz desde quando.
A tela de remuneração da página pede nome e CPF de quem consulta para abrir o detalhe: essa parte não é usada.
"""
import json
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "GO"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
API = "https://transparencia.al.go.leg.br/api/transparencia/verbas_indenizatorias"
PASTA = DADOS / "assembleias" / "go"
C = CACHE / "assembleias" / "go"
MAX_PRESTACOES = 400
PAUSA = 0.5
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Goiás", "uf": UF, "casa": "Assembleia Legislativa de Goiás", "vagas": 41, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 17.253/2011, com a redação da Lei 21.780/2023), proporcional aos meses no cargo. "
                     "O 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal; entra o valor indenizado (o aprovado), não o apresentado.",
    "verba_notas": ["Cada nota entra no mês da prestação de contas."],
    "pagina": "https://transparencia.al.go.leg.br/",
    "notas": ["Quem estava no cargo em cada mês: os deputados com prestação de contas da verba naquele mês. Quem está no cargo hoje: "
              "a lista de deputados em exercício do site da Alego, menos quem tem afastamento em aberto (licença, falecimento) "
              "na lista de deputados fora do exercício; o titular sem afastamento publicado conta como no cargo nos meses sem "
              "prestação de contas."],
    "fontes": {"verba": "https://transparencia.al.go.leg.br/", "subsidio": "https://legisla.casacivil.go.gov.br/api/v2/pesquisa/legislacoes/106697/pdf"},
}


def _json(caminho, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{API}/{caminho}", params=params, timeout=120)
            r.raise_for_status()
            dormir(PAUSA)
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


PORTAL = "https://portal.al.go.leg.br/deputados/"


def _linhas(caminho):
    """Linhas da tabela de uma página de deputados do site da Alego: [(id, [textos das células])]."""
    import html as H
    import re
    verificar_prazo()
    t = _sessao().get(PORTAL + caminho, timeout=60).text
    saida = []
    for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
        m = re.search(r"/deputados/perfil/(\d+)", linha)
        cel = [" ".join(H.unescape(re.sub(r"<b[^>]*>.*?</b>|<[^>]+>", " ", c)).split()) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, flags=re.S)]
        if m and cel:
            saida.append((int(m.group(1)), cel))
    return saida


def _situacao_hoje():
    """em_exercicio.csv (id e nome de quem a página "Deputados em Exercício" lista) e afastamentos.csv (as linhas de
    "Deputados fora do exercício": id, nome, tipo, data do afastamento e do retorno)."""
    ex = [{"id": i, "nome": c[0]} for i, c in _linhas("em-exercicio")]
    if 0.8 * CFG["vagas"] <= len(ex) <= 1.2 * CFG["vagas"]:
        pd.DataFrame(ex).assign(visto_em=time.strftime("%Y-%m-%d"), fonte=PORTAL + "em-exercicio").to_csv(PASTA / comum.EM_EXERCICIO, index=False)
    af = [{"id": i, "nome": c[0], "tipo": c[1], "afastamento": c[2], "retorno": c[3] if len(c) > 3 else ""} for i, c in _linhas("fora-exercicio") if len(c) >= 3]
    if af:
        pd.DataFrame(af).to_csv(PASTA / "afastamentos.csv", index=False)


def _hoje(ids):
    """({id: True/False} de quem está em exercício hoje, {id: último dia no cargo}) pela lista dos em exercício e pelos
    afastamentos em aberto (licença, falecimento, renúncia; "Retorno do Titular" e "Suplência" são a saída do suplente,
    que a lista dos em exercício já mostra)."""
    from datetime import date, datetime, timedelta
    arq_ex, arq_af = PASTA / comum.EM_EXERCICIO, PASTA / "afastamentos.csv"
    if not arq_ex.exists():
        return None, {}
    lista = set(pd.read_csv(arq_ex).id.astype(int))
    af = pd.read_csv(arq_af, dtype=str).fillna("") if arq_af.exists() else pd.DataFrame(columns=["id", "tipo", "afastamento", "retorno"])
    hoje, fora, fins = date.today(), set(), {}
    d = lambda s: datetime.strptime(s.strip(), "%d/%m/%Y").date() if s.strip() else None
    for id_, g in af.groupby("id"):
        g = g.assign(ini=g.afastamento.map(d), ret=g.retorno.map(d)).dropna(subset=["ini"]).sort_values("ini")
        g = g[~g.tipo.map(normalizar_nome).isin({"RETORNO DO TITULAR", "SUPLENCIA"})]
        if len(g) and g.ini.iloc[-1] <= hoje and (g.ret.iloc[-1] is None or g.ret.iloc[-1] > hoje):
            fora.add(int(id_))
            ult = g.ini.iloc[-1] if "FALEC" in normalizar_nome(g.tipo.iloc[-1]) else g.ini.iloc[-1] - timedelta(days=1)
            fins[int(id_)] = ult.isoformat()
    return {i: (i in lista and i not in fora) for i in ids}, fins


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:
        _situacao_hoje()
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — sem as listas, ficam as já gravadas
        log(f"  Alego: as listas de deputados em exercício e afastados não abriram ({type(e).__name__}); ficam as já gravadas")
    (C / "prestacoes").mkdir(parents=True, exist_ok=True)
    meses = sorted(p["ano"] * 100 + m for p in _json("periodos") for m in p["meses"] if p["ano"] * 100 + m >= INICIO)
    lista_arq = PASTA / "deputados_por_mes.csv"
    antigos = pd.read_csv(lista_arq) if lista_arq.exists() else pd.DataFrame(columns=["ano", "mes", "id", "nome"])
    feitos = set(antigos.ano * 100 + antigos.mes) if len(antigos) else set()
    novos = []
    for am in meses:
        if am in feitos and am < meses[-2]:
            continue
        for d in _json("deputados", {"ano": am // 100, "mes": am % 100}) or []:
            novos.append({"ano": am // 100, "mes": am % 100, "id": int(d["id"]), "nome": " ".join(d["nome"].split())})
    if novos:
        nv = pd.DataFrame(novos)
        antigos = pd.concat([antigos[~(antigos.ano * 100 + antigos.mes).isin(set(nv.ano * 100 + nv.mes))], nv], ignore_index=True)
    antigos.sort_values(["ano", "mes", "nome"]).to_csv(lista_arq, index=False)
    baixadas, partidos = 0, {}
    ultimos = set(meses[-2:])
    fila = []
    for p in antigos.sort_values(["ano", "mes"], ascending=False).itertuples():
        arq = C / "prestacoes" / f"{p.ano}{p.mes:02d}_{p.id}.json"
        am = p.ano * 100 + p.mes
        if not (arq.exists() and (am not in ultimos or time.time() - arq.stat().st_mtime < 3 * 86400)):
            fila.append((p.ano, p.mes, p.id, arq))
    fila = fila[:MAX_PRESTACOES]

    def uma(item):
        ano, mes, id_, arq = item
        arq.write_text(json.dumps(_json("exibir", {"ano": ano, "mes": mes, "deputado_id": id_}), ensure_ascii=False), encoding="utf-8")
        return 1

    from concurrent.futures import ThreadPoolExecutor
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:  # a API responde devagar (~2 s por prestação): 3 pedidos por vez
            for _ in ex.map(uma, fila):
                baixadas += 1
    finally:
        linhas = []
        for p in antigos.itertuples():
            arq = C / "prestacoes" / f"{p.ano}{p.mes:02d}_{p.id}.json"
            if not arq.exists():
                continue
            d = json.loads(arq.read_text(encoding="utf-8")) or {}
            if (d.get("deputado") or {}).get("partido"):
                partidos[p.id] = d["deputado"]["partido"]
            for g in d.get("grupos") or []:
                grupo = g.get("descricao", "")
                for s in g.get("subgrupos") or []:
                    for lanc in s.get("lancamentos") or []:
                        f = lanc.get("fornecedor") or {}
                        linhas.append({"ano": p.ano, "mes": p.mes, "id": p.id, "grupo": " ".join(grupo.split()), "subgrupo": " ".join((s.get("descricao") or "").split()),
                                       "fornecedor": (f.get("nome") or "").strip(), "cnpj_cpf": vc.mascarar(f.get("cnpj_cpf") or ""),
                                       "data": (f.get("data") or "")[:10], "numero": f.get("numero", ""), "valor": num(f.get("valor_indenizado"))})
        pd.DataFrame(linhas).sort_values(["ano", "mes", "id", "data"]).to_csv(PASTA / "verba_notas.csv", index=False)
        if partidos:
            antigo = pd.read_csv(PASTA / "partidos.csv") if (PASTA / "partidos.csv").exists() else pd.DataFrame(columns=["id", "partido"])
            juntos = {**dict(zip(antigo.id, antigo.partido)), **partidos}
            pd.DataFrame(sorted(juntos.items()), columns=["id", "partido"]).to_csv(PASTA / "partidos.csv", index=False)
        faltam = sum(1 for p in antigos.itertuples() if not (C / "prestacoes" / f"{p.ano}{p.mes:02d}_{p.id}.json").exists())
        log(f"  Alego: {antigos.id.nunique()} deputados com prestação desde {INICIO % 100:02d}/{INICIO // 100}, {baixadas} prestações baixadas agora, {faltam} faltando")


def _tipo(grupo):
    import re
    t = re.sub(r"^\d+\s*-\s*", "", grupo or "").strip()
    return t.capitalize() if t else "Outros"


def montar(tipos):
    arq_l = PASTA / "deputados_por_mes.csv"
    if not arq_l.exists():
        return None
    lista = pd.read_csv(arq_l)
    verba = pd.read_csv(PASTA / "verba_notas.csv", dtype={"cnpj_cpf": str}).fillna("") if (PASTA / "verba_notas.csv").exists() else pd.DataFrame()
    partidos = dict(pd.read_csv(PASTA / "partidos.csv").values) if (PASTA / "partidos.csv").exists() else {}
    tse = comum.tse_2022(UF)
    p2026 = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((lista.ano * 100 + lista.mes).max())
    ver, mandatos = [], []
    for id_, g in lista.groupby("id"):
        nome = g.nome.iloc[-1]
        t = comum.achar(nome, tse) or {}
        ver.append({"codigo": int(id_), "nome": nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "", "partido": partidos.get(id_) or p2026.get(normalizar_nome(t.get("nome", "")), ""),
                    "genero": t.get("genero") or ("F" if feminino(nome.replace("Dra. ", "")) else "M"), "eleito": t.get("eleito", ""),
                    "pagina": "https://portal.al.go.leg.br/deputados/em-exercicio"})
        for i, f in comum.periodos(list(g.ano * 100 + g.mes), ultimo_dado, ultimo):
            mandatos.append({"codigo": int(id_), "inicio": i, "fim": f})
    atual, fins = _hoje([v["codigo"] for v in ver])
    if atual:  # o titular sem afastamento publicado está no cargo também nos meses sem prestação de contas
        mandatos = comum.aplicar_hoje(mandatos, atual, ultimo_dado, fins, folga=24)
    desp = verba.rename(columns={"id": "codigo"}).assign(tipo=lambda d: d.grupo.map(_tipo)) if len(verba) else None
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), fora_hoje=comum.fora_hoje(atual))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]] if desp is not None else None)
