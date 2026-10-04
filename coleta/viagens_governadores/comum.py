"""Parte comum dos robôs das viagens dos governadores e vices.

Cada estado grava dados/governadores/viagens/<uf>.csv (vai para o Git), uma linha por viagem:
    id, inicio, fim (AAAA-MM-DD), nome (como a fonte escreve), cargo (como a fonte escreve), destino, diarias,
    passagens, outros, devolucoes (R$), obs, fonte (o endereço da consulta)
Nada de CPF (as respostas de alguns portais trazem o CPF mascarado: não é lido) nem do texto livre do motivo.

montar() liga cada viagem à pessoa (o índice em "ocupantes" do arquivo curado, na ordem do site) pelo nome e pela data
de início (a viagem é da pessoa no cargo que ela ocupava naquele dia) e soma por mês do início da viagem, como nos
ministros: e.vg = [[aaaamm, índice em e.oc, diárias, passagens, outros, devoluções, número de viagens], ...].
"""
import csv
import json
import time
from pathlib import Path

from ..config import CACHE, DADOS
from ..util import _sessao, dormir, gravar_linhas, normalizar_nome, verificar_prazo

PASTA = DADOS / "governadores" / "viagens"
C = CACHE / "viagens"
INICIO = 202501
COLUNAS = ["id", "inicio", "fim", "nome", "cargo", "destino", "diarias", "passagens", "outros", "devolucoes", "obs", "fonte"]


def arquivo(uf):
    return PASTA / f"{uf.lower()}.csv"


def ultimo_mes():
    """O último mês fechado (AAAAMM)."""
    t = time.localtime()
    return (t.tm_year - 1) * 100 + 12 if t.tm_mon == 1 else t.tm_year * 100 + t.tm_mon - 1


def meses(ate=None):
    ate = ate or ultimo_mes()
    saida, am = [], INICIO
    while am <= ate:
        saida.append(am)
        a, m = divmod(am, 100)
        am = (a + 1) * 100 + 1 if m == 12 else am + 1
    return saida


def recente(am, n=3):
    """O mês está entre os n últimos fechados (a fonte ainda pode mudar: a consulta é refeita)?"""
    return am >= meses()[-n]


def obter(url, arq, dias, metodo="GET", **kw):
    """JSON da fonte, com cache em `arq` (refeito depois de `dias`; None = nunca)."""
    arq = Path(arq)
    if arq.exists() and (dias is None or time.time() - arq.stat().st_mtime < dias * 86400):
        return json.loads(arq.read_text(encoding="utf-8"))
    verificar_prazo()
    ultimo = None
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=120, **kw)
            r.raise_for_status()
            d = r.json()
            break
        except Exception as e:  # noqa: BLE001 — erro temporário da fonte: tenta de novo, depois desiste
            ultimo = e
            dormir(10 * (tentativa + 1))
    else:
        raise ultimo
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    dormir(1)
    return d


def num(v):
    if v in (None, "", "-"):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


LIDOS = PASTA / "lidos.json"  # {uf: último mês lido na última coleta que deu certo} (o "até" de e.vgf)


def lido_ate(uf):
    return json.loads(LIDOS.read_text(encoding="utf-8")).get(uf) if LIDOS.exists() else None


class MenosQueOGravado(RuntimeError):
    """A fonte trouxe bem menos viagens do que já estava gravado: a coleta falha e o último dado bom fica."""


def gravar(uf, linhas):
    """Grava as viagens do estado (todas desde INICIO) e, depois, o mês lido. Se a fonte trouxe bem menos viagens do que
    já estava gravado (nenhuma, quando havia alguma, ou menos de 90% menos 2), não grava nada e falha: o último dado bom
    fica, o mês lido não avança e a situação marca a falha (regra do projeto: robô que falha não apaga o último dado
    bom). A gravação passa ainda pela comparação de util.gravar_com."""
    unicas = {}
    for l in linhas:
        unicas[str(l["id"])] = l
    antes = len(ler(uf))
    if antes and (not unicas or len(unicas) < 0.9 * antes - 2):
        raise MenosQueOGravado(f"a fonte trouxe {len(unicas)} viagens, e {antes} já estavam gravadas: fica o que estava")
    PASTA.mkdir(parents=True, exist_ok=True)
    ordem = sorted(unicas.values(), key=lambda l: (l["inicio"], str(l["id"])))
    linhas_csv = [{k: (round(l.get(k) or 0.0, 2) if k in ("diarias", "passagens", "outros", "devolucoes") else (l.get(k) or ""))
                   for k in COLUNAS} for l in ordem]
    if not gravar_linhas(arquivo(uf), COLUNAS, linhas_csv):
        raise MenosQueOGravado("a gravação foi recusada por perda de cobertura: fica o que estava")
    lidos = json.loads(LIDOS.read_text(encoding="utf-8")) if LIDOS.exists() else {}
    lidos[uf] = ultimo_mes()
    LIDOS.write_text(json.dumps(dict(sorted(lidos.items())), indent=1) + "\n", encoding="utf-8")
    return len(ordem)


def ler(uf):
    if not arquivo(uf).exists():
        return []
    with open(arquivo(uf), encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------------------------------- ligação com as pessoas
def _tokens(nome):
    return {w for w in normalizar_nome(nome or "").split() if len(w) > 2 and w not in ("DOS", "DAS", "DE", "DA", "DO")}


def _mes(aaaa_mm_dd):
    return int(aaaa_mm_dd[:4]) * 100 + int(aaaa_mm_dd[5:7])


def quem(ocupantes, nome, inicio):
    """Índice (em `ocupantes`, na ordem do site) da pessoa no cargo no dia `inicio` cujo nome bate com `nome` (todas as
    palavras do nome curto, do civil ou do da folha estão no nome da fonte). Quem foi vice e depois governador: vale o
    cargo daquele dia. Fora do período em qualquer cargo: None."""
    tok = _tokens(nome)
    candidatos = []
    for i, o in enumerate(ocupantes):
        nomes = [o.get("folha_nome"), o.get("civil"), o.get("nome")]
        if not any(_tokens(n) and _tokens(n) <= tok for n in nomes if n):
            continue
        if o["de"] <= inicio and (not o.get("ate") or inicio <= o["ate"]):
            candidatos.append((o["de"], i))
    return max(candidatos)[1] if candidatos else None


def montar(uf, ocupantes):
    """(vg, sem_pessoa): as viagens do estado somadas por mês e pessoa, e quantas ficaram sem pessoa no cargo."""
    soma, sem = {}, 0
    for l in ler(uf):
        i = quem(ocupantes, l["nome"], l["inicio"])
        if i is None:
            sem += 1
            continue
        k = (_mes(l["inicio"]), i)
        s = soma.setdefault(k, [0.0, 0.0, 0.0, 0.0, 0])
        for j, c in enumerate(("diarias", "passagens", "outros", "devolucoes")):
            s[j] += float(l[c] or 0)
        s[4] += 1
    vg = [[am, i, round(s[0], 2), round(s[1], 2), round(s[2], 2), round(s[3], 2), s[4]] for (am, i), s in sorted(soma.items())]
    return vg, sem
