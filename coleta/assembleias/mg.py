"""Assembleia Legislativa de Minas Gerais (ALMG): deputado estadual por deputado estadual.

Fontes (Dados Abertos da ALMG, https://dadosabertos.almg.gov.br/ws/, serviço feito para acesso automatizado; o robots.txt
do site tem "Disallow: /", e a leitura é uma das exceções do projeto, ver coleta/util.py e o README):
- Deputados por situação (1: em exercício; 2: afastados; 3: que exerceram mandato): /ws/deputados/situacao/<n>, e os dados
  de cada um (nome civil, sexo, partido, situação): /ws/deputados/<id>
- Verba indenizatória do deputado no mês, por tipo e nota a nota (emitente, CNPJ/CPF, documento, data, valor reembolsado):
  /ws/prestacao_contas/verbas_indenizatorias/deputados/<id>/<ano>/<mês>
- Subsídio: Lei 24.266/2022 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025), o mesmo da página "Remuneração
  dos deputados e custeio" da ALMG.
- Eleito/suplente: TSE (eleição de 2022); partido: o da ALMG (o de hoje).
Quem está no cargo hoje: a lista de deputados em exercício. Desde quando: os meses com verba.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "MG"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
WS = "https://dadosabertos.almg.gov.br/ws"
PASTA = DADOS / "assembleias" / "mg"
C = CACHE / "assembleias" / "mg"
CFG = {
    "cod": COD, "n": "Minas Gerais", "uf": UF, "casa": "Assembleia Legislativa de Minas Gerais", "vagas": 77, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 24.266/2022), proporcional aos meses no cargo. O 13º e outros pagamentos não "
                     "aparecem aqui."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal; entra o valor reembolsado.",
    "verba_notas": ["Cada nota entra no mês de referência da prestação de contas.",
                    "A prestação de contas chega depois do mês: o site vai até o último mês em que pelo menos 80% dos deputados já prestaram contas, e os meses mais recentes ainda podem crescer."],
    "pagina": "https://www.almg.gov.br/a-assembleia/deputados/inicial/",
    "notas": ["Quem está no cargo hoje: a lista de deputados em exercício da ALMG. Desde quando: o início do exercício informado pela ALMG (para quem saiu, os meses com verba).",
              "Partido: o que a ALMG informa hoje."],
    "fontes": {"deputados": f"{WS}/deputados/em_exercicio", "verba": "https://www.almg.gov.br/transparencia/prestacao-de-contas/deputados/verba-indenizatoria/",
               "subsidio": "https://www.almg.gov.br/legislacao-mineira/texto/LEI/24266/2022/"},
}


def _json(caminho):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{WS}/{caminho}", params={"formato": "json"}, timeout=120)
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(15)


def _data(x):
    return (x or {}).get("$", "")[:10] if isinstance(x, dict) else str(x or "")[:10]


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _so_cnpj(doc):
    """Só o CNPJ (empresa) é guardado; o CPF de quem é pessoa física não, nem mascarado (regra do projeto): no lugar dele,
    a marca "PF" (vereadores.comum.mascarar), para o site mostrar "Pessoa física" e não o nome."""
    d = re.sub(r"\D", "", doc or "")
    return d if len(d) == 14 else (vc.PF if len(d) == 11 or "*" in (doc or "") else "")


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    # 1. deputados (em exercício, afastados e quem exerceu mandato na legislatura) e os dados de cada um
    ids = {}
    for sit in (1, 2, 3):
        for d in _json(f"deputados/situacao/{sit}").get("list", []):
            ids[int(d["id"])] = sit
    arq_d = PASTA / "deputados.csv"
    antigos = pd.read_csv(arq_d).fillna("") if arq_d.exists() else pd.DataFrame(columns=["id"])
    velho = not arq_d.exists() or time.time() - arq_d.stat().st_mtime > 6 * 86400
    linhas = [] if velho else antigos.to_dict("records")
    conhecidos = {int(x["id"]) for x in linhas}
    for i in ids:
        if i in conhecidos:
            continue
        d = _json(f"deputados/{i}").get("deputado", {})
        linhas.append({"id": i, "nome": d.get("nome", ""), "nome_civil": d.get("nomeServidor", ""), "sexo": d.get("sexo", ""),
                       "partido": d.get("partido", ""), "situacao": d.get("situacao", ""), "codigo_situacao": d.get("codigoSituacao", ids[i]),
                       "inicio_situacao": _data(d.get("inicioSituacao")), "tipo_mandato": d.get("tipoMandato", "")})
    if linhas:
        gravar_csv(pd.DataFrame(linhas).sort_values("nome"), arq_d)
    # 2. verba de cada deputado e mês (os dois últimos meses são pedidos de novo uma vez por semana)
    meses = _meses()
    arq_v, arq_m = PASTA / "verba_notas.csv", PASTA / "verba_meses.csv"
    notas = pd.read_csv(arq_v, dtype={"cnpj_cpf": str}) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "id"])
    feitos_df = pd.read_csv(arq_m) if arq_m.exists() else pd.DataFrame(columns=["ano", "mes", "id", "pedido_em"])
    hoje = time.strftime("%Y-%m-%d")
    semana = time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400))
    feitos = {(int(a), int(m), int(i)): str(p) for a, m, i, p in zip(feitos_df.ano, feitos_df.mes, feitos_df.id, feitos_df.pedido_em)}
    pedir = [(am, i) for i in ids for am in meses
             if (am // 100, am % 100, i) not in feitos or (am >= meses[-2] and feitos[(am // 100, am % 100, i)] < semana)]

    def um(item):
        am, i = item
        saida = []
        for t in _json(f"prestacao_contas/verbas_indenizatorias/deputados/{i}/{am // 100}/{am % 100}").get("list", []):
            detalhes = t.get("listaDetalheVerba") or []
            for x in detalhes:
                saida.append({"ano": am // 100, "mes": am % 100, "id": i, "tipo": t.get("descTipoDespesa", ""), "emitente": " ".join((x.get("nomeEmitente") or "").split()),
                              "cnpj_cpf": _so_cnpj(x.get("cpfCnpj") or ""), "documento": x.get("descDocumento", ""), "data": _data(x.get("dataEmissao")),
                              "valor_despesa": x.get("valorDespesa"), "valor": x.get("valorReembolsado")})
            resto = round(float(t.get("valor") or 0) - sum(float(x.get("valorReembolsado") or 0) for x in detalhes), 2)
            if abs(resto) >= 0.01:  # o total do tipo que as notas não explicam
                saida.append({"ano": am // 100, "mes": am % 100, "id": i, "tipo": t.get("descTipoDespesa", ""), "emitente": "", "cnpj_cpf": "",
                              "documento": "", "data": "", "valor_despesa": None, "valor": resto})
        return am, i, saida
    res = []
    try:
        with ThreadPoolExecutor(2) as ex:
            for r in ex.map(um, pedir):
                res.append(r)
    finally:
        if res:
            chave = {(am // 100, am % 100, i) for am, i, _ in res}
            if len(notas):
                notas = notas[[k not in chave for k in zip(notas.ano, notas.mes, notas.id)]]
            novos = pd.DataFrame([x for _, _, s in res for x in s])
            notas = pd.concat([notas, novos]) if len(novos) else notas
            # os pedidos só contam como feitos se as notas foram gravadas (util.gravar_com pode recusar; o resultado vazio
            # também passa pela comparação)
            ordem = [c for c in ("ano", "mes", "id", "tipo", "data") if c in notas.columns]
            if gravar_csv(notas.sort_values(ordem) if ordem else notas, arq_v):
                for am, i, _ in res:
                    feitos[(am // 100, am % 100, i)] = hoje
                gravar_csv(pd.DataFrame([{"ano": a, "mes": m, "id": i, "pedido_em": p} for (a, m, i), p in sorted(feitos.items())]), arq_m)
        log(f"  ALMG: verba de {len(res)} de {len(pedir)} deputados e meses pedida agora")


_TIPOS = [(r"COMBUST", "Combustível"), (r"LOCA[CÇ][AÃ]O DE VE[IÍ]C|VE[IÍ]CULO", "Aluguel de carros"), (r"DIVULGA|PUBLICIDADE", "Divulgação do mandato"),
          (r"CONSULTORIA|ASSESSORIA|PESQUISA", "Consultorias e assessorias"), (r"IM[OÓ]VE|ALUGUEL|CONDOM|ESCRIT", "Escritório (aluguel e contas)"),
          (r"TELEF|INTERNET", "Telefone e internet"), (r"HOSPEDA|DI[AÁ]RIA", "Hospedagem e diárias"), (r"PASSAGE|A[EÉ]RE", "Passagens"),
          (r"ALIMENTA|REFEI", "Alimentação"), (r"MATERIA", "Material de escritório"), (r"PUBLICA[CÇ]", "Assinaturas e livros")]


def _tipo(t):
    u = normalizar_nome(t)
    for rx, nome in _TIPOS:
        if __import__("re").search(rx, u):
            return nome
    return vc.tipo_curto(t)


def _todos_meses(de, ate):
    return [a * 100 + m for a in range(de // 100, ate // 100 + 1) for m in range(1, 13) if de <= a * 100 + m <= ate]


def montar(tipos):
    arq_d, arq_v = PASTA / "deputados.csv", PASTA / "verba_notas.csv"
    if not arq_d.exists() or not arq_v.exists():
        return None
    deps = pd.read_csv(arq_d).fillna("")
    v = pd.read_csv(arq_v, dtype={"cnpj_cpf": str}).fillna({"emitente": "", "cnpj_cpf": "", "tipo": ""})
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    ultimo = vc.ultimo_mes_fechado()
    # A prestação de contas chega semanas depois do mês: o último mês do site é o último em que pelo menos 80% das
    # vagas já têm verba (os meses seguintes, com poucas notas, ficam para a próxima coleta).
    por_mes = v.groupby(v.ano * 100 + v.mes).id.nunique()
    cheios = [int(m) for m, n in por_mes.items() if n >= 0.8 * CFG["vagas"]]
    ultimo_dado = max(cheios) if cheios else int(por_mes.index.max())
    v = v[v.ano * 100 + v.mes <= ultimo_dado]
    meses_de = {i: sorted(set(g.ano * 100 + g.mes)) for i, g in v.groupby("id")}
    ver, mandatos = [], []
    for d in deps.itertuples():
        meses_g = meses_de.get(int(d.id), [])
        em_exercicio = int(d.codigo_situacao or 0) == 1
        if not meses_g and not em_exercicio:
            continue
        t = por_civil.get(normalizar_nome(d.nome_civil)) or comum.achar(d.nome, tse) or {}
        ver.append({"codigo": int(d.id), "nome": d.nome, "nome_civil": vc.titulo(t.get("nome") or d.nome_civil or d.nome), "partido": d.partido,
                    "genero": "F" if str(d.sexo).upper().startswith("F") else ("M" if d.sexo else ("F" if feminino(d.nome) else "M")),
                    "eleito": t.get("eleito", "suplente" if "SUPLENTE" in normalizar_nome(d.tipo_mandato) else ""), "pagina": CFG["pagina"]})
        if em_exercicio:
            ini = str(d.inicio_situacao)[:7].replace("-", "")
            ini = max(INICIO, int(ini)) if ini.isdigit() else ultimo_dado
            meses_g = sorted(set(m for m in meses_g if m <= ultimo_dado) | set(m for m in _todos_meses(ini, ultimo_dado)))
        per = comum.periodos(meses_g, ultimo_dado, ultimo, folga=2)
        if not em_exercicio:
            # Quem saiu: o fim é a data da saída (renúncia, fim da suplência) informada pela ALMG, quando ela vem depois
            # do último mês com verba; senão, o fim desse mês.
            fim = max(meses_g)
            saida = str(d.inicio_situacao)[:10]
            if not (len(saida) == 10 and int(saida[:7].replace("-", "")) >= fim):
                saida = f"{fim // 100}-{fim % 100:02d}-28"
            per = [(i, f) for i, f in per[:-1]] + [(per[-1][0], saida)] if per else per
        for i, f in per:
            mandatos.append({"codigo": int(d.id), "inicio": i, "fim": f})
    d = v[v.valor.abs() >= 0.005]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.id.astype(int), "tipo": d.tipo.map(_tipo), "fornecedor": d.emitente,
                         "cnpj_cpf": d.cnpj_cpf, "valor": d.valor})
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp)
