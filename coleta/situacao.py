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
}
SAIDA_MD = PROCESSADOS / "situacao.md"
SAIDA_JSON = PROCESSADOS / "situacao.json"


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
        atraso = _meses_entre(um, fechado) if um else None
        situacao = ("falhando" if falhando else "atrasada (fonte)" if atraso is not None and atraso >= 3 and ch in ATRASOS_CONHECIDOS
                    else "atrasada" if atraso is not None and atraso >= 3 else "ok")
        erro = next((c.get("ultimo_erro") for lugar, c in tent.items() if c.get("falhas", 0) > 0), None)
        linhas.append({"fonte": ch, "situacao": situacao, "ultimo_mes": um, "meses_atras": atraso,
                       "ultimo_sucesso": ultimo_ok[0] if ultimo_ok else None, "onde": ultimo_ok[1] if ultimo_ok else None,
                       "so_brasil": onde._so_brasil(ch), "erro": erro or (ATRASOS_CONHECIDOS.get(ch) if situacao == "atrasada (fonte)" else None)})
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
    log(f"Situação das fontes: {len(linhas)} fontes, {len(problemas)} com problema (dados/processados/situacao.md)")
    for l in problemas:
        log(f"  {l['fonte']}: {l['situacao']}" + (f" ({l['erro'][:100]})" if l["erro"] else f" (último mês {fmt(l['ultimo_mes'])})"))
    return len(problemas)
