"""Situação das fontes: de cada uma, o último mês que está no site, a última coleta que deu certo (e onde: exterior
ou Brasil) e a última falha. Sai em dados/processados/situacao.md (e .json), no fim de cada rodada.

- "falhando": a última tentativa falhou em todos os lugares que tentaram (o site continua com o que já tinha);
- "atrasada": o último mês no site está 3 meses ou mais atrás do último mês fechado (pode ser só o atraso da própria
  fonte: Minas e São Paulo, por exemplo, publicam a folha com alguns meses de atraso);
- "ok".
Na rodada do GitHub, o relatório aparece no resumo da execução; na do Brasil, as fontes com problema viram um aviso.
"""
import json
from datetime import datetime

from . import onde
from .config import PROCESSADOS, RAIZ
from .util import log

SITE = RAIZ / "site" / "dados"
# atrasos que a própria fonte explica (não são falha do robô): aparecem como "atrasada (fonte)"
ATRASOS_CONHECIDOS = {
    "folhas/MG": "a Secretaria de Planejamento publica a folha com alguns meses de atraso",
    "folhas/SP": "o Estado publica a série histórica com alguns meses de atraso",
    "folhas/PA": "desde abr/2026 a consulta não mostra quem tem mandato eletivo",
    "folhas/RJ": "desde mar/2026 o governador em exercício é pago pelo Tribunal de Justiça, e o cargo de vice está vago",
    "assembleias/rj": "a Alerj publica o mês de cada gabinete depois de analisar a prestação de contas",
    "assembleias/ma": "a Alema publica a prestação de contas de cada deputado com meses de atraso; o site vai até o último mês com 80% dos deputados",
    "judiciario/stf": "o DadosJusBr coleta cada mês por volta do dia 16 do mês seguinte",
    "judiciario/stm": "o DadosJusBr coleta cada mês por volta do dia 16 do mês seguinte",
    "judiciario/tse": "o DadosJusBr coleta cada mês por volta do dia 16 do mês seguinte",
    "prefeituras/campo_grande": "a consulta da Prefeitura não traz a folha depois de fev/2026 (conferido em 01/10/2026)",
    "prefeituras/recife": "o arquivo de 2026 no portal de dados abertos da Prefeitura vai até jun/2026 (atualizado pela última vez em "
                          "26/06/2026, conferido em 02/10/2026)",
}
SAIDA_MD = PROCESSADOS / "situacao.md"
SAIDA_JSON = PROCESSADOS / "situacao.json"
SAIDA_SITE = SITE / "situacao.json"  # a versão pública (página "frescor dos dados"): sem erro técnico nem onde rodou
GRUPOS = [("federal", "Governo federal e Congresso"), ("judiciario", "Judiciário"), ("folhas", "Governadores"),
          ("assembleias", "Assembleias Legislativas"), ("vereadores", "Câmaras Municipais das capitais"),
          ("prefeituras", "Prefeituras das capitais"), ("tce", "Interior (Tribunais de Contas)")]
# grupos cuja fonte tem de aparecer no arquivo do site: sem o último mês lá, a montagem falhou (a cidade ou o estado saiu do site)
NO_SITE = ("vereadores", "prefeituras", "assembleias")


def _ler(nome):
    arq = SITE / nome
    try:
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    except ValueError:
        return {}


def _meses_entre(a, b):
    return (b // 100 - a // 100) * 12 + (b % 100 - a % 100)


def _ultimos_meses():
    """{fonte: último mês (AAAAMM) no site}."""
    from . import assembleias, prefeituras, vereadores
    um = {}
    cam, pre, ass = _ler("camaras.json").get("meta", {}), _ler("prefeituras.json").get("meta", {}), _ler("assembleias.json").get("meta", {})
    for m in vereadores.CIDADES:
        um[onde.chave("vereadores", m)] = cam.get("cidades", {}).get(str(m.CFG["cod"]), {}).get("ultimo_mes")
    for m in prefeituras.CIDADES:
        um[onde.chave("prefeituras", m)] = pre.get("cidades", {}).get(str(m.CFG["cod"]), {}).get("ultimo_mes")
    for m in assembleias.ESTADOS:
        um[onde.chave("assembleias", m)] = ass.get("estados", {}).get(m.CFG["uf"], {}).get("ultimo_mes")
    for e in _ler("governadores.json").get("e", []):
        if e.get("m"):
            um[f"folhas/{e['uf']}"] = max(l[0] for l in e["m"])
    dados = _ler("dados.json").get("meta", {})
    for f in ("camara", "senado"):
        um[f"federal/{f}"] = dados.get("ultimo_mes")
    um["federal/executivo"] = dados.get("ultimo_mes_executivo")
    for sigla, m in _ler("judiciario.json").get("meta", {}).get("orgaos", {}).items():
        um[f"judiciario/{sigla.lower()}"] = m.get("ultimo_mes")
    for arq in sorted((SITE / "interior").glob("*.json")) if (SITE / "interior").exists() else []:
        meta = _ler(f"interior/{arq.name}").get("meta", {})
        if meta.get("ultimo_mes"):
            um[f"tce/{arq.stem}"] = meta["ultimo_mes"]
    return um


def executar():
    from .vereadores.comum import ultimo_mes_fechado
    fechado = ultimo_mes_fechado()
    coletas = {lugar: onde.ler(lugar) for lugar in onde.LUGARES}
    meses = _ultimos_meses()
    linhas = []
    for ch in sorted(set(meses) | set(coletas["exterior"]) | set(coletas["brasil"])):
        tent = {lugar: coletas[lugar].get(ch) for lugar in onde.LUGARES if coletas[lugar].get(ch)}
        sucessos = [(c["ultimo_sucesso"], lugar) for lugar, c in tent.items() if c.get("ultimo_sucesso")]
        ultimo_ok = max(sucessos) if sucessos else None
        falhando = bool(tent) and all(c.get("falhas", 0) > 0 for c in tent.values())
        um = meses.get(ch)
        fora_do_site = um is None and ch.split("/")[0] in NO_SITE
        falhando = falhando or fora_do_site
        atraso = _meses_entre(um, fechado) if um else None
        situacao = ("falhando" if falhando else "atrasada (fonte)" if atraso is not None and atraso >= 3 and ch in ATRASOS_CONHECIDOS
                    else "atrasada" if atraso is not None and atraso >= 3 else "ok")
        erro = next((c.get("ultimo_erro") for lugar, c in tent.items() if c.get("falhas", 0) > 0), None)
        if fora_do_site and not erro:
            erro = "não entrou no arquivo do site (a montagem falhou: ver o log da rodada)"
        falhas = [c.get("primeira_falha") or c.get("ultima_falha") for c in tent.values() if c.get("falhas", 0) > 0]
        linhas.append({"fonte": ch, "situacao": situacao, "ultimo_mes": um, "meses_atras": atraso,
                       "ultimo_sucesso": ultimo_ok[0] if ultimo_ok else None, "onde": ultimo_ok[1] if ultimo_ok else None,
                       "so_brasil": onde._so_brasil(ch), "falha_desde": min([f for f in falhas if f], default=None) if falhando else None,
                       "erro": erro or (ATRASOS_CONHECIDOS.get(ch) if situacao == "atrasada (fonte)" else None)})
    ordem = {"falhando": 0, "atrasada": 1, "atrasada (fonte)": 2, "ok": 3}
    linhas.sort(key=lambda l: (ordem[l["situacao"]], l["fonte"]))
    problemas = [l for l in linhas if l["situacao"] in ("falhando", "atrasada")]
    SAIDA_JSON.write_text(json.dumps({"gerado_em": datetime.now().isoformat(timespec="seconds"), "ultimo_mes_fechado": fechado,
                                      "fontes": linhas}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fmt = lambda am: f"{am % 100:02d}/{am // 100}" if am else "—"
    md = [f"# Situação das fontes ({datetime.now():%d/%m/%Y %H:%M}, rodada: {onde.LUGAR})", "",
          f"Último mês fechado: {fmt(fechado)}. {len(linhas)} fontes: {sum(l['situacao'] == 'ok' for l in linhas)} ok, "
          f"{sum(l['situacao'] == 'atrasada (fonte)' for l in linhas)} com o atraso da própria fonte, "
          f"{sum(l['situacao'] == 'atrasada' for l in linhas)} atrasadas, {sum(l['situacao'] == 'falhando' for l in linhas)} falhando.", "",
          "| Fonte | Situação | Último mês no site | Última coleta certa | Onde | Último erro ou motivo |", "|---|---|---|---|---|---|"]
    for l in linhas:
        md.append(f"| {l['fonte']}{' (só do Brasil)' if l['so_brasil'] else ''} | {l['situacao']} | {fmt(l['ultimo_mes'])} | "
                  f"{(l['ultimo_sucesso'] or '—')[:10]} | {l['onde'] or '—'} | {(l['erro'] or '').replace('|', '/')[:120]} |")
    SAIDA_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    publicar(linhas, fechado)
    log(f"Situação das fontes: {len(linhas)} fontes, {len(problemas)} com problema (dados/processados/situacao.md)")
    for l in problemas:
        log(f"  {l['fonte']}: {l['situacao']}" + (f" ({l['erro'][:100]})" if l["erro"] else f" (último mês {fmt(l['ultimo_mes'])})"))
    return len(problemas)


def _nomes_e_links():
    """{fonte: (nome, uf ou None, link oficial)} de cada fonte, pelo que os próprios robôs e arquivos do site dizem.
    Também {"via:" + fonte: nome} de quem não vem direto do órgão (STF, STM e TSE pelo DadosJusBr)."""
    from . import assembleias, prefeituras, vereadores

    def link(cfg, *chaves):
        f = cfg.get("fontes") or {}
        return next((f[k] for k in chaves if f.get(k)), None) or cfg.get("pagina")
    saida = {}
    for m in vereadores.CIDADES:
        saida[onde.chave("vereadores", m)] = (m.CFG.get("casa") or f"Câmara Municipal de {m.CFG['n']}", m.CFG["uf"],
                                              link(m.CFG, "folha", "verba", "gastos"))
    for m in prefeituras.CIDADES:
        saida[onde.chave("prefeituras", m)] = (m.CFG.get("casa") or f"Prefeitura de {m.CFG['n']}", m.CFG["uf"], link(m.CFG, "folha"))
    estados = {}
    for m in assembleias.ESTADOS:
        estados[m.CFG["uf"]] = m.CFG["n"]
        saida[onde.chave("assembleias", m)] = (m.CFG["casa"], m.CFG["uf"], link(m.CFG, "folha", "verba"))
    for e in _ler("governadores.json").get("e", []):
        saida[f"folhas/{e['uf']}"] = (f"Folha de pagamento do governo do estado ({estados.get(e['uf'], e['uf'])})", e["uf"],
                                      (e.get("folha") or {}).get("u"))
    fontes = _ler("dados.json").get("meta", {}).get("fontes", {})
    saida["federal/camara"] = ("Câmara dos Deputados", None, fontes.get("camara_api"))
    saida["federal/senado"] = ("Senado Federal", None, fontes.get("senado_legis"))
    saida["federal/executivo"] = ("Governo federal (presidente, vice e ministros): Portal da Transparência", None, fontes.get("portal_transparencia"))
    for sigla, m in _ler("judiciario.json").get("meta", {}).get("orgaos", {}).items():
        saida[f"judiciario/{sigla.lower()}"] = (m.get("n") or sigla, None, m.get("fonte"))
        if m.get("via") and m["via"] != "oficial":
            saida[f"via:judiciario/{sigla.lower()}"] = m["via"]
    for arq in sorted((SITE / "interior").glob("*.json")) if (SITE / "interior").exists() else []:
        meta = _ler(f"interior/{arq.name}").get("meta", {})
        saida[f"tce/{arq.stem}"] = (f"{meta.get('tribunal') or 'Tribunal de Contas'}: vereadores, prefeitos e vices do interior ({estados.get(meta.get('uf'), meta.get('uf'))})",
                                    meta.get("uf"), meta.get("url"))
    return saida


def publicar(linhas, fechado):
    """site/dados/situacao.json, para a página pública "frescor dos dados": de cada fonte, o nome, o grupo, o link oficial,
    o último mês com dados no site, a data da última coleta certa e a situação em palavras neutras. Nada interno: sem a
    mensagem de erro, o caminho de arquivo nem onde a coleta rodou."""
    fmt_mes = lambda am: f"{am % 100:02d}/{am // 100}"
    fmt_dia = lambda iso: f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
    info = _nomes_e_links()
    fontes = []
    for l in linhas:
        grupo = l["fonte"].split("/")[0]
        nome, uf, url = info.get(l["fonte"], (l["fonte"], None, None))
        s = l["situacao"]
        if s == "falhando":
            sit, texto = "falhou", (f"A coleta falhou desde {fmt_dia(l['falha_desde'])}" if l.get("falha_desde") else "A última coleta falhou") + \
                ": o site mostra os últimos dados obtidos."
        elif s == "atrasada (fonte)":
            motivo = ATRASOS_CONHECIDOS[l["fonte"]]
            sit, texto = "atraso_fonte", f"Atraso da própria fonte: {motivo[0].lower() + motivo[1:]}."
        elif s == "atrasada":
            sit, texto = "atrasada", f"Os dados vão até {fmt_mes(l['ultimo_mes'])}, {l['meses_atras']} meses antes do último mês fechado."
        else:
            sit, texto = "em_dia", "Em dia."
        fontes.append({"id": l["fonte"], "nome": nome, "grupo": grupo, "uf": uf, "url": url, "via": info.get("via:" + l["fonte"]),
                       "ultimo_mes": l["ultimo_mes"],
                       "ultima_coleta": (l["ultimo_sucesso"] or "")[:10] or None, "situacao": sit, "texto": texto})
    ordem = {g: i for i, (g, _) in enumerate(GRUPOS)}
    fontes.sort(key=lambda f: (ordem.get(f["grupo"], 99), f["uf"] or "", f["nome"]))
    from zoneinfo import ZoneInfo
    dados = {"gerado_em": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"), "ultimo_mes_fechado": fechado,
             "grupos": [{"id": g, "nome": n} for g, n in GRUPOS if any(f["grupo"] == g for f in fontes)],
             "situacoes": {"em_dia": "Em dia", "atraso_fonte": "Atraso da própria fonte", "atrasada": "Atrasada", "falhou": "A coleta falhou"},
             "fontes": fontes}
    SAIDA_SITE.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
