"""TCE-RJ: o total pago aos vereadores de cada Câmara do estado do Rio de Janeiro (91 municípios; a capital tem o próprio
Tribunal de Contas do Município e fica de fora).

Fonte: Portal de Dados Abertos do TCE-RJ (https://dados.tcerj.tc.br/), API documentada
(https://dados.tcerj.tc.br/api/v1/docs), "Situação Funcional": o que cada município manda ao Tribunal pelo sistema
e-TCERJ. Uma consulta por ano (?ano=AAAA&jsonfull=true, ~3 MB) traz, para cada unidade gestora (Câmara, Prefeitura,
fundos, institutos) e cada mês, cada situação funcional ("Agente Político", "Efetivo - Estatutário", "Comissionado
Extraquadro"...) com a quantidade de pessoas e a remuneração somada. Sem nomes e sem valor por pessoa. Sem login nem
chave; o robots.txt do portal não proíbe nada.

- Vereadores: a situação "Agente Político" na unidade gestora da Câmara ("CAMARA <cidade>"). É o que a Câmara informa
  como agente político: em uns 2 de cada 3 municípios a quantidade é a das cadeiras; nos outros, passa um pouco (suplente
  que assumiu, quem saiu no meio do mês) ou fica diferente. O site mostra a quantidade ao lado das cadeiras.
- Prefeito e vice ficam de fora: na Prefeitura, "Agente Político" junta o prefeito, o vice e os secretários.
- O valor é a remuneração somada, como a fonte chama ("Remuneracao"); os valores redondos (R$ 306.000 para 17 pessoas)
  indicam que é o bruto, antes dos descontos. Não separa 13º nem férias.
- A unidade da Câmara vem escrita "CAMARA <cidade>" ou "CÂMARA ..."; as 91 câmaras estão na fonte (03/10/2026).
"""
import json
from datetime import timedelta
from urllib.parse import quote

from ..config import HOJE
from ..util import _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import cargo, comum

UF = "RJ"
PORTAL = "https://dados.tcerj.tc.br/"
API = "https://dados.tcerj.tc.br/api/v1/situacao_funcional"
# nomes que o TCE-RJ escreve diferente do IBGE (chave do nome no TCE -> nome no IBGE)
NOMES_DIFERENTES = {"TRAJANO DE MORAIS": "Trajano de Moraes"}
_ultimo_ente = {}


def _cidades():
    cid = comum.municipios(UF)
    for k, v in NOMES_DIFERENTES.items():
        if comum.chave_cidade(v) in cid:
            cid[k] = cid[comum.chave_cidade(v)]
    return cid


def _ano(ano):
    """Os registros do ano (lista de dicts), de uma vez."""
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(API, params={"ano": ano, "jsonfull": "true"}, timeout=300)
            r.raise_for_status()
            return json.loads(r.content.decode("utf-8-sig"))
        except Exception:  # noqa: BLE001
            if tentativa == 2:
                raise
            dormir(10 * (tentativa + 1))


def link(cod):
    """A consulta da cidade na API (o ano do último mês), em JSON."""
    ente = _ultimo_ente.get(cod)
    if not ente:
        return API
    return f"{API}?ano={HOJE.year if HOJE.month > 1 else HOJE.year - 1}&municipio={quote(ente)}&jsonfull=true"


def coletar():
    """Lê os anos desde 2025 e grava todos os meses (é pouco: uma consulta por ano)."""
    cidades = _cidades()
    linhas, blocos, sem, cods = [], [], set(), set()
    agora = comum.agora()
    ultimo_mes = int((HOJE.replace(day=1) - timedelta(days=1)).strftime("%Y%m"))
    for ano in range(comum.INICIO // 100, HOJE.year + 1):
        regs = _ano(ano)
        log(f"  TCE-RJ {ano}: {len(regs)} registros")
        contagem, por = {}, {}
        meses_ano = set()
        for x in regs:
            cid = cidades.get(comum.chave_cidade(x.get("Ente", "")))
            if cid is None:
                sem.add(x.get("Ente"))
                continue
            am = int(str(x["Anomes"]).replace("/", ""))
            meses_ano.add(am)
            cods.add(cid[0])  # só as cidades que o TCE-RJ fiscaliza (a capital fica de fora)
            ug = str(x.get("UnidadeGestora") or "")
            if not normalizar_nome(ug).startswith("CAMARA"):
                continue
            _ultimo_ente[cid[0]] = x["Ente"]
            k = (cid[0], "camara", am)
            contagem[k] = contagem.get(k, 0) + 1
            if x.get("SituacaoFuncional") != "Agente Político":
                continue
            p = por.setdefault(k, {"cod_ibge": cid[0], "municipio": cid[1], "orgao": "camara", "ano_mes": am,
                                   "papel": "vereador", "cargo": "Agente Político", "quantidade": 0, "valor_total": 0.0,
                                   "indenizatorio": None, "decimo": None, "ferias": None, "unidade": ug})
            p["quantidade"] += int(x.get("Quantidade") or 0)
            p["valor_total"] = round(p["valor_total"] + float(x.get("Remuneracao") or 0), 2)
        linhas += list(por.values())
        for am in sorted(m for m in meses_ano if m <= ultimo_mes):
            for c in sorted(cods):
                k = (c, "camara", am)
                blocos.append({"cod_ibge": c, "orgao": "camara", "ano_mes": am, "linhas_fonte": contagem.get(k, 0),
                               "pessoas": por[k]["quantidade"] if k in por else 0,
                               "url": f"{API}?ano={am // 100}&jsonfull=true", "lido_em": agora})
    if sem:
        log(f"  TCE-RJ: {len(sem)} entes sem código do IBGE: {', '.join(sorted(map(str, sem)))}")
    n, nb = cargo.gravar(UF, linhas, blocos)
    log(f"  TCE-RJ: {len(linhas)} linhas (Câmara e mês) em {nb} blocos")
    return len(linhas)


CFG = {
    "tribunal": "TCE-RJ",
    "fonte": "Tribunal de Contas do Estado do Rio de Janeiro (TCE-RJ), Portal de Dados Abertos: a situação funcional que "
             "cada município manda ao Tribunal (quantidade de pessoas e remuneração somada, por unidade e mês)",
    "url": PORTAL,
    "nota": "O Tribunal de Contas do Rio de Janeiro publica, para cada Câmara e cada mês, quantas pessoas estavam como "
            "agente político e a remuneração somada delas, como a Câmara informou. Não publica o valor de cada vereador "
            "nem os nomes: o valor por pessoa é uma média (o total dividido pela quantidade), e não o salário de um "
            "vereador.",
    "notas": ["A quantidade é a que a Câmara informou como agente político; pode ser diferente do número de cadeiras "
              "(suplente que assumiu, quem saiu no meio do mês).",
              "A capital tem o próprio Tribunal de Contas do Município e não está nesta fonte.",
              "Na Prefeitura, a fonte junta o prefeito, o vice e os secretários: prefeito e vice ficam de fora."],
    "orgaos": ("camara",),
    "link": link,
}


def montar():
    # sem a coleta nesta rodada, o nome do ente sai do nome da cidade, como o TCE-RJ escreve (maiúsculas, sem acento)
    cidades = comum.municipios(UF)
    diferentes = {comum.chave_cidade(v): k for k, v in NOMES_DIFERENTES.items()}
    for k, v in cidades.items():
        _ultimo_ente.setdefault(v[0], diferentes.get(k, k))
    return cargo.montar_site(UF, CFG)


checar = cargo.checar
