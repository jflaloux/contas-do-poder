"""Roda os robôs de coleta.

Uso:
    python3 coletar.py camara          # só a Câmara
    python3 coletar.py senado          # só o Senado
    python3 coletar.py executivo       # presidente, vice e ministros (Portal da Transparência)
    python3 coletar.py municipios      # câmaras municipais: custo (Tesouro) e vereadores eleitos (TSE)
    python3 coletar.py vereadores      # capitais (São Paulo, Rio, Belo Horizonte, Fortaleza, Goiânia, Maceió, Manaus, Natal, Porto Alegre,
                                       # Recife, São Luís, Aracaju, Boa Vista): cada vereador,
                                       # com salário, verba do gabinete e equipe (vereadores_sp é o nome antigo)
    python3 coletar.py prefeituras     # São Paulo, Rio (só prefeito e vice), Recife, Fortaleza, Vitória, Porto Alegre, Salvador,
                                       # Curitiba, Natal e Campo Grande: prefeito, vice e secretários (e subprefeitos, em SP), mês a mês,
                                       # pela folha (prefeitura_sp é o nome antigo)
    python3 coletar.py governadores    # os 27 governadores e vices: salário pela lei (dados/governadores/governadores.json)
                                       # e, em 24 estados, o mês a mês pela folha (coleta/folhas_estaduais/)
    python3 coletar.py assembleias     # deputados estaduais das 27 Assembleias: subsídio pela lei ou pela folha, verba do gabinete
                                       # com fornecedores, em site/dados/assembleias.json (dados/assembleias/)
    python3 coletar.py indice          # Índice de Transparência dos estados (dados/indice/), em site/dados/indice_transparencia.json
    python3 coletar.py renda           # distribuição da renda de quem trabalha (PNAD Contínua do IBGE), para o "ganha
                                       # mais que X% dos brasileiros que trabalham"; só baixa (~900 MB) quando sai um
                                       # trimestre novo
    python3 coletar.py padronizar      # junta tudo na base unificada
    python3 coletar.py fotos           # baixa as fotos que faltam para site/fotos/
    python3 coletar.py conferir        # compara nossos números com os sites oficiais
    python3 coletar.py site            # gera site/dados/dados.json
    python3 coletar.py situacao        # relatório de cada fonte: último mês no site, última coleta certa, falhas
                                       # (dados/processados/situacao.md)
    python3 coletar.py tce             # Tribunais de Contas: vereadores, prefeito, vice e (PB) secretários de todas as cidades da
                                       # Paraíba e do Ceará, mês a mês (dados/municipios_tce/, site/dados/interior/<uf>.json)
    python3 coletar.py judiciario      # ministros do STF, STJ, TST, STM e TSE, conselheiros do CNJ e o PGR, mês a mês
                                       # (dados/judiciario/, site/dados/judiciario.json)
    python3 coletar.py tudo            # camara + senado + executivo + municipios + vereadores + prefeituras + governadores + assembleias + tce
                                       # + judiciario + indice
                                       # + renda + padronizar + fotos + site + situacao
    python3 coletar.py montar          # só refaz os arquivos do site das capitais, Assembleias e governadores (sem coletar),
                                       # os endereços e o relatório de situação
    python3 coletar.py brasil          # a rodada do Brasil (rotina/semana-brasil.sh): só as fontes que o exterior não
                                       # pega (coleta/onde.py), e depois os arquivos do site que dependem delas

    No GitHub Actions (CONTAS_ONDE=exterior), "tudo" pula as fontes que só abrem do Brasil (coleta/onde.py).

    --tempo-max 160   para parar sozinho depois de 160 s (rode de novo para continuar)
    --max-alertas 8   (com "conferir") termina com erro se a conferência passar desse número;
                      é o que trava a publicação automática no GitHub Actions
"""
import argparse
import sys

from coleta import (assembleias, camara, conferir, enderecos, executivo, fotos, governadores, indice, municipios, onde, padronizar, prefeituras,
                    judiciario, renda, senado, site, situacao, tce, vereadores)
from coleta.config import FIM_LEGISLATURA, LEGISLATURA, LEGISLATURA_ENCERRADA
from coleta.util import TempoEsgotado, definir_prazo, log

ETAPAS = {
    "camara": camara.coletar,
    "senado": senado.coletar,
    "executivo": executivo.coletar,
    "municipios": municipios.coletar,
    "vereadores": vereadores.coletar,
    "vereadores_sp": vereadores.coletar,  # nome antigo (quando só havia São Paulo)
    "prefeituras": prefeituras.coletar,
    "prefeitura_sp": prefeituras.coletar,  # nome antigo (quando só havia São Paulo)
    "governadores": governadores.coletar,
    "assembleias": assembleias.coletar,
    "tce": tce.coletar,
    "judiciario": judiciario.coletar,
    "indice": indice.executar,
    "renda": renda.executar,
    "padronizar": padronizar.executar,
    "fotos": fotos.coletar,
    "conferir": conferir.executar,
    "site": site.executar,
    "situacao": situacao.executar,
}
# etapas de uma fonte só (federais): a tentativa e o resultado vão para dados/processados/coletas_<lugar>.json
FEDERAIS = {"camara", "senado", "executivo", "municipios", "renda"}


def montar():
    """Refaz, sem coletar nada, os arquivos do site que vêm dos CSVs de dados/ (capitais, Assembleias, governadores),
    os endereços e o relatório de situação. É o que resolve um conflito do Git nesses arquivos: eles saem dos CSVs."""
    vereadores.executar_site()
    tce.executar_site()
    judiciario.executar_site(baixar_fotos=False)
    prefeituras.executar_site(baixar_fotos=False)
    assembleias.executar_site(baixar_fotos=False)
    governadores.executar(baixar_fotos=False)
    enderecos.executar()
    return situacao.executar()


def rodada_brasil():
    """A rodada do Brasil: as fontes que só abrem do Brasil (e as que falharam de fora nesta semana), depois os arquivos
    do site que dependem delas, os endereços e o relatório de situação. Não mexe na base federal (dados.json)."""
    onde.SO_O_QUE_FALTA = True
    for etapa in (vereadores.coletar, prefeituras.coletar, assembleias.coletar, governadores.coletar, tce.coletar, judiciario.coletar):
        etapa()
    enderecos.executar()
    return situacao.executar()


def main():
    ap = argparse.ArgumentParser(description="Coleta de dados públicos sobre políticos (federais, governadores, prefeituras e câmaras)")
    ap.add_argument("etapa", choices=[*ETAPAS, "tudo", "brasil", "montar"])
    ap.add_argument("--tempo-max", type=int, default=0, help="segundos (0 = sem limite)")
    ap.add_argument("--max-alertas", type=int, default=None, help="com 'conferir': erro se passar deste número")
    args = ap.parse_args()
    if LEGISLATURA_ENCERRADA and args.etapa in ("camara", "senado", "executivo", "tudo"):
        log(f"A legislatura {LEGISLATURA} terminou em {FIM_LEGISLATURA[1]:02d}/{FIM_LEGISLATURA[0]}. "
            "Atualize coleta/config.py para a nova legislatura antes de coletar de novo.")
        sys.exit(5)
    definir_prazo(args.tempo_max)
    etapas = (["camara", "senado", "executivo", "municipios", "vereadores", "prefeituras", "governadores", "assembleias", "tce", "judiciario", "indice", "renda", "padronizar",
               "fotos", "site", "situacao"]
              if args.etapa == "tudo" else [args.etapa])
    try:
        if args.etapa in ("brasil", "montar"):
            (rodada_brasil if args.etapa == "brasil" else montar)()
            return
        for etapa in etapas:
            if etapa in FEDERAIS:
                if onde.pular("federal", etapa):
                    continue
                with onde.registrar("federal", etapa):
                    resultado = ETAPAS[etapa]()
                continue
            resultado = ETAPAS[etapa]()
            if etapa == "conferir" and args.max_alertas is not None and resultado > args.max_alertas:
                log(f"Conferência com {resultado} alertas (máximo {args.max_alertas}). Veja dados/processados/conferencia.md.")
                sys.exit(4)
    except TempoEsgotado:
        log("Tempo máximo atingido. Rode o mesmo comando de novo para continuar de onde parou.")
        sys.exit(3)


if __name__ == "__main__":
    main()
