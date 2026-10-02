"""TCE-CE: a folha de pagamento de todas as prefeituras e câmaras do Ceará (184 municípios).

Fonte: API de Dados Abertos do SIM, o sistema pelo qual os municípios mandam as contas ao Tribunal de Contas do Ceará
(https://api-dados-abertos.tce.ce.gov.br/sim/, documentada em OpenAPI; manual do SIM, com as tabelas de códigos, em
https://www.tce.ce.gov.br/municipios/sim/documentacao-e-programas). Sem login nem chave; até 1.000 registros por
pedido. Por município e mês:

- /folhas_pagamentos: o total de cada folha (por órgão e unidade): diz se o município já mandou a folha do mês e
  serve para conferir a soma do que lemos;
- /agentes_publicos_folha: cada item pago a cada pessoa (salário, subsídio, 13º, férias... e também os descontos,
  que não são lidos), com o CPF cifrado e o tipo de vínculo ("L" = cargo eletivo), mas sem o nome;
- /agentes_publicos_municipais: o cadastro de cada pessoa (nome, cargo e o tipo do cargo pela tabela do SIM: 00 =
  prefeito, 01 = vice-prefeito, 02 = presidente da Câmara, 58 = vereador). Em janeiro vem o cadastro inteiro; nos
  outros meses, só quem entrou ou mudou;
- /itens_remuneratorios: o nome de cada item (o código é do município).

A folha e o cadastro são ligados pelo CPF cifrado, só na memória, durante a leitura de cada município: o CPF (nem o
cifrado) nunca é gravado, nem no cache. Por isso cada leitura pede de novo o cadastro de janeiro, só dos órgãos que
interessam: a Câmara, o gabinete do prefeito e a prefeitura (tipos de unidade 01 e 00) e onde o prefeito e o vice
estavam da última vez. O cadastro inteiro só é lido quando o prefeito não está em nenhum deles.

- Vereadores: quem tem cargo eletivo (vínculo "L") na folha ou no cadastro da Câmara, ou o cargo de vereador pelo
  nome (ver _papel: o tipo de cargo 58 sozinho não basta). O tipo 02 (presidente da Câmara) vai no fim do cargo.
- Prefeito e vice: tipo de cargo 00 e 01 no cadastro, com o vínculo eletivo ou o nome do cargo (ver
  _eh_prefeito_ou_vice), fora da Câmara. O órgão e a unidade de cada um (o Gabinete, quase sempre) ficam guardados em
  dados/cache/tce/ce/postos/ para as próximas vezes.
- Bruto = soma dos itens remuneratórios (orçamentários e extraorçamentários) de todas as folhas do mês (normal,
  complementar e 13º), separado em salário, 13º (a folha de 13º ou o item com esse nome), férias e outros. Descontos
  (imposto, previdência, empréstimos) não são lidos.
- Secretários municipais ficam de fora: no cadastro são fáceis de achar (tipo de cargo 03, vínculo "S"), mas o valor
  está na folha de cada secretaria, com milhares de pessoas (a API não filtra por pessoa nem por vínculo): seria
  preciso ler a folha inteira de cada município todo mês.
- Ritmo: no máximo 2 pedidos ao mesmo tempo, com pausa, e até MAX_TAREFAS tarefas por rodada (a rodada semanal
  normal, com os 2 últimos meses dos 184 municípios, tem umas 190). Ver a nota sobre o bloqueio em PAUSA.
- A API não ordena os registros: sem ordem, as páginas de 1.000 se repetem e pulam registros (no cadastro de janeiro
  de Juazeiro do Norte, 9.988 linhas lidas e só ~7.400 diferentes). Por isso todo pedido vai com $orderby (aceito
  pela API, fora da documentação), e a soma do que lemos é conferida com o total de cada folha.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ..folhas_estaduais.comum import classificar
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

UF = "CE"
API = "https://api-dados-abertos.tce.ce.gov.br/sim"
CACHE = comum.CACHE_TCE / "ce"
# Em 02/10/2026, depois de umas 3 horas de leitura com 3 pedidos ao mesmo tempo e 0,1 s de pausa (a primeira leitura,
# de jan/2025 em diante), os endereços do TCE-CE pararam de responder ao Mac por uns 12 minutos (a conexão caía antes
# da resposta; de fora do Brasil continuavam abrindo). Por isso o ritmo agora é bem mais lento, e o robô para quando
# vários municípios seguidos dão erro (FALHAS_MAX).
PAUSA = 0.5        # segundos entre pedidos, em cada uma das linhas de leitura
PARALELO = 2       # municípios lidos ao mesmo tempo (no máximo 2 pedidos simultâneos)
MAX_TAREFAS = 250  # tarefas (município e até 6 meses) por rodada: a primeira leitura se divide em algumas semanas
FALHAS_MAX = 5     # municípios seguidos com erro de conexão: o robô para (o tribunal pode estar bloqueando) e a fonte
                   # fica como falhando em coleta/onde.py
MESES_POR_VEZ = 6  # cada tarefa lê até 6 meses de um município (e grava): assim a coleta em partes não perde muito
ORDEM = {
    "agentes_publicos_municipais": "cpf_servidor,codigo_orgao,codigo_unidade_orcamentaria,numero_matricula,tipo_cargo,"
                                   "data_posse,nm_tipo_cargo",
    "agentes_publicos_folha": "cpf_agente,codigo_orgao,codigo_unidade_orcamentaria,tipo_folha,data_emissao_folha,"
                              "codigo_item,valor_item",
    "folhas_pagamentos": "codigo_orgao,codigo_unidade_orcamentaria,tipo_folha,data_emissao_folha",
    "orgaos": "codigo_orgao",
    "municipios": "codigo_municipio",
    "itens_remuneratorios": "codigo_item,data_referencia_doc",
}
ELETIVOS = {"00": "prefeito", "01": "vice", "02": "vereador", "58": "vereador"}


def _api(ep, **params):
    """Todos os registros de uma consulta, de 1.000 em 1.000 (com $orderby, para as páginas não se repetirem)."""
    saida, inicio = [], 0
    while True:
        verificar_prazo()
        p = {**params, "$orderby": ORDEM[ep], "$start_index": inicio}
        for tentativa in range(4):
            try:
                r = _sessao().get(f"{API}/{ep}", params=p, timeout=120)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code} em {r.url}", response=r)
                r.raise_for_status()
                e = r.json()["elements"]
                break
            except (requests.RequestException, ValueError):
                if tentativa == 3:
                    raise
                dormir(5 * (tentativa + 1))
        dormir(PAUSA)
        saida += e
        if len(e) < 1000:
            return saida
        inicio += 1000


def url_folha(cod, ano_mes, orgao, uo=None):
    u = (f"{API}/agentes_publicos_folha?codigo_municipio={cod}&exercicio_orcamento={ano_mes // 100}00"
         f"&data_referencia_doc={ano_mes}&codigo_orgao={orgao}")
    return u + (f"&codigo_unidade_orcamentaria={uo}" if uo else "")


def _cache_json(nome, max_dias, gerar):
    a = CACHE / nome
    if a.exists() and (max_dias is None or time.time() - a.stat().st_mtime < max_dias * 86400):
        return json.loads(a.read_text(encoding="utf-8"))
    d = gerar()
    a.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(a)
    return d


def municipios():
    """[(código do TCE, código do IBGE, nome)] dos 184 municípios (a API dá o código do IBGE de cada um)."""
    lista = _cache_json("municipios.json", 30, lambda: [[x["codigo_municipio"], x["codigo_municipio_ibge"], x["nome_municipio"]]
                                                          for x in _api("municipios") if x.get("codigo_municipio_ibge")])
    return [(c, int(i), n) for c, i, n in lista]


def _orgaos(cod, ano):
    """[(código, nome, tipo de unidade)] dos órgãos do município no ano (02 = Câmara Municipal)."""
    from ..config import HOJE
    dias = 7 if ano >= HOJE.year else None
    return _cache_json(f"orgaos/{cod}_{ano}.json", dias, lambda: [[o["codigo_orgao"], o["nome_orgao"].strip(), o["codigo_tipo_unidade"]]
                                                                  for o in _api("orgaos", codigo_municipio=cod, exercicio_orcamento=ano * 100)])


def _itens(cod):
    """{código do item: (tipo R/D, descrição)}."""
    return _cache_json(f"itens/{cod}.json", 30, lambda: {str(x["codigo_item"]): [x["tipo_item"], (x["descricao_item"] or "").strip()]
                                                        for x in _api("itens_remuneratorios", codigo_municipio=cod)})


GRANDE = 150_000  # habitantes: acima disso, o cadastro de cada mês é lido só dos órgãos que interessam
_POP = {}


def _populacao():
    if not _POP:
        _POP.update({v[0]: v[2] for v in comum.municipios(UF).values()})
    return _POP


def _postos_arquivo(cod, ano):
    return CACHE / "postos" / f"{cod}_{ano}.json"


class Cadastro:
    """O cadastro dos agentes públicos lido nesta execução (só na memória: tem o CPF cifrado)."""

    def __init__(self):
        self.por_cpf, self.meses = {}, set()

    def juntar(self, registros, ref):
        self.meses.add(ref)
        for x in registros:
            self.por_cpf.setdefault(x["cpf_servidor"], []).append({
                "ref": ref, "orgao": x["codigo_orgao"], "uo": (x["codigo_unidade_orcamentaria"] or "").strip(),
                "tipo": x["tipo_cargo"], "cargo": (x["nm_tipo_cargo"] or "").strip(), "vinculo": x["codigo_vinculo"],
                "nome": (x["nome_servidor"] or "").strip()})

    def achar(self, cpf, mes, orgao, preferir):
        """O registro mais adequado para a pessoa naquele mês: do mesmo órgão, o mais recente até o mês (o cadastro de
        fevereiro em diante só traz quem entrou ou mudou) e, no mesmo mês, o do tipo de cargo preferido."""
        regs = [r for r in self.por_cpf.get(cpf, []) if r["ref"] <= mes]
        if not regs:
            return None
        return max(regs, key=lambda r: (r["orgao"] == orgao, r["ref"],
                                        -preferir.index(r["tipo"]) if r["tipo"] in preferir else -99))


def _eh_prefeito_ou_vice(reg, eletivo):
    """"prefeito" ou "vice" pelo cadastro: o tipo de cargo 00/01 com o cargo eletivo (vínculo "L") ou com o nome do cargo
    batendo; ou o nome do cargo com o vínculo eletivo. Há municípios que marcam 00/01 em outro cargo (em Sobral, um
    "ASSISTENTE ESPECIAL", comissionado, vem com o tipo 01): sem o vínculo nem o nome do cargo, não entra."""
    eletivo = eletivo or reg["vinculo"] == "L"
    pelo_nome = comum.papel_prefeitura(reg["cargo"])
    if reg["tipo"] in ("00", "01") and (eletivo or pelo_nome):
        return ELETIVOS[reg["tipo"]]
    return pelo_nome if pelo_nome and eletivo else None


# cargos que não são de vereador (para o funcionário que a Câmara marcou com o vínculo eletivo por engano); os nomes
# genéricos que algumas câmaras usam para todos ("PADRÃO", "AGENTE PUBLICO", "SERVIDOR") não entram
_OUTRO_CARGO = re.compile(r"SERVICOSGERAIS|AUXILIAR|MOTORISTA|VIGIA|VIGILANTE|ZELADOR|PORTEIRO|RECEPCIONISTA|DIGITADOR|"
                          r"TECNICO|PROFESSOR|ENFERMEIR|TESOUREIR|CONTADOR|PROCURADOR|DIRETOR|COORDENADOR|ASSISTENTE|"
                          r"AGENTEADMINISTRATIVO|CHEFE|COPEIR|MERENDEIR|ESTAGIARI|GARI")


def _papel(reg, camara, eletivo, mesmo=True):
    """Na Câmara, vereador é quem tem o cargo eletivo (vínculo "L", na folha ou no cadastro) ou o cargo de vereador pelo
    nome. O tipo de cargo 58 (vereador) sozinho não basta: há câmaras que o usam para funcionários (em Aiuaba, "Agente
    Administrativo"; em Banabuiú, "PADRAO"), e há vereadores com outro tipo (90). `mesmo`: o registro do cadastro é do
    mesmo órgão da folha; se não for (a pessoa tem outro vínculo no município), só vale o que a folha diz."""
    if camara:
        c = comum.so_letras(reg["cargo"])
        if "TUTELAR" in c:
            return None  # conselheiro tutelar também é cargo eletivo (vínculo "L"), e há câmaras que o pagam
        if mesmo and reg["tipo"] not in ("02", "58") and _OUTRO_CARGO.search(c) and not comum.eh_vereador(reg["cargo"]):
            return None  # funcionário com o vínculo "L" por engano (em Potengi, "SERVICOS GERAIS", tipo de cargo 90)
        if eletivo or (mesmo and (reg["vinculo"] == "L" or comum.eh_vereador(reg["cargo"], eletivo=False))):
            return "vereador"
        return None
    return _eh_prefeito_ou_vice(reg, eletivo) if mesmo else None


ELETIVO_CAMARA = "CARGO ELETIVO NA FOLHA DA CÂMARA"


def _cargo(reg, papel, mesmo=True):
    """O cargo como o município escreveu; o tipo 02 da tabela do SIM (presidente da Câmara) entra no fim quando o nome
    do cargo não diz ("VEREADOR" -> "VEREADOR - PRESIDENTE DA CÂMARA"). Quando o único registro da pessoa no cadastro
    lido é de outro órgão (outro vínculo dela no município, como professora ou enfermeiro), o cargo é o que a folha da
    Câmara diz: cargo eletivo."""
    if not mesmo:
        return ELETIVO_CAMARA
    cargo = reg["cargo"]
    if papel == "vereador" and reg["tipo"] == "02" and not comum.eh_presidente(cargo):
        cargo = f"{cargo} - PRESIDENTE DA CÂMARA" if cargo else "PRESIDENTE DA CÂMARA"
    return cargo


def _parte(item, tipo_folha, itens):
    if tipo_folha in ("AD", "ID", "PD"):
        return "decimo"
    p = classificar(itens.get(str(item), ["", ""])[1])
    return "outros" if p == "beneficios" else p


def _municipio(cod, ibge, nome_cidade, fazer):
    """Lê os meses `fazer` ({mês: {"camara", "prefeitura"}}) de um município. Devolve (linhas, blocos, avisos)."""
    linhas, blocos, avisos = [], [], []
    itens = None
    for ano in sorted({m // 100 for m in fazer}):
        ms = sorted(m for m in fazer if m // 100 == ano)
        ex = ano * 100
        org = _orgaos(cod, ano)
        nomes_org = {o: n for o, n, _ in org}
        camaras = [o for o, n, t in org if t == "02" or "CAMARA" in normalizar_nome(n)]
        totais = {m: _api("folhas_pagamentos", codigo_municipio=cod, exercicio_orcamento=ex, data_referencia_doc=m) for m in ms}
        com = [m for m in ms if totais[m]]
        for m in ms:
            if not totais[m]:
                for orgao in fazer[m]:
                    blocos.append({"cod_ibge": ibge, "orgao": orgao, "ano_mes": m, "linhas_fonte": 0, "pessoas": 0,
                                   "url": f"{API}/folhas_pagamentos?codigo_municipio={cod}&exercicio_orcamento={ex}&data_referencia_doc={m}",
                                   "lido_em": comum.agora()})
        if not com:
            continue
        itens = itens or _itens(cod)
        cad = Cadastro()
        jan = ano * 100 + 1
        arq_postos = _postos_arquivo(cod, ano)
        postos = json.loads(arq_postos.read_text()) if arq_postos.exists() else None
        # o cadastro só dos órgãos que interessam: as câmaras, o gabinete do prefeito e a prefeitura (tipos 01 e 00 da
        # tabela de unidades do SIM) e onde o prefeito e o vice estavam da última vez (o cadastro inteiro de uma cidade
        # grande tem dezenas de milhares de linhas)
        alvo = list(dict.fromkeys(camaras + ([p[0] for p in postos] if postos else [o for o, _, t in org if t in ("00", "01")])))

        def cadastro(ref, orgaos):
            for o in orgaos:
                cad.juntar(_api("agentes_publicos_municipais", codigo_municipio=cod, exercicio_orcamento=ex,
                                data_referencia_doc=ref, codigo_orgao=o), ref)
            cad.meses.add(ref)

        def novos_postos(papel=None):
            achados = set()
            for regs in cad.por_cpf.values():
                for r in regs:
                    if r["orgao"] not in camaras and _eh_prefeito_ou_vice(r, False) in ((papel,) if papel else ("prefeito", "vice")):
                        achados.add((r["orgao"], r["uo"]))
            return achados

        cadastro(jan, alvo)
        if postos is None and not novos_postos("prefeito"):
            # primeira vez no ano e o prefeito não está no gabinete nem na prefeitura: o cadastro de janeiro inteiro
            cad.juntar(_api("agentes_publicos_municipais", codigo_municipio=cod, exercicio_orcamento=ex,
                            data_referencia_doc=jan), jan)

        def mais_cadastro(ate):
            """Os meses de fevereiro até `ate` que ainda não foram lidos (quem entrou ou mudou no ano): nas cidades
            grandes, só dos mesmos órgãos; nas outras, o do mês inteiro (quase sempre um pedido só)."""
            lidos = 0
            orgaos = list(dict.fromkeys(alvo + [o for o, _ in sorted(conhecidos)]))
            for ref in comum.meses(jan + 1, ate):
                if ref not in cad.meses:
                    if _populacao().get(ibge, 0) > GRANDE:
                        cadastro(ref, orgaos)
                    else:
                        cad.juntar(_api("agentes_publicos_municipais", codigo_municipio=cod, exercicio_orcamento=ex,
                                        data_referencia_doc=ref), ref)
                    lidos += 1
            return lidos

        conhecidos = set(map(tuple, postos or [])) | novos_postos()
        for m in com:
            orgaos_mes = {t["codigo_orgao"] for t in totais[m]}
            pedidos = {}  # (órgão, uo ou None) -> registros da folha
            for o in camaras:
                if o in orgaos_mes and "camara" in fazer[m]:
                    pedidos[(o, None)] = _api("agentes_publicos_folha", codigo_municipio=cod, exercicio_orcamento=ex,
                                              data_referencia_doc=m, codigo_orgao=o)

            def ler_prefeitura():
                for o, u in sorted(conhecidos):
                    if o in orgaos_mes and (o, u) not in pedidos and "prefeitura" in fazer[m]:
                        pedidos[(o, u)] = _api("agentes_publicos_folha", codigo_municipio=cod, exercicio_orcamento=ex,
                                               data_referencia_doc=m, codigo_orgao=o, codigo_unidade_orcamentaria=u)
            ler_prefeitura()
            # quem tem cargo eletivo na folha precisa estar no cadastro daquele órgão; senão, lê os meses seguintes do
            # cadastro (o suplente que assumiu em março está no cadastro de março)
            faltam = []
            for (o, u), regs in pedidos.items():
                for c in {x["cpf_agente"] for x in regs if x["codigo_vinculo"] == "L"}:
                    r = cad.achar(c, m, o, ["02", "58"] if o in camaras else ["00", "01"])
                    if r is None or r["orgao"] != o:
                        faltam.append(c)
            sem_prefeito = "prefeitura" in fazer[m] and not any(
                (r := cad.achar(x["cpf_agente"], m, o, ["00", "01"])) and _eh_prefeito_ou_vice(r, x["codigo_vinculo"] == "L") == "prefeito"
                for (o, u), regs in pedidos.items() if o not in camaras for x in regs)
            if (faltam or sem_prefeito) and m > jan and mais_cadastro(m):
                antes = set(conhecidos)
                conhecidos |= novos_postos()
                if conhecidos != antes:
                    ler_prefeitura()
            # confere a soma lida com o total de cada folha (órgão, unidade, tipo e data de emissão da folha)
            esperado, lido = {}, {}
            for t in totais[m]:
                k = (t["codigo_orgao"], t["codigo_unidade_orcamentaria"].strip(), t["tipo_folha"], t["data_emissao_folha"])
                esperado[k] = esperado.get(k, 0) + (t["valor_total_item_orc"] or 0)
            for (o, u), regs in pedidos.items():
                for x in regs:
                    if x["tipo_classificacao"] == "O":
                        k = (o, x["codigo_unidade_orcamentaria"].strip(), x["tipo_folha"], x["data_emissao_folha"])
                        lido[k] = lido.get(k, 0) + (x["valor_item"] or 0)
            for k, v in esperado.items():
                if any(k[0] == o and (u is None or k[1] == u) for o, u in pedidos) and abs(lido.get(k, 0) - v) > 1:
                    avisos.append(f"{nome_cidade} {m} órgão {k[0]}/{k[1]} folha {k[2]} de {k[3][:10]}: lemos "
                                  f"{lido.get(k, 0):.2f}, o total da folha é {v:.2f}")
            # pessoas
            gente = {}
            for (o, u), regs in pedidos.items():
                camara = o in camaras
                por_cpf = {}
                for x in regs:
                    por_cpf.setdefault(x["cpf_agente"], []).append(x)
                for cpf, xs in por_cpf.items():
                    eletivo = any(x["codigo_vinculo"] == "L" for x in xs)
                    reg = cad.achar(cpf, m, o, ["02", "58"] if camara else ["00", "01"])
                    if reg is None:
                        if eletivo:
                            avisos.append(f"{nome_cidade} {m}: pessoa com cargo eletivo na folha do órgão {o} sem cadastro")
                        continue
                    mesmo = reg["orgao"] == o
                    papel = _papel(reg, camara, eletivo, mesmo)
                    if not papel:
                        continue
                    orgao = "camara" if camara else "prefeitura"
                    p = gente.setdefault((cpf, orgao), {"cod_ibge": ibge, "municipio": nome_cidade, "orgao": orgao,
                                                         "ano_mes": m, "nome": reg["nome"].upper(), "cargo": _cargo(reg, papel, mesmo),
                                                         "papel": papel, "valor_bruto": 0.0, "salario": 0.0, "decimo": 0.0,
                                                         "ferias": 0.0, "outros": 0.0, "unidade": set()})
                    for x in xs:
                        if (x["tipo_classificacao"] or "").strip() not in ("O", "E"):
                            continue  # desconto: não é lido
                        v = float(x["valor_item"] or 0)
                        p["valor_bruto"] += v
                        p[_parte(x["codigo_item"], x["tipo_folha"], itens)] += v
                    if not camara:  # na Câmara, a unidade é sempre a própria Câmara
                        p["unidade"].add(nomes_org.get(o, o))
            pessoas_por = {"camara": 0, "prefeitura": 0}
            for p in gente.values():
                if p["valor_bruto"] <= 0:
                    continue
                pessoas_por[p["orgao"]] += 1
                linhas.append({**p, "valor_bruto": round(p["valor_bruto"], 2),
                               **{k: round(p[k], 2) or None for k in comum.PARTES},
                               "unidade": " / ".join(sorted(p["unidade"]))})
            for orgao in fazer[m]:
                if orgao == "camara":
                    regs = [x for (o, _), r in pedidos.items() if o in camaras for x in r]
                    url = url_folha(cod, m, camaras[0]) if camaras else None
                else:
                    regs = [t for t in totais[m] if t["codigo_orgao"] not in camaras]
                    pf = sorted(conhecidos)
                    url = url_folha(cod, m, pf[0][0], pf[0][1]) if pf else None
                blocos.append({"cod_ibge": ibge, "orgao": orgao, "ano_mes": m, "linhas_fonte": len(regs),
                               "pessoas": pessoas_por[orgao], "url": url, "lido_em": comum.agora()})
        arq_postos.parent.mkdir(parents=True, exist_ok=True)
        arq_postos.write_text(json.dumps(sorted(map(list, conhecidos))))
    return linhas, blocos, avisos


# Blocos lidos antes desta correção (02/10/2026), quando o cargo de um vereador podia vir de outro vínculo dele no
# município (professora, enfermeiro), e um conselheiro tutelar ou um funcionário marcado com o vínculo eletivo entrava
# como vereador: os que têm "vereador" com um cargo de outra função são lidos de novo, uma vez.
CORRECAO = "2026-10-02T15:50"


def _reler():
    df, f = comum.ler(UF), comum.ler_fontes(UF)
    if not len(df) or not len(f):
        return set()
    v = df[(df.papel == "vereador") & (df.cargo.fillna("") != ELETIVO_CAMARA)]
    v = v[[not comum.eh_vereador(c, eletivo=True) and bool(_OUTRO_CARGO.search(comum.so_letras(c))) for c in v.cargo.fillna("")]]
    suspeitos = set(zip(v.cod_ibge.astype(int), v.orgao, v.ano_mes.astype(int)))
    antigos = {(int(c), o, int(m)) for c, o, m, q in zip(f.cod_ibge, f.orgao, f.ano_mes, f.lido_em) if str(q) < CORRECAO}
    return suspeitos & antigos


def disponiveis():
    """Meses de jan/2025 até o mês passado (o que ainda não foi mandado vem vazio e é tentado de novo depois)."""
    from ..vereadores.comum import ultimo_mes_fechado
    return comum.meses(comum.INICIO, ultimo_mes_fechado())


def coletar(so=None):
    """Lê o que falta de cada município (3 por vez, até MESES_POR_VEZ meses por tarefa) e grava a cada 3 tarefas.
    `so`: lista de códigos do IBGE (para testar)."""
    nomes = {v[0]: v[1] for v in comum.municipios(UF).values()}
    lista = municipios()
    fora = [f"{n} ({i})" for _, i, n in lista if i not in nomes]
    if fora:
        log(f"  TCE-CE: {len(fora)} códigos do IBGE da API que não estão na lista do IBGE: {', '.join(fora)}")
    lista = [(c, i, nomes.get(i, n.title())) for c, i, n in lista]
    if so:
        lista = [x for x in lista if x[1] in set(so)]
    fazer = comum.blocos_a_fazer(UF, [i for _, i, _ in lista], ["camara", "prefeitura"], disponiveis())
    fazer |= {k for k in _reler() if k[0] in {i for _, i, _ in lista}}
    por_cidade = {}
    for c, o, m in fazer:
        por_cidade.setdefault(c, {}).setdefault(m, set()).add(o)
    tarefas = []
    for c, i, n in lista:
        ms = sorted(por_cidade.get(i, {}))
        for ano in sorted({m // 100 for m in ms}):
            do_ano = [m for m in ms if m // 100 == ano]
            for k in range(0, len(do_ano), MESES_POR_VEZ):
                tarefas.append((c, i, n, {m: por_cidade[i][m] for m in do_ano[k:k + MESES_POR_VEZ]}))
    # os meses mais recentes primeiro: se a coleta parar no meio, o que falta é o mais antigo
    tarefas.sort(key=lambda t: -max(t[3]))
    if len(tarefas) > MAX_TAREFAS:
        log(f"  TCE-CE: {len(tarefas)} tarefas; esta rodada faz as {MAX_TAREFAS} mais recentes, o resto fica para a próxima")
        tarefas = tarefas[:MAX_TAREFAS]
    log(f"  TCE-CE: {len(fazer)} blocos (cidade, órgão e mês) a ler, em {len(por_cidade)} municípios ({len(tarefas)} tarefas)")
    total, pend_l, pend_b, avisos, feitos, salvo = 0, [], [], [], 0, [time.time()]
    erros, seguidos = [], [0]

    def salvar():
        nonlocal total
        if pend_b:
            n, _ = comum.gravar(UF, pend_l, pend_b)
            total += n
            pend_l.clear()
            pend_b.clear()
        salvo[0] = time.time()

    ex = ThreadPoolExecutor(PARALELO)
    futuros = {ex.submit(_municipio, *t): t[2] for t in tarefas}
    try:
        for f in as_completed(futuros):
            try:
                l, b, a = f.result()
            except TempoEsgotado:
                raise
            except Exception as e:  # noqa: BLE001 — um município com erro não para os outros
                log(f"  TCE-CE {futuros[f]}: {e}")
                erros.append(f"{futuros[f]}: {type(e).__name__}: {e}")
                seguidos[0] += 1
                if seguidos[0] >= FALHAS_MAX:
                    # erro de conexão em vários municípios seguidos: o tribunal pode estar bloqueando; para aqui e não
                    # tenta de outro jeito (regra do CLAUDE.md)
                    ex.shutdown(wait=False, cancel_futures=True)
                    salvar()
                    raise RuntimeError(f"TCE-CE: {seguidos[0]} municípios seguidos com erro; o primeiro: {erros[-seguidos[0]]}")
                continue
            seguidos[0] = 0
            pend_l.extend(l)
            pend_b.extend(b)
            avisos.extend(a)
            feitos += 1
            if feitos % 3 == 0 or time.time() - salvo[0] > 20:
                salvar()
            if feitos % 30 == 0:
                log(f"  TCE-CE: {feitos}/{len(tarefas)} tarefas")
    except TempoEsgotado:
        ex.shutdown(wait=False, cancel_futures=True)
        salvar()
        raise
    finally:
        for a in avisos[:20]:
            log(f"  TCE-CE aviso: {a}")
        if len(avisos) > 20:
            log(f"  TCE-CE: mais {len(avisos) - 20} avisos")
    ex.shutdown(wait=True)
    salvar()
    if erros and len(erros) * 2 > len(tarefas):
        raise RuntimeError(f"TCE-CE: {len(erros)} de {len(tarefas)} leituras com erro; a primeira: {erros[0]}")
    return total


CFG = {
    "tribunal": "TCE-CE",
    "fonte": "Tribunal de Contas do Estado do Ceará (TCE-CE), API de Dados Abertos do SIM: a folha de pagamento e o "
             "cadastro dos agentes públicos que cada município manda ao Tribunal",
    "url": "https://api-dados-abertos.tce.ce.gov.br/sim/",
    "nota": "Valor bruto do mês, como a Câmara ou a Prefeitura informou ao Tribunal de Contas do Ceará, antes dos "
            "descontos: a soma dos itens pagos (subsídio, 13º, férias e outros) em todas as folhas do mês.",
    "notas": ["Cada município manda a sua folha ao Tribunal todo mês; o mês que ainda não foi mandado aparece sem valor.",
              "O nome vem do cadastro que o município manda ao Tribunal, com até 40 letras: os nomes mais longos vêm "
              "cortados (com …), a não ser quando casam com o nome completo de um candidato de 2024 no TSE.",
              "Partido: o da eleição de 2024 (TSE), quando o nome da folha é exatamente o de um único candidato da "
              "cidade."],
    "secretarios": False,
    "nome_cortado": True,
    "link_da_fonte": True,  # cada cidade leva o endereço da folha da Câmara do último mês (a consulta na API)
}


def montar():
    return comum.montar_site(UF, CFG)
