"""Assembleia Legislativa do Ceará (Alece): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alece, https://transparencia.al.ce.gov.br/, sem cadastro):
- Folha de pagamento nominal do mês, em CSV (Gestão de Pessoas > Pessoal), com a categoria "DEPUTADOS": remuneração
  bruta, abate-teto e 13º de cada deputado (titular ou suplente em exercício):
  https://transparencia.al.ce.gov.br/gestao-de-pessoas/pessoal/csv?mes=MM&ano=AAAA. Os descontos (imposto,
  previdência) e o líquido não são guardados.
- Verba de Desempenho Parlamentar (VDP), empenho por empenho (descrição, CNPJ, credor, valor), em CSV:
  https://transparencia.al.ce.gov.br/despesas/verba-desempenho-parlamentar/csv?mes=MM&ano=AAAA
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem esteve no cargo em cada mês: quem está na folha do mês com a categoria "DEPUTADOS".
"""
import csv
import io
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "CE"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
BASE = "https://transparencia.al.ce.gov.br"
PASTA = DADOS / "assembleias" / "ce"
C = CACHE / "assembleias" / "ce"
CFG = {
    "cod": COD, "n": "Ceará", "uf": UF, "casa": "Assembleia Legislativa do Ceará", "vagas": 46, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33066.39], [202502, 34776.64]],
    "subsidio_folha": True,
    "salario_nota": ("Remuneração bruta da folha de pagamento da Alece (já descontado o abate-teto), antes do imposto e da previdência. "
                     "O subsídio fixado pelo Ato Deliberativo 917/2022 é de R$ 34.776,64 desde fev/2025; a remuneração bruta da folha "
                     "é maior, e a Alece não detalha as parcelas."),
    "verba_nome": "Verba de Desempenho Parlamentar (VDP)",
    "verba_regra": "Despesas do mandato pagas pela Alece até o limite mensal da verba.",
    "verba_notas": ["A Alece publica a VDP empenho por empenho (não nota fiscal por nota fiscal), com o credor e o CNPJ."],
    "pagina": "https://www.al.ce.gov.br/deputados",
    "notas": ["Quem estava no cargo em cada mês: quem aparece na folha do mês com a categoria \"DEPUTADOS\" (titulares e suplentes "
              "em exercício).", "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": f"{BASE}/gestao-de-pessoas/pessoal", "verba": f"{BASE}/despesas/verba-desempenho-parlamentar",
               "subsidio": f"{BASE}/uploads/estrutura_remuneratoria/YuihxetEr86nWb3jQ0XLfOcxvijZ3SjnmVsS7mWJ.txt"},
}


def _csv(caminho, am, dias):
    arq = C / f"{caminho.replace('/', '_')}_{am}.csv"
    if arq.exists() and time.time() - arq.stat().st_mtime < dias * 86400:
        return arq.read_bytes()
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{BASE}/{caminho}/csv", params={"mes": f"{am % 100:02d}", "ano": am // 100}, timeout=300)
            r.raise_for_status()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(r.content)
    dormir(3)
    return r.content


def _texto(b):
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:
        return b.decode("latin1")


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    folha, verba = [], []
    meses = _meses()
    for am in meses:
        dias = 5 if am >= meses[-2] else 3650
        linhas = list(csv.reader(io.StringIO(_texto(_csv("gestao-de-pessoas/pessoal", am, dias))), delimiter=";"))
        cab = next((i for i, l in enumerate(linhas) if l and normalizar_nome(l[0]).startswith("MATRICULA")), None)
        if cab is not None:
            col = {normalizar_nome(c): i for i, c in enumerate(linhas[cab])}
            for l in linhas[cab + 1:]:
                if len(l) < len(col) or normalizar_nome(l[col["CATEGORIA"]]) != "DEPUTADOS":
                    continue
                teto = next((i for k, i in col.items() if "TETO" in k), None)
                dec = next((i for k, i in col.items() if k.startswith("13")), None)
                folha.append({"ano": am // 100, "mes": am % 100, "matricula": l[col["MATRICULA"]].strip(), "nome": l[col["NOME"]].strip(),
                              "situacao": l[col["SITUACAO"]].strip(), "bruta": num(l[col["REMUNERACAO BRUTA"]]),
                              "abate_teto": num(l[teto]) if teto is not None else 0.0, "decimo": num(l[dec]) if dec is not None else 0.0})
        linhas = list(csv.reader(io.StringIO(_texto(_csv("despesas/verba-desempenho-parlamentar", am, dias))), delimiter=";"))
        cab = next((i for i, l in enumerate(linhas) if l and normalizar_nome(l[0]) == "DEPUTADO"), None)
        if cab is not None:
            for l in linhas[cab + 1:]:
                if len(l) < 7 or not l[0].strip():
                    continue
                verba.append({"ano": am // 100, "mes": am % 100, "deputado": " ".join(l[0].split()), "empenho": l[2].strip(), "descricao": " ".join(l[3].split()),
                              "cnpj_cpf": vc.mascarar(l[4]), "fornecedor": " ".join(l[5].split()), "valor": num(l[6])})
    pd.DataFrame(folha).sort_values(["ano", "mes", "nome"]).to_csv(PASTA / "folha_deputados.csv", index=False)
    pd.DataFrame(verba).sort_values(["ano", "mes", "deputado", "empenho"]).to_csv(PASTA / "vdp_empenhos.csv", index=False)
    log(f"  Alece: {len(folha)} contracheques de deputados e {len(verba)} empenhos da VDP desde {INICIO % 100:02d}/{INICIO // 100}")


# nomes da VDP que não batem com o nome de urna nem com o da folha (conferidos pelos meses em que aparecem)
APELIDOS_VDP = {"MISSIAS DIAS": "MANOEL MISSIAS BEZERRA", "MISSISAS DIAS": "MANOEL MISSIAS BEZERRA", "NIZO COSTA": "ANTONIO VALDENIZO DA COSTA",
                "CARMELO BOLSONARO": "CARMELO SILVEIRA CARNEIRO LEAO NETO"}

_TIPOS = [(r"REFEI|ALIMENTA", "Vale-refeição e vale-alimentação"), (r"COMBUST", "Combustível"), (r"LOCA[CÇ][AÃ]O DE VE[IÍ]C|VEICULO", "Locação de veículos"),
          (r"JUR[IÍ]DIC", "Consultoria jurídica"), (r"CONT[AÁ]B", "Consultoria contábil"), (r"CONSULTORIA|ASSESSORIA|PESQUISA", "Consultorias e assessorias"),
          (r"DIVULGA|PUBLICIDADE|M[IÍ]DIA|COMUNICA", "Divulgação e comunicação"), (r"ALUGUEL|LOCA[CÇ][AÃ]O DE IM[OÓ]VEL|ESCRIT[OÓ]RIO", "Escritório"),
          (r"TELEF|INTERNET", "Telefone e internet"), (r"GR[AÁ]FIC|IMPRESS", "Gráfica"), (r"PASSAGE|HOSPEDA|DI[AÁ]RIA", "Passagens e hospedagem")]


def _tipo(descricao):
    u = normalizar_nome(descricao)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return "Outras despesas"


def montar(tipos):
    arq_f = PASTA / "folha_deputados.csv"
    if not arq_f.exists():
        return None
    folha = pd.read_csv(arq_f, dtype={"matricula": str}).fillna("")
    vdp = pd.read_csv(PASTA / "vdp_empenhos.csv", dtype={"cnpj_cpf": str}).fillna("") if (PASTA / "vdp_empenhos.csv").exists() else pd.DataFrame()
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((folha.ano * 100 + folha.mes).max())
    ver, mandatos, nomes_folha = [], [], {}
    for mat, g in folha.groupby("matricula"):
        t = comum.achar(g.nome.iloc[-1], {normalizar_nome(v["nome"]): v for v in tse.values()}) or comum.achar(g.nome.iloc[-1], tse) or {}
        nome_civil = vc.titulo(t.get("nome") or g.nome.iloc[-1])  # o do TSE tem os acentos; o da folha, não
        nomes_folha[normalizar_nome(g.nome.iloc[-1])] = {"nome": g.nome.iloc[-1], "urna": t.get("urna", ""), "eleito": "eleito", "mat": mat}
        ver.append({"codigo": int(mat), "nome": vc.titulo(t["urna"]) if t.get("urna") else nome_civil, "nome_civil": nome_civil,
                    "partido": partidos.get(normalizar_nome(g.nome.iloc[-1]), ""), "genero": t.get("genero") or ("F" if feminino(nome_civil) else "M"),
                    "eleito": t.get("eleito", "") or ("suplente" if "SUPLENTE" in normalizar_nome(g.situacao.iloc[-1]) else ""), "pagina": CFG["pagina"]})
        for i, f in vc.periodos_de_meses(list(g.ano * 100 + g.mes), ultimo_dado):
            mandatos.append({"codigo": int(mat), "inicio": i, "fim": f})
    ganha = []
    for r in folha.itertuples():
        ganha.append({"ano": r.ano, "mes": r.mes, "codigo": int(r.matricula), "categoria": "salario", "valor": float(r.bruta) - float(r.abate_teto)})
        if r.decimo:
            ganha.append({"ano": r.ano, "mes": r.mes, "codigo": int(r.matricula), "categoria": "decimo_terceiro", "valor": float(r.decimo)})
    # o nome da VDP ("DEP AGENOR NETO") é o nome parlamentar: casa com o nome de urna ou o nome civil da folha
    aliases = {}
    for n, v in nomes_folha.items():
        aliases[n] = v
        if v["urna"]:
            aliases[normalizar_nome(v["urna"])] = dict(v, nome=v["urna"])
    import difflib
    for apelido, civil in APELIDOS_VDP.items():
        if normalizar_nome(civil) in nomes_folha:
            aliases[normalizar_nome(apelido)] = nomes_folha[normalizar_nome(civil)]
    chaves = list(aliases)
    cod_vdp, sem = {}, []
    for dep in sorted(set(vdp.deputado)) if len(vdp) else []:
        nome = re.sub(r"^DEP\.?\s+", "", dep).strip(" .")
        v = comum.achar(nome, aliases)
        if not v:  # a VDP tem erros de digitação ("SEGIO AGUIAR", "WALTER CAVACANTE"): o nome mais parecido, se for bem parecido
            perto = difflib.get_close_matches(normalizar_nome(nome), chaves, n=2, cutoff=0.85)
            if len(perto) == 1 or (len(perto) == 2 and aliases[perto[0]]["mat"] == aliases[perto[1]]["mat"]):
                v = aliases[perto[0]]
        if v:
            cod_vdp[dep] = int(v["mat"])
        else:
            sem.append(dep)
    if sem:
        log(f"  Alece: VDP sem deputado da folha: {', '.join(sem)}")
    desp = vdp[vdp.deputado.isin(cod_vdp)].assign(codigo=lambda d: d.deputado.map(cod_vdp), tipo=lambda d: d.descricao.map(_tipo)) if len(vdp) else None
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=pd.DataFrame(ganha),
                     despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]] if desp is not None else None)
