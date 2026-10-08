"""Câmara Municipal de Porto Velho: vereador por vereador, pelo robô comum do portal portaltp (ver portaltp.py).

Fontes: o Portal da Transparência da Câmara (https://cmportovelho-ro.portaltp.com.br/), "Dados Abertos > Servidores"
(folha mensal em JSON, com as parcelas de cada um) e "Liquidações" (a verba indenizatória: as liquidações do elemento
3.3.90.93.01 a cada vereador), e o SAPL da Câmara (https://sapl.portovelho.ro.leg.br/, mandatos, nome parlamentar e foto).
A equipe de cada vereador: a lotação "GAB. <nome>" na folha (o vereador está lotado no próprio gabinete).

Plano de queda (escrito em 08/10/2026, também em dados/referencia/plano-de-queda.json): portal fora do ar ou com outro
formato: o robô mantém o que já gravou (gravação segura) e o site fica até o último mês lido (a verba, até o último mês
liquidado: verba_ate); SAPL fora do ar: ficam os mandatos gravados e o "no cargo" sai da folha; sem reserva no Tribunal de
Contas; passou de 1 hora, congelar.
"""
from ..config import DADOS
from ..util import normalizar_nome
from . import portaltp

COD = 1100205
PORTAL = "https://cmportovelho-ro.portaltp.com.br"
SAPL = "https://sapl.portovelho.ro.leg.br"
PASTA = DADOS / "municipios" / "porto_velho"
VAGAS = 23


def _gabinete(x):
    """O gabinete de um servidor: a lotação "GAB. <nome do vereador>" (as comissões e os setores não são gabinete)."""
    local = " ".join(str(x.get("local") or "").split())
    return local if normalizar_nome(local).startswith("GAB") else None


CFG = {
    "cod": COD, "n": "Porto Velho", "uf": "RO", "vagas": VAGAS, "inicio": 202501, "pasta": PASTA, "cache": "cmpvh",
    "portal": PORTAL, "sapl": SAPL, "pagina": f"{SAPL}/parlamentar/", "gabinete": _gabinete, "verba_liquidacoes": True,
    "verba_tipo": "Verba indenizatória (liquidação do mês)",
    "site": {
        "cod": COD, "n": "Porto Velho", "uf": "RO", "casa": "Câmara Municipal de Porto Velho", "vagas": VAGAS, "inicio": 202501,
        "subsidio": [[202501, 20864.78]],
        "salario_nota": ("Valor do mês na folha da Câmara, parcela por parcela: o salário base (o subsídio, R$ 20.864,78), "
                         "vantagens pessoais, outras remunerações, indenizações, férias e 13º (o valor da folha). Sem os descontos."),
        "verba_nome": "Verba indenizatória", "verba_mes": {},
        "verba_regra": "Ressarcimento de despesas do mandato, pago ao vereador; aqui, pelo valor que a Câmara liquida a cada um no mês.",
        "verba_notas": ["As liquidações da Câmara (elemento 3.3.90.93.01, indenizações) a cada vereador, no mês da liquidação. Os "
                        "dados abertos não trazem as notas nem os fornecedores.",
                        "O mês é o da liquidação, não o da despesa: há meses sem liquidação e meses com duas. A média por mês "
                        "divide o total pelo número de meses no cargo."],
        "equipe_nota": ("Servidores lotados no gabinete do vereador na folha da Câmara, com o custo bruto (todas as parcelas "
                        "pagas, antes dos descontos). O gabinete da Presidência e as comissões não entram."),
        "credito_foto": "Câmara Municipal de Porto Velho", "pagina": f"{SAPL}/parlamentar/",
        "notas": ["Quem estava no cargo em cada mês: quem está na folha da Câmara no mês com o salário base (ou as férias: em "
                  "jan/2026 a folha traz só as férias de todos os vereadores). Quem está em "
                  "exercício hoje: quem está na folha do último mês e tem mandato em vigor no SAPL da Câmara."],
        "fontes": {"folha": f"{PORTAL}/consultas/pessoal/servidores.aspx", "api": f"{PORTAL}/api/pessoal/api-servidores.aspx",
                   "verba": f"{PORTAL}/api/despesas/api-liquidacoes.aspx", "mandatos": f"{SAPL}/parlamentar/"},
    },
}


def coletar():
    portaltp.coletar(CFG)


def montar(tipos):
    return portaltp.montar(CFG, tipos)
