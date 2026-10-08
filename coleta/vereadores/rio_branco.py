"""Câmara Municipal de Rio Branco: vereador por vereador, pelo robô comum do portal portaltp (ver portaltp.py).

Fontes: o Portal da Transparência da Câmara (https://cmriobranco-ac.portaltp.com.br/), "Dados Abertos > Servidores"
(folha mensal em JSON, com as parcelas de cada um) e o SAPL da Câmara (https://sapl.riobranco.ac.leg.br/, mandatos, nome
parlamentar e foto). A equipe de cada vereador: o centro de custo "GAB VEREADOR <nome>" na folha. A verba indenizatória
(Lei 1.856/2011) não aparece nas liquidações a vereadores nem tem página com dados: fica de fora.

Plano de queda (escrito em 08/10/2026, também em dados/referencia/plano-de-queda.json): portal fora do ar ou com outro
formato: o robô mantém o que já gravou (gravação segura) e o site fica até o último mês lido; SAPL fora do ar: ficam os
mandatos gravados e o "no cargo" sai da folha; sem reserva no Tribunal de Contas; passou de 1 hora, congelar.
"""
import re

from ..config import DADOS
from ..util import normalizar_nome
from . import portaltp

COD = 1200401
PORTAL = "https://cmriobranco-ac.portaltp.com.br"
SAPL = "https://sapl.riobranco.ac.leg.br"
PASTA = DADOS / "municipios" / "rio_branco"
VAGAS = 21


def _gabinete(x):
    """O gabinete de um servidor: o centro de custo "007072-GAB. VEREADOR ZE LOPES" (os outros centros não são gabinete)."""
    cc = " ".join(str(x.get("centro_custo") or "").split())
    return cc if re.search(r"\bGAB\b.*VEREADOR|\bGAB\b.*PRESIDENTE", normalizar_nome(cc)) else None


CFG = {
    "cod": COD, "n": "Rio Branco", "uf": "AC", "vagas": VAGAS, "inicio": 202501, "pasta": PASTA, "cache": "cmrb",
    "portal": PORTAL, "sapl": SAPL, "pagina": f"{SAPL}/parlamentar/", "gabinete": _gabinete, "verba_liquidacoes": False,
    "site": {
        "cod": COD, "n": "Rio Branco", "uf": "AC", "casa": "Câmara Municipal de Rio Branco", "vagas": VAGAS, "inicio": 202501,
        "subsidio": [[202501, 20069.09], [202602, 20864.78]],
        "salario_nota": ("Valor do mês na folha da Câmara, parcela por parcela: o salário base (o subsídio: R$ 20.069,09 até "
                         "jan/2026 e R$ 20.864,78 desde fev/2026, o valor da folha), "
                         "\"outros vencimentos\" (a folha não diz o que são; R$ 5.500 para a maioria), o auxílio-alimentação, "
                         "férias e 13º. Sem os descontos."),
        "verba_nome": None, "verba_mes": {},
        "equipe_nota": ("Servidores do centro de custo do gabinete do vereador na folha da Câmara, com o custo bruto (todas as "
                        "parcelas pagas, antes dos descontos). O gabinete da Presidência não entra."),
        "credito_foto": "Câmara Municipal de Rio Branco", "pagina": f"{SAPL}/parlamentar/",
        "notas": ["Quem estava no cargo em cada mês: quem está na folha da Câmara no mês com o salário base (ou as férias). Quem está em "
                  "exercício hoje: quem está na folha do último mês e tem mandato em vigor no SAPL da Câmara.",
                  "A verba indenizatória (Lei 1.856/2011) não aparece nos dados abertos da Câmara (nem nas liquidações a "
                  "vereadores): fica de fora."],
        "fontes": {"folha": f"{PORTAL}/consultas/pessoal/servidores.aspx", "api": f"{PORTAL}/api/pessoal/api-servidores.aspx",
                   "mandatos": f"{SAPL}/parlamentar/"},
    },
}


def coletar():
    portaltp.coletar(CFG)


def montar(tipos):
    return portaltp.montar(CFG, tipos)
