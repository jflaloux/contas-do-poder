"""Viagens dos governadores: coleta (todas as UFs com robô, ou só as dadas) e anexa e.vg/e.vgf ao governadores.json.

Uso: python3 -m coleta.viagens_governadores [UF ...] [--tempo=segundos] [--so-anexar]
--so-anexar: não coleta; só põe e.vg/e.vgf no site/dados/governadores.json que já existe, sem refazer o resto.
"""
import sys

from ..util import TempoEsgotado, definir_prazo
from . import coletar, so_anexar

args = sys.argv[1:]
tempo = next((int(a.split("=", 1)[1]) for a in args if a.startswith("--tempo=")), 0)
definir_prazo(tempo)
try:
    if "--so-anexar" not in args:
        coletar({a.upper() for a in args if not a.startswith("-")} or None)
except TempoEsgotado:
    print("tempo esgotado: rode de novo para continuar (o que já foi lido fica no cache)")
so_anexar()
