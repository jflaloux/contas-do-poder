"""Roda os robôs de coleta.

Uso:
    python3 coletar.py camara          # só a Câmara
    python3 coletar.py senado          # só o Senado
    python3 coletar.py padronizar      # junta tudo na base unificada
    python3 coletar.py conferir        # compara nossos números com os sites oficiais
    python3 coletar.py site            # gera site/dados/dados.json
    python3 coletar.py tudo            # camara + senado + padronizar + site

    --tempo-max 160   para parar sozinho depois de 160 s (rode de novo para continuar)
"""
import argparse
import sys

from coleta import camara, conferir, padronizar, senado, site
from coleta.util import TempoEsgotado, definir_prazo, log

ETAPAS = {
    "camara": camara.coletar,
    "senado": senado.coletar,
    "padronizar": padronizar.executar,
    "conferir": conferir.executar,
    "site": site.executar,
}


def main():
    ap = argparse.ArgumentParser(description="Coleta de dados públicos sobre políticos federais")
    ap.add_argument("etapa", choices=[*ETAPAS, "tudo"])
    ap.add_argument("--tempo-max", type=int, default=0, help="segundos (0 = sem limite)")
    args = ap.parse_args()
    definir_prazo(args.tempo_max)
    etapas = ["camara", "senado", "padronizar", "site"] if args.etapa == "tudo" else [args.etapa]
    try:
        for etapa in etapas:
            ETAPAS[etapa]()
    except TempoEsgotado:
        log("Tempo máximo atingido. Rode o mesmo comando de novo para continuar de onde parou.")
        sys.exit(3)


if __name__ == "__main__":
    main()
