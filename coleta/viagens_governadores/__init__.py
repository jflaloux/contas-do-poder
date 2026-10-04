"""Viagens a serviço dos governadores e vices (diárias e passagens), onde o Estado publica por pessoa.

Cada módulo cuida de um estado: coletar(nomes) lê a fonte e grava dados/governadores/viagens/<uf>.csv (vai para o Git;
uma linha por viagem, sem CPF), e o site recebe, em site/dados/governadores.json, para cada estado com robô:
    e.vg  = [[aaaamm, índice em e.oc, diárias, passagens, outros, devoluções, número de viagens], ...]
    e.vgf = {"u": a página da fonte, "nota": o que a fonte mostra, "desde": AAAAMM, "ate": AAAAMM (o último mês lido)}
O mês é o do início da viagem, como nos ministros. Os nomes procurados são os do arquivo curado
(dados/governadores/governadores.json: folha_nome, civil e nome) e, onde a fonte escreve o nome inteiro, os de
NOMES_FONTE. O levantamento dos 27 estados está em dados/referencia/viagens_governadores.json.

    python3 -m coleta.viagens_governadores [UF ...]       coleta (todas ou só as UFs dadas) e anexa ao governadores.json
    python3 -m coleta.viagens_governadores --so-anexar    só anexa e.vg/e.vgf ao site/dados/governadores.json que existe
"""
import json
import sys

from .. import onde
from ..config import DADOS, RAIZ
from ..util import TempoEsgotado, gravar_json, log, normalizar_nome
from . import am, comum, mg, pb, se, sp

ESTADOS = {"AM": am, "MG": mg, "PB": pb, "SE": se, "SP": sp}
CURADO = DADOS / "governadores" / "governadores.json"
SITE = RAIZ / "site" / "dados" / "governadores.json"
# nomes inteiros como a fonte escreve, quando o arquivo curado não os tem (governador e vice desde 2025)
NOMES_FONTE = {
    "MG": ["ROMEU ZEMA NETO", "MATEUS SIMOES DE ALMEIDA"],
    "PB": ["JOAO AZEVEDO LINS FILHO", "LUCAS RIBEIRO NOVAIS DE ARAUJO"],
    "SP": ["TARCISIO GOMES DE FREITAS", "FELICIO RAMUTH"],
}


def _curado():
    return {e["uf"]: e for e in json.loads(CURADO.read_text(encoding="utf-8"))}


def ocupantes_ordenados(e):
    """Os ocupantes na ordem de "oc" do site (a mesma de governadores.executar)."""
    return sorted(e["ocupantes"], key=lambda o: (o["de"], {"gov": 0, "exercicio": 0, "vice": 1}[o["cargo"]]))


def nomes(uf, e):
    ns = {normalizar_nome(o.get(k)) for o in e["ocupantes"] for k in ("folha_nome", "civil") if o.get(k)}
    return ns | {normalizar_nome(n) for n in NOMES_FONTE.get(uf, [])}


def coletar(ufs=None):
    curado = _curado()
    for uf, m in ESTADOS.items():
        if ufs and uf not in ufs:
            continue
        if onde.pular("viagens", uf):
            continue
        try:
            with onde.registrar("viagens", uf):
                n = m.coletar(nomes(uf, curado[uf]))
            log(f"  Viagens {uf}: {n} viagens do governador e do vice desde {comum.INICIO % 100:02d}/{comum.INICIO // 100}")
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — um estado fora do ar não para os outros
            log(f"  Viagens {uf}: a coleta falhou ({e}); o site usa o que já estava gravado")


def anexar(estado_site, curado_uf):
    """Acrescenta e.vg e e.vgf ao estado do site (o dict de governadores.json), se o estado tem robô e dados."""
    uf = estado_site["uf"]
    m = ESTADOS.get(uf)
    if not m or not comum.arquivo(uf).exists():
        return estado_site
    vg, sem = comum.montar(uf, ocupantes_ordenados(curado_uf))
    if sem:
        log(f"  Viagens {uf}: {sem} viagens fora dos períodos no cargo (não entram)")
    estado_site["vg"] = vg
    estado_site["vgf"] = {"u": m.FONTE, "nota": m.NOTA, "desde": comum.INICIO, "ate": comum.lido_ate(uf)}
    return estado_site


def so_anexar():
    """Põe e.vg/e.vgf no site/dados/governadores.json que já existe, sem refazer o resto (refazer o arquivo fora da
    rodada muda mais do que se quer: o último mês fechado avança, notas mudam)."""
    dados = json.loads(SITE.read_text(encoding="utf-8"))
    curado = _curado()
    for e in dados["e"]:
        anexar(e, curado[e["uf"]])
    gravar_json(SITE, dados)
    log(f"Site: {SITE.relative_to(RAIZ)}: viagens anexadas em {', '.join(e['uf'] for e in dados['e'] if 'vg' in e)}")

