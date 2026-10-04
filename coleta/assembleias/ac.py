"""Assembleia Legislativa do Acre (Aleac): deputado estadual por deputado estadual.

Fontes (abrem também de fora do Brasil):
- Deputados: a lista de servidores do Portal da Transparência da Aleac (https://app.al.ac.leg.br/gestao-pessoas/servidores),
  pelo que a página usa (api/funcionario/servidores/datatables/server?busca=DEPUTADO): matrícula, nome, cargo
  "DEPUTADO ESTADUAL", data de admissão e de exoneração.
- Nome parlamentar e página de cada deputado: a página "Deputados" do site da Aleac (https://www.al.ac.leg.br/?page_id=45506,
  aba "Legislatura 16ª"). O partido dessa página não é usado (está desatualizado para vários deputados).
- Subsídio: Lei 4.136/2023 (R$ 31.948,49 desde fev/2024, R$ 33.448,49 desde fev/2025 e R$ 34.774,64 desde fev/2026):
  https://app.al.ac.leg.br/legisla-e/legislacao/visualizar/9238
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
O que não entra: a folha dos deputados (a consulta "Remuneração dos Servidores" não traz valores para nenhum mês), a verba
indenizatória por deputado (o portal só tem a regulamentação) e a equipe de cada gabinete (a lotação de todos é "GABINETE").
Quem está no cargo: as datas de admissão e de exoneração da lista de servidores (licenças não aparecem nela).
"""
import html as H
import re
import time

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "AC"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://app.al.ac.leg.br/"
PAG = f"{SITE}gestao-pessoas/servidores"
PAG_DEPUTADOS = "https://www.al.ac.leg.br/?page_id=45506"
PASTA = DADOS / "assembleias" / "ac"
CFG = {
    "cod": COD, "n": "Acre", "uf": UF, "casa": "Assembleia Legislativa do Acre", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 31948.49], [202502, 33448.49], [202602, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 4.136/2023), proporcional aos dias no cargo. A consulta \"Remuneração dos "
                     "Servidores\" da Aleac não traz valores, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Ressarcimento de despesas do mandato (regulamentação interna da Aleac).",
    "verba_notas": ["A Aleac publica só a regulamentação da verba indenizatória, sem os valores de cada deputado: a verba fica de fora."],
    "pagina": PAG_DEPUTADOS,
    "notas": ["Quem está no cargo: as datas de admissão e de exoneração de cada deputado na lista de servidores da Aleac. A lista "
              "não mostra licenças: até a exoneração do suplente Marcus Cavalcante, em 09/03/2026, ela tem 25 deputados no cargo "
              "para 24 vagas.",
              "A equipe dos gabinetes não entra: a lista de servidores mostra a lotação de todos como \"GABINETE\", sem o deputado.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"deputados": PAG, "lista": PAG_DEPUTADOS, "subsidio": f"{SITE}legisla-e/legislacao/visualizar/9238"},
}


def _get(params):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{SITE}api/funcionario/servidores/datatables/server", params=params, timeout=90)
            r.raise_for_status()
            dormir(1)
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _site():
    """Página "Deputados" do site da Aleac -> [(nome parlamentar, página)] da aba da legislatura atual."""
    t = _sessao().get(PAG_DEPUTADOS, timeout=90).text
    i = t.find('data-tab-id="1"')
    j = t.find('data-tab-id="2"', i + 1)
    aba = t[i:j if j > i else len(t)] if i >= 0 else ""
    saida = []
    for link, nome in re.findall(r'<a href="([^"]*page_id=\d+)"[^>]*>.*?<h2 class="title">([^<]+)</h2>', aba, flags=re.S):
        link = H.unescape(link)
        saida.append((" ".join(H.unescape(nome).split()), link if link.startswith("http") else "https://www.al.ac.leg.br" + link))
    return saida


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    d = _get({"draw": 1, "start": 0, "length": 200, "busca": "DEPUTADO"})
    deps = [{"matricula": x["matricula"], "nome": " ".join((x.get("nome") or "").split()), "cargo": (x.get("cargo") or "").strip(),
             "setor": (x.get("setor") or "").strip(), "admissao": x.get("dataAdmissao") or "", "exoneracao": x.get("dataDemissao") or ""}
            for x in d.get("data") or [] if normalizar_nome(x.get("cargo") or "") == "DEPUTADO ESTADUAL"]
    if len(deps) < 20:
        log(f"  Aleac: a lista de servidores trouxe só {len(deps)} deputados; fica o que já estava gravado")
        return
    gravar_csv(pd.DataFrame(deps).assign(visto_em=time.strftime("%Y-%m-%d")).sort_values(["admissao", "nome"]),
               PASTA / "deputados.csv")
    try:
        site = _site()
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — sem a página, fica o nome de urna do TSE
        log(f"  Aleac: a página de deputados não abriu ({type(e).__name__}); fica a lista que já estava gravada")
        site = []
    if len(site) >= 20:
        gravar_csv(pd.DataFrame(site, columns=["nome_parlamentar", "pagina"]), PASTA / "deputados_site.csv")
    log(f"  Aleac: {len(deps)} deputados na lista de servidores ({sum(1 for x in deps if not x['exoneracao'])} sem exoneração); "
        f"{len(site)} na página de deputados")


def _partido(civil, partidos):
    """Partido da candidatura de 2026 pelo nome civil; se o nome mudou (sobrenome a mais ou a menos), o único compatível."""
    if civil in partidos:
        return partidos[civil]
    achados = {p for n, p in partidos.items() if vc.compativel(n, civil) or vc.compativel(civil, n)}
    return achados.pop() if len(achados) == 1 else ""


def _do_site(civil, site, tse):
    """(nome parlamentar, página) do deputado na página da Aleac: todas as palavras do nome parlamentar (sem títulos) no nome
    civil, sem outro deputado que também sirva; senão, o candidato do TSE com esse nome de urna e o mesmo nome civil."""
    palavras = set(comum._palavras(civil))
    for nome, pagina in site:
        p = set(comum._palavras(nome))
        if p and p <= palavras:
            return nome, pagina
    for nome, pagina in site:
        t = comum.achar(nome, tse)
        if t and normalizar_nome(t["nome"]) == civil:
            return nome, pagina
    return None, None


def montar(tipos):
    arq = PASTA / "deputados.csv"
    if not arq.exists():
        return None
    deps = pd.read_csv(arq, dtype=str).fillna("")
    inicio = f"{INICIO // 100}-{INICIO % 100:02d}-01"
    deps = deps[(deps.exoneracao == "") | (deps.exoneracao >= inicio)]
    site = [tuple(x) for x in pd.read_csv(PASTA / "deputados_site.csv", dtype=str).fillna("").values] \
        if (PASTA / "deputados_site.csv").exists() else []
    # o nome parlamentar só vale se casar com um único deputado da lista de servidores
    civis = [normalizar_nome(n) for n in deps.nome]
    usados = {}
    for c in civis:
        nome, _ = _do_site(c, site, {})
        if nome:
            usados.setdefault(nome, []).append(c)
    site = [(n, p) for n, p in site if len(usados.get(n, [])) <= 1]
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ver, mandatos = [], []
    for r in deps.itertuples():
        civil = normalizar_nome(r.nome)
        t = por_civil.get(civil) or comum.achar(civil, tse) or {}
        codigo = comum.codigo_de(civil, t)
        parlamentar, pagina = _do_site(civil, site, tse)
        ver.append({"codigo": codigo, "nome": parlamentar or vc.titulo(t.get("urna") or civil), "nome_civil": vc.titulo(t.get("nome") or civil),
                    "partido": _partido(normalizar_nome(t.get("nome") or civil), partidos) or _partido(civil, partidos),
                    "genero": t.get("genero") or ("F" if feminino(civil) else "M"), "eleito": t.get("eleito", ""), "pagina": pagina or CFG["pagina"]})
        mandatos.append({"codigo": codigo, "inicio": max(r.admissao[:10], inicio), "fim": r.exoneracao[:10]})
    cfg = dict(CFG, ultimo_mes=ultimo)
    return vc.montar(cfg, tipos, pd.DataFrame(ver).drop_duplicates("codigo"), pd.DataFrame(mandatos))
