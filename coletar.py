"""Roda os robôs de coleta.

Uso:
    python3 coletar.py camara          # só a Câmara
    python3 coletar.py senado          # só o Senado
    python3 coletar.py executivo       # presidente, vice e ministros (Portal da Transparência)
    python3 coletar.py municipios      # câmaras municipais: custo (Tesouro) e vereadores eleitos (TSE)
    python3 coletar.py vereadores      # capitais (São Paulo, Fortaleza, Goiânia, Manaus, Natal, Recife): cada vereador,
                                       # com salário, verba do gabinete e equipe (vereadores_sp é o nome antigo)
    python3 coletar.py prefeitura_sp   # São Paulo (capital): prefeito, vice, secretários e subprefeitos, mês a mês
    python3 coletar.py padronizar      # junta tudo na base unificada
    python3 coletar.py fotos           # baixa as fotos que faltam para site/fotos/
    python3 coletar.py conferir        # compara nossos números com os sites oficiais
    python3 coletar.py site            # gera site/dados/dados.json
    python3 coletar.py tudo            # camara + senado + executivo + municipios + vereadores + prefeitura_sp + padronizar + fotos + site

    --tempo-max 160   para parar sozinho depois de 160 s (rode de novo para continuar)
    --max-alertas 8   (com "conferir") termina com erro se a conferência passar desse número;
                      é o que trava a publicação automática no GitHub Actions
"""
import argparse
import sys

from coleta import camara, conferir, executivo, fotos, municipios, padronizar, prefeitura_sp, senado, site, vereadores
from coleta.config import FIM_LEGISLATURA, LEGISLATURA, LEGISLATURA_ENCERRADA
from coleta.util import TempoEsgotado, definir_prazo, log

ETAPAS = {
    "camara": camara.coletar,
    "senado": senado.coletar,
    "executivo": executivo.coletar,
    "municipios": municipios.coletar,
    "vereadores": vereadores.coletar,
    "vereadores_sp": vereadores.coletar,  # nome antigo (quando só havia São Paulo)
    "prefeitura_sp": prefeitura_sp.coletar,
    "padronizar": padronizar.executar,
    "fotos": fotos.coletar,
    "conferir": conferir.executar,
    "site": site.executar,
}


def main():
    ap = argparse.ArgumentParser(description="Coleta de dados públicos sobre políticos federais")
    ap.add_argument("etapa", choices=[*ETAPAS, "tudo"])
    ap.add_argument("--tempo-max", type=int, default=0, help="segundos (0 = sem limite)")
    ap.add_argument("--max-alertas", type=int, default=None, help="com 'conferir': erro se passar deste número")
    args = ap.parse_args()
    if LEGISLATURA_ENCERRADA and args.etapa in ("camara", "senado", "executivo", "tudo"):
        log(f"A legislatura {LEGISLATURA} terminou em {FIM_LEGISLATURA[1]:02d}/{FIM_LEGISLATURA[0]}. "
            "Atualize coleta/config.py para a nova legislatura antes de coletar de novo.")
        sys.exit(5)
    definir_prazo(args.tempo_max)
    etapas = ["camara", "senado", "executivo", "municipios", "vereadores", "prefeitura_sp", "padronizar", "fotos", "site"] if args.etapa == "tudo" else [args.etapa]
    try:
        for etapa in etapas:
            resultado = ETAPAS[etapa]()
            if etapa == "conferir" and args.max_alertas is not None and resultado > args.max_alertas:
                log(f"Conferência com {resultado} alertas (máximo {args.max_alertas}). Veja dados/processados/conferencia.md.")
                sys.exit(4)
    except TempoEsgotado:
        log("Tempo máximo atingido. Rode o mesmo comando de novo para continuar de onde parou.")
        sys.exit(3)


if __name__ == "__main__":
    main()
