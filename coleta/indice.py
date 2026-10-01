"""Índice de acesso aos salários dos governadores: dá para saber, pela fonte oficial, quanto o governador e o vice
receberam em cada mês? Uma nota de 0 a 1 por Estado, em duas dimensões, como no Índice de Transparência do DadosJusBr
(https://dadosjusbr.org/indice):

- Completude (o que a fonte mostra): nome, cargo, quem está no cargo hoje, as partes do pagamento, histórico e a lei do
  salário.
- Facilidade (como dá para obter): formato aberto, acesso programático, sem barreiras (CAPTCHA, login, CPF) e aberto a
  robôs e a quem está fora do Brasil.

Cada dimensão é a média dos seus critérios; o índice é a média harmônica das duas (se uma é zero, o índice é zero: uma
fonte completa que ninguém consegue usar, ou fácil de usar que não mostra nada, não é transparente).

As notas e as provas estão em dados/indice/governadores.json (mantido à mão, estado por estado: o que a folha mostra e o
que o nosso robô consegue). A nota da lei vem de dados/governadores/governadores.json: 1 se achamos a lei (ou decreto
legislativo) que fixa o valor de hoje. Estado com algum critério "a conferir" (None) fica sem índice.
Saída: site/dados/indice.json.
"""
import json

from .config import DADOS, RAIZ
from .util import log, salvar_json

CURADO = DADOS / "indice" / "governadores.json"
GOVERNADORES = DADOS / "governadores" / "governadores.json"
SAIDA = RAIZ / "site" / "dados" / "indice.json"

CRITERIOS = [
    # (id, dimensão, nome curto, como pontua)
    ("nome", "completude", "Nome", "1 = nome completo; 0,5 = nome mascarado; 0 = sem nome."),
    ("cargo", "completude", "Cargo", "1 = mostra o cargo (ou o vínculo pelo qual a pessoa recebe)."),
    ("no_cargo_hoje", "completude", "Quem está no cargo", "1 = o governador e o vice aparecem no mês mais recente (ou a fonte explica que recebem por outro órgão); 0 = sumiram da consulta."),
    ("partes", "completude", "Partes do pagamento", "Fração de 5 partes mostradas separadas: subsídio, 13º, férias, auxílios e abate-teto."),
    ("historico", "completude", "Histórico", "1 = pelo menos 12 meses publicados."),
    ("lei", "completude", "Lei do salário", "1 = a lei (ou decreto legislativo) que fixa o valor de hoje está publicada e foi achada."),
    ("formato", "facilidade", "Formato aberto", "1 = arquivo ou API em formato aberto (CSV, JSON); 0,75 = parte em formato proprietário; 0,5 = só páginas HTML; 0 = só painel ou PDF."),
    ("acesso", "facilidade", "Acesso", "1 = arquivo para baixar ou API documentada; 0,75 = API sem documentação (a que a página usa); 0,5 = só lendo as páginas; 0,25 = só pelo painel; 0 = só clicando."),
    ("sem_barreira", "facilidade", "Sem barreiras", "1 = sem CAPTCHA, login ou CPF; 0 = com alguma dessas barreiras."),
    ("robos_exterior", "facilidade", "Aberto a robôs e ao exterior", "1 = o robots.txt permite e abre de fora do Brasil; 0,5 = só um dos dois; 0 = nenhum."),
]
NOMES_UF = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
            "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
            "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
            "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins"}
VALORES = {0, 0.2, 0.25, 0.4, 0.5, 0.6, 0.75, 0.8, 1}


def _lei(e):
    """(nota, prova, link) do critério da lei, pelo valor de hoje do governador em dados/governadores/governadores.json."""
    gov = sorted((s for s in e["subsidio"] if s["cargo"] == "gov"), key=lambda s: s["desde"])
    if not gov:
        return 0, "Sem o valor do subsídio", None
    atual = gov[-1]
    for s in [x for x in gov if abs(x["valor"] - atual["valor"]) < 0.01][::-1]:
        n = s["norma"].lower()
        if s["confianca"] == "lei" or ("lei" in n.split("(")[0] and "não localizad" not in n and "não confirmad" not in n):
            return 1, s["norma"], s["fonte"]
    return 0, f"Não achamos a lei que fixa o valor de hoje ({atual['norma']})", atual["fonte"]


def _media(v):
    return sum(v) / len(v) if v else None


def executar():
    curado = json.loads(CURADO.read_text(encoding="utf-8"))
    gov = {e["uf"]: e for e in json.loads(GOVERNADORES.read_text(encoding="utf-8"))}
    estados, erros = [], []
    if set(curado["estados"]) != set(NOMES_UF):
        erros.append(f"estados diferentes de 27: {sorted(set(NOMES_UF) ^ set(curado['estados']))}")
    for uf in sorted(NOMES_UF):
        c = dict(curado["estados"].get(uf, {}))
        nota, prova, link = _lei(gov[uf])
        c["lei"] = [nota, prova]
        crit = {}
        for cid, dim, _, _ in CRITERIOS:
            if cid not in c or len(c[cid]) != 2 or not c[cid][1]:
                erros.append(f"{uf}: critério {cid} sem nota ou sem prova")
                continue
            v, p = c[cid]
            if v is not None and v not in VALORES:
                erros.append(f"{uf}: {cid} = {v} fora dos valores possíveis")
            crit[cid] = {"v": v, "prova": p}
        crit.get("lei", {})["link"] = link
        dims = {}
        for dim in ("completude", "facilidade"):
            vs = [crit[cid]["v"] for cid, d, _, _ in CRITERIOS if d == dim and cid in crit]
            dims[dim] = None if any(v is None for v in vs) else round(_media(vs), 3)
        cmp, fac = dims["completude"], dims["facilidade"]
        indice = None if cmp is None or fac is None else (0.0 if cmp == 0 or fac == 0 else round(2 * cmp * fac / (cmp + fac), 3))
        estados.append({"uf": uf, "nome": NOMES_UF[uf], "indice": indice, "completude": cmp, "facilidade": fac,
                        "fonte": (gov[uf].get("folha") or {}).get("url"), "criterios": crit,
                        "a_conferir": [cid for cid, v in crit.items() if v["v"] is None]})
    if erros:
        raise ValueError("Índice: " + "; ".join(erros))
    com = sorted((e for e in estados if e["indice"] is not None), key=lambda e: -e["indice"])
    saida = {
        "meta": {
            "titulo": "Índice de acesso aos salários dos governadores",
            "pergunta": "Dá para saber, pela fonte oficial, quanto o governador e o vice receberam em cada mês?",
            "conferido_em": curado["conferido_em"],
            "como": ["Duas dimensões, de 0 a 1: completude (o que a fonte mostra) e facilidade (como dá para obter). Cada uma é "
                     "a média dos seus critérios; o índice é a média harmônica das duas, então uma fonte completa que é difícil "
                     "de usar, ou fácil de usar que mostra pouco, não tem nota alta.",
                     "Cada nota tem a prova: o que a folha de pagamento do Estado mostra e o que o nosso robô conseguiu ler. "
                     "Estado com algum critério ainda a conferir fica sem índice.",
                     "O índice mede uma coisa só: o acesso ao salário do governador e do vice. Não é uma nota da transparência "
                     "do Estado como um todo.",
                     "Inspirado no Índice de Transparência do DadosJusBr (dadosjusbr.org/indice), que avalia o Judiciário."],
            "criterios": [{"id": cid, "dimensao": dim, "nome": nome, "como_pontua": como} for cid, dim, nome, como in CRITERIOS],
        },
        "estados": estados,
    }
    salvar_json(SAIDA, saida)
    transparencia()
    log(f"Índice: site/dados/indice.json — {len(com)} estados com nota (de {com[-1]['indice'] if com else '-'} a "
        f"{com[0]['indice'] if com else '-'}), {len(estados) - len(com)} a conferir")
    return saida


# ---------------------------------------------------------------- Índice de Transparência dos estados (vários blocos)
# Cada bloco é uma pergunta sobre uma fonte do Estado, com as mesmas duas dimensões (completude e facilidade) e as notas
# mantidas à mão em dados/indice/<bloco>.json. O índice do Estado é a média dos índices dos blocos; Estado com algum
# bloco a conferir fica sem índice geral (os blocos com nota aparecem mesmo assim).
CURADO_ASSEMBLEIA = DADOS / "indice" / "assembleias.json"
SAIDA_TRANSPARENCIA = RAIZ / "site" / "dados" / "indice_transparencia.json"
CRITERIOS_ASSEMBLEIA = [
    ("salario", "completude", "Salário", "1 = folha de cada deputado, mês a mês, com as partes (subsídio, 13º, auxílios); 0,75 = folha de cada deputado sem todas as partes (ou só em páginas); 0,5 = só o valor da lei ou da tabela; 0 = nada."),
    ("verba_deputado", "completude", "Verba por deputado", "1 = a verba do gabinete (cota, verba indenizatória) de cada deputado, mês a mês; 0 = não."),
    ("verba_nota", "completude", "Verba nota a nota", "1 = cada nota, com fornecedor e CNPJ; 0,75 = nota a nota sem CNPJ (ou com o CNPJ mascarado), ou somada por fornecedor; 0,5 = só o total por categoria; 0 = só o total ou nada."),
    ("equipe", "completude", "Equipe do gabinete", "1 = os servidores de cada gabinete com o custo; 0,75 = a folha com a lotação do gabinete; 0,5 = só a lista ou a contagem; 0 = nada ou sem ligação com o gabinete."),
    ("historico", "completude", "Histórico", "1 = pelo menos 12 meses publicados."),
    ("lei", "completude", "Lei do salário", "1 = a lei que fixa o subsídio de hoje está publicada e foi achada."),
    ("formato", "facilidade", "Formato aberto", "1 = arquivo ou API em formato aberto (CSV, JSON, XML, ODS); 0,75 = parte aberto, parte em PDF, páginas ou formato proprietário; 0,5 = só páginas HTML; 0 = só painel ou PDF."),
    ("acesso", "facilidade", "Acesso", "1 = arquivo para baixar ou API documentada; 0,75 = API sem documentação (a que a página usa); 0,5 = só lendo as páginas; 0,25 = só pelo painel ou por formulários que a página monta; 0 = só clicando."),
    ("sem_barreira", "facilidade", "Sem barreiras", "1 = sem CAPTCHA, login, token ou CPF; 0,5 = barreira só numa parte; 0 = barreira nos dados principais."),
    ("robos_exterior", "facilidade", "Aberto a robôs e ao exterior", "1 = o robots.txt permite e abre de fora do Brasil; 0,5 = só um dos dois; 0 = nenhum."),
]
BLOCOS = [
    {"id": "governo", "titulo": "Governo do Estado", "pergunta": "Dá para saber, pela fonte oficial, quanto o governador e o vice receberam em cada mês?",
     "criterios": CRITERIOS},
    {"id": "assembleia", "titulo": "Assembleia Legislativa",
     "pergunta": "Dá para saber, pela fonte oficial, quanto cada deputado estadual recebe e quanto gasta da verba do gabinete?",
     "criterios": CRITERIOS_ASSEMBLEIA},
]


def _bloco(criterios, notas, uf, erros, extra=None):
    c = dict(notas)
    if extra:
        c.update(extra)
    crit = {}
    for cid, dim, _, _ in criterios:
        if cid not in c or len(c[cid]) != 2 or not c[cid][1]:
            erros.append(f"{uf}: critério {cid} sem nota ou sem prova")
            continue
        v, p = c[cid]
        if v is not None and v not in VALORES:
            erros.append(f"{uf}: {cid} = {v} fora dos valores possíveis")
        crit[cid] = {"v": v, "prova": p}
    dims = {}
    for dim in ("completude", "facilidade"):
        vs = [crit[cid]["v"] for cid, d, _, _ in criterios if d == dim and cid in crit]
        dims[dim] = None if any(v is None for v in vs) else round(_media(vs), 3)
    cmp, fac = dims["completude"], dims["facilidade"]
    indice = None if cmp is None or fac is None else (0.0 if cmp == 0 or fac == 0 else round(2 * cmp * fac / (cmp + fac), 3))
    return {"indice": indice, "completude": cmp, "facilidade": fac, "criterios": crit, "a_conferir": [k for k, v in crit.items() if v["v"] is None]}


def transparencia():
    """site/dados/indice_transparencia.json: o Índice de Transparência dos estados, com um bloco por fonte (governo e
    Assembleia). Cada bloco tem as duas dimensões; o índice do Estado é a média dos blocos."""
    gov_c = json.loads(CURADO.read_text(encoding="utf-8"))
    ass_c = json.loads(CURADO_ASSEMBLEIA.read_text(encoding="utf-8"))
    gov = {e["uf"]: e for e in json.loads(GOVERNADORES.read_text(encoding="utf-8"))}
    ref = json.loads((DADOS / "referencia" / "assembleias.json").read_text(encoding="utf-8")).get("estados", {})
    estados, erros = [], []
    for nome_bloco, cur in (("governo", gov_c), ("assembleia", ass_c)):
        if set(cur["estados"]) != set(NOMES_UF):
            erros.append(f"{nome_bloco}: estados diferentes de 27: {sorted(set(NOMES_UF) ^ set(cur['estados']))}")
    for uf in sorted(NOMES_UF):
        nota, prova, link = _lei(gov[uf])
        b_gov = _bloco(CRITERIOS, gov_c["estados"].get(uf, {}), uf, erros, {"lei": [nota, prova]})
        b_gov["criterios"].get("lei", {})["link"] = link
        b_gov["fonte"] = (gov[uf].get("folha") or {}).get("url")
        b_ass = _bloco(CRITERIOS_ASSEMBLEIA, ass_c["estados"].get(uf, {}), uf, erros)
        r = ref.get(uf, {})
        b_ass["fonte"] = (r.get("verba") or {}).get("url") or r.get("site")
        if (r.get("subsidio") or {}).get("url"):
            b_ass["criterios"].get("lei", {})["link"] = r["subsidio"]["url"]
        blocos = {"governo": b_gov, "assembleia": b_ass}
        vs = [b["indice"] for b in blocos.values()]
        estados.append({"uf": uf, "nome": NOMES_UF[uf], "indice": None if any(v is None for v in vs) else round(_media(vs), 3),
                        "blocos": blocos, "a_conferir": [k for k, b in blocos.items() if b["indice"] is None]})
    if erros:
        raise ValueError("Índice de Transparência: " + "; ".join(erros))
    saida = {
        "meta": {
            "titulo": "Índice de Transparência dos estados",
            "pergunta": "Dá para saber, pela fonte oficial de cada Estado, quanto ganham e quanto custam os seus políticos?",
            "conferido_em": max(gov_c["conferido_em"], ass_c["conferido_em"]),
            "como": ["Um bloco para cada fonte do Estado: o governo (salário do governador e do vice) e a Assembleia Legislativa "
                     "(salário, verba do gabinete e equipe de cada deputado estadual).",
                     "Cada bloco tem duas dimensões, de 0 a 1: completude (o que a fonte mostra) e facilidade (como dá para obter). "
                     "Cada dimensão é a média dos seus critérios; o índice do bloco é a média harmônica das duas, então uma fonte "
                     "completa que é difícil de usar, ou fácil de usar que mostra pouco, não tem nota alta.",
                     "O índice do Estado é a média dos índices dos blocos. Estado com algum bloco ainda a conferir fica sem índice "
                     "geral; os blocos que já têm nota aparecem.",
                     "Cada nota tem a prova: o que a fonte oficial mostra e o que o nosso robô conseguiu ler.",
                     "Inspirado no Índice de Transparência do DadosJusBr (dadosjusbr.org/indice), que avalia o Judiciário."],
            "blocos": [{"id": b["id"], "titulo": b["titulo"], "pergunta": b["pergunta"],
                        "criterios": [{"id": cid, "dimensao": dim, "nome": n, "como_pontua": como} for cid, dim, n, como in b["criterios"]]} for b in BLOCOS],
        },
        "estados": estados,
    }
    salvar_json(SAIDA_TRANSPARENCIA, saida)
    com = sorted((e for e in estados if e["indice"] is not None), key=lambda e: -e["indice"])
    log(f"Índice de Transparência: site/dados/indice_transparencia.json — {len(com)} estados com nota geral, "
        f"{len(estados) - len(com)} com algum bloco a conferir")
    return saida
