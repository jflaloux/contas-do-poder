"""Índice de Transparência dos estados: dá para saber, pela fonte oficial de cada Estado, quanto ganham e quanto custam
os seus políticos? Uma nota de 0 a 1 por Estado, como no Índice de Transparência do DadosJusBr
(https://dadosjusbr.org/indice), com um bloco para cada fonte:

- Governo do Estado: a folha do governador e do vice (notas em dados/indice/governadores.json; a nota da lei vem de
  dados/governadores/governadores.json: 1 se achamos a lei ou o decreto legislativo que fixa o valor de hoje).
- Assembleia Legislativa: salário, verba do gabinete e equipe de cada deputado estadual (dados/indice/assembleias.json).

Cada bloco tem duas dimensões: completude (o que a fonte mostra) e facilidade (formato aberto, acesso programático, sem
barreiras como CAPTCHA, login ou CPF, aberto a robôs e a quem está fora do Brasil). Cada dimensão é a média dos seus
critérios; o índice do bloco é a média harmônica das duas (se uma é zero, o índice é zero: uma fonte completa que
ninguém consegue usar, ou fácil de usar que não mostra nada, não é transparente). O índice do Estado é a média dos
blocos. As contas usam os valores exatos; o arquivo leva 6 casas, e o site arredonda só na hora de mostrar. Estado com algum critério "a
conferir" (None) num bloco fica sem índice geral; os blocos com nota aparecem.
Saída: site/dados/indice_transparencia.json.
"""
import json

from .config import DADOS, RAIZ
from .util import gravar_json, log

CURADO = DADOS / "indice" / "governadores.json"
GOVERNADORES = DADOS / "governadores" / "governadores.json"

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


# ---------------------------------------------------------------- Índice de Transparência dos estados (vários blocos)
# Cada bloco é uma pergunta sobre uma fonte do Estado, com as mesmas duas dimensões (completude e facilidade) e as notas
# mantidas à mão em dados/indice/<bloco>.json. O índice do Estado é a média dos índices dos blocos que se aplicam (no DF
# não há prefeitura nem Câmara de Vereadores). Estado com algum bloco a conferir fica sem índice geral: o arquivo traz
# então o "indice_parcial" (a média dos blocos que já têm nota) e a lista dos blocos a conferir.
CURADO_ASSEMBLEIA = DADOS / "indice" / "assembleias.json"
CURADO_PREFEITURA = DADOS / "indice" / "prefeituras.json"
CURADO_CAMARA = DADOS / "indice" / "camaras.json"
SAIDA_TRANSPARENCIA = RAIZ / "site" / "dados" / "indice_transparencia.json"
_FORMATO = ("formato", "facilidade", "Formato aberto", "1 = arquivo ou API em formato aberto (CSV, JSON, XML, ODS); 0,75 = parte aberto, parte em PDF, páginas ou formato proprietário; 0,5 = só páginas HTML; 0 = só painel ou PDF.")
_ACESSO = ("acesso", "facilidade", "Acesso", "1 = arquivo para baixar ou API documentada; 0,75 = API sem documentação (a que a página usa); 0,5 = só lendo as páginas; 0,25 = só pelo painel ou por formulários que a página monta; 0 = só clicando.")
_BARREIRA = ("sem_barreira", "facilidade", "Sem barreiras", "1 = sem CAPTCHA, login, token ou CPF; 0,5 = barreira só numa parte; 0 = barreira nos dados principais.")
_ROBOS = ("robos_exterior", "facilidade", "Aberto a robôs e ao exterior", "1 = o robots.txt permite e abre de fora do Brasil; 0,5 = só um dos dois; 0 = nenhum.")
_HISTORICO = ("historico", "completude", "Histórico", "1 = pelo menos 12 meses publicados.")


def _legislativo(quem, plural):
    """Critérios de uma casa legislativa (Assembleia ou Câmara): `quem` é "deputado" ou "vereador"."""
    return [
        ("salario", "completude", "Salário", f"1 = folha de cada {quem}, mês a mês, com as partes (subsídio, 13º, auxílios); 0,75 = folha de cada {quem} sem todas as partes (ou só em páginas); 0,5 = só o valor da lei ou da tabela; 0 = nada."),
        (f"verba_{quem}", "completude", f"Verba por {quem}", f"1 = a verba do gabinete (cota, verba indenizatória) de cada {quem}, mês a mês; 0 = não."),
        ("verba_nota", "completude", "Verba nota a nota", "1 = cada nota, com fornecedor e CNPJ; 0,75 = nota a nota sem CNPJ (ou com o CNPJ mascarado), ou somada por fornecedor; 0,5 = só o total por categoria; 0 = só o total ou nada."),
        ("equipe", "completude", "Equipe do gabinete", "1 = os servidores de cada gabinete com o custo; 0,75 = a folha com a lotação do gabinete; 0,5 = só a lista ou a contagem; 0 = nada ou sem ligação com o gabinete."),
        _HISTORICO,
        ("lei", "completude", "Lei do salário", f"1 = o ato que fixa o subsídio de hoje dos {plural} (lei, decreto legislativo ou resolução) está publicado e foi achado."),
        _FORMATO, _ACESSO, _BARREIRA, _ROBOS,
    ]


CRITERIOS_ASSEMBLEIA = _legislativo("deputado", "deputados")
CRITERIOS_CAMARA = _legislativo("vereador", "vereadores")
CRITERIOS_PREFEITURA = [
    ("nome", "completude", "Nome", "1 = nome completo; 0,5 = nome mascarado; 0 = sem nome."),
    ("cargo", "completude", "Cargo", "1 = mostra o cargo (prefeito, vice, secretário) ou o vínculo pelo qual a pessoa recebe."),
    ("no_cargo_hoje", "completude", "Quem está no cargo", "1 = o prefeito e o vice aparecem no mês mais recente (ou a fonte explica que recebem por outro órgão); 0 = sumiram da consulta."),
    ("partes", "completude", "Partes do pagamento", "Fração de 5 partes mostradas separadas: subsídio, 13º, férias, auxílios e abate-teto."),
    ("secretarios", "completude", "Secretários", "1 = os secretários municipais aparecem com o cargo e o pagamento; 0,5 = aparecem, mas sem dar para separar pelo cargo; 0 = não aparecem."),
    _HISTORICO,
    _FORMATO, _ACESSO, _BARREIRA, _ROBOS,
]
BLOCOS = [
    {"id": "governo", "titulo": "Governo do Estado", "pergunta": "Dá para saber, pela fonte oficial, quanto o governador e o vice receberam em cada mês?",
     "criterios": CRITERIOS},
    {"id": "assembleia", "titulo": "Assembleia Legislativa",
     "pergunta": "Dá para saber, pela fonte oficial, quanto cada deputado estadual recebe e quanto gasta da verba do gabinete?",
     "criterios": CRITERIOS_ASSEMBLEIA},
    {"id": "prefeitura", "titulo": "Prefeitura da capital",
     "pergunta": "Dá para saber, pela fonte oficial, quanto o prefeito, o vice e os secretários da capital receberam em cada mês?",
     "criterios": CRITERIOS_PREFEITURA},
    {"id": "camara", "titulo": "Câmara Municipal da capital",
     "pergunta": "Dá para saber, pela fonte oficial, quanto cada vereador da capital recebe e quanto gasta da verba do gabinete?",
     "criterios": CRITERIOS_CAMARA},
]
CAPITAIS = {"AC": "Rio Branco", "AL": "Maceió", "AM": "Manaus", "AP": "Macapá", "BA": "Salvador", "CE": "Fortaleza", "DF": "Brasília",
            "ES": "Vitória", "GO": "Goiânia", "MA": "São Luís", "MG": "Belo Horizonte", "MS": "Campo Grande", "MT": "Cuiabá",
            "PA": "Belém", "PB": "João Pessoa", "PE": "Recife", "PI": "Teresina", "PR": "Curitiba", "RJ": "Rio de Janeiro",
            "RN": "Natal", "RO": "Porto Velho", "RR": "Boa Vista", "RS": "Porto Alegre", "SC": "Florianópolis", "SE": "Aracaju",
            "SP": "São Paulo", "TO": "Palmas"}


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
        dims[dim] = None if any(v is None for v in vs) else _media(vs)
    cmp, fac = dims["completude"], dims["facilidade"]
    indice = None if cmp is None or fac is None else (0.0 if cmp == 0 or fac == 0 else 2 * cmp * fac / (cmp + fac))
    # o valor exato fica em "_exato" para a média do Estado; o arquivo leva só os arredondados
    return {"indice": _arred(indice), "completude": _arred(cmp), "facilidade": _arred(fac), "criterios": crit,
            "a_conferir": [k for k, v in crit.items() if v["v"] is None], "_exato": indice}


def _arred(v):
    # 6 casas: o site arredonda para 2 na hora de mostrar, e arredondar duas vezes (0,9049 -> 0,905 -> 0,91) erra
    return None if v is None else round(v, 6)


def _municipal(cur, uf, criterios, erros):
    """Bloco da prefeitura ou da Câmara da capital: {"nao_se_aplica": motivo} no DF; senão, o bloco com a cidade."""
    e = cur["estados"].get(uf) or {}
    if e.get("nao_se_aplica"):
        return {"nao_se_aplica": e["nao_se_aplica"]}
    notas = {k: v for k, v in e.items() if k not in ("cidade", "fonte", "obs")}
    b = _bloco(criterios, notas, uf, erros)
    b["cidade"] = e.get("cidade") or CAPITAIS[uf]
    b["fonte"] = e.get("fonte")
    return b


def executar():
    """site/dados/indice_transparencia.json: o Índice de Transparência dos estados, com um bloco por fonte (governo,
    Assembleia, prefeitura e Câmara da capital). Cada bloco tem as duas dimensões; o índice do Estado é a média dos
    blocos (contas com os valores exatos; 6 casas no arquivo)."""
    gov_c = json.loads(CURADO.read_text(encoding="utf-8"))
    ass_c = json.loads(CURADO_ASSEMBLEIA.read_text(encoding="utf-8"))
    pre_c = json.loads(CURADO_PREFEITURA.read_text(encoding="utf-8"))
    cam_c = json.loads(CURADO_CAMARA.read_text(encoding="utf-8"))
    gov = {e["uf"]: e for e in json.loads(GOVERNADORES.read_text(encoding="utf-8"))}
    ref = json.loads((DADOS / "referencia" / "assembleias.json").read_text(encoding="utf-8")).get("estados", {})
    estados, erros = [], []
    for nome_bloco, cur in (("governo", gov_c), ("assembleia", ass_c), ("prefeitura", pre_c), ("camara", cam_c)):
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
        blocos = {"governo": b_gov, "assembleia": b_ass,
                  "prefeitura": _municipal(pre_c, uf, CRITERIOS_PREFEITURA, erros),
                  "camara": _municipal(cam_c, uf, CRITERIOS_CAMARA, erros)}
        valem = {k: b for k, b in blocos.items() if not b.get("nao_se_aplica")}
        exatos = {k: b.pop("_exato") for k, b in valem.items()}
        com_nota = [v for v in exatos.values() if v is not None]
        a_conferir = [k for k, v in exatos.items() if v is None]
        estados.append({"uf": uf, "nome": NOMES_UF[uf], "capital": CAPITAIS[uf],
                        "indice": None if a_conferir else _arred(_media(com_nota)),
                        "indice_parcial": _arred(_media(com_nota)) if a_conferir and com_nota else None,
                        "blocos_com_nota": len(com_nota), "blocos_que_valem": len(valem),
                        "blocos": blocos, "a_conferir": a_conferir})
    if erros:
        raise ValueError("Índice de Transparência: " + "; ".join(erros))
    saida = {
        "meta": {
            "titulo": "Índice de Transparência dos estados",
            "pergunta": "Dá para saber, pela fonte oficial de cada Estado, quanto ganham e quanto custam os seus políticos?",
            "conferido_em": max(c["conferido_em"] for c in (gov_c, ass_c, pre_c, cam_c)),
            "como": ["Quatro blocos para cada Estado: o governo (salário do governador e do vice), a Assembleia Legislativa "
                     "(salário, verba do gabinete e equipe de cada deputado estadual), a prefeitura da capital (prefeito, vice e "
                     "secretários) e a Câmara Municipal da capital (salário, verba e equipe de cada vereador). No DF, que não tem "
                     "prefeitura nem vereadores, valem só os dois primeiros.",
                     "Cada bloco tem duas dimensões, de 0 a 1: completude (o que a fonte mostra) e facilidade (como dá para obter). "
                     "Cada dimensão é a média dos seus critérios; o índice do bloco é a média harmônica das duas, então uma fonte "
                     "completa que é difícil de usar, ou fácil de usar que mostra pouco, não tem nota alta.",
                     "O índice do Estado é a média dos índices dos blocos, com o mesmo peso para cada um. Cada bloco é uma fonte "
                     "diferente, com responsáveis diferentes: a prefeitura e a Câmara da capital não dependem do governo do Estado.",
                     "Estado com algum bloco ainda a conferir fica sem índice geral; os blocos que já têm nota aparecem.",
                     "Cada nota tem a prova: o que a fonte oficial mostra e o que o nosso robô conseguiu ler.",
                     "Inspirado no Índice de Transparência do DadosJusBr (dadosjusbr.org/indice), que avalia o Judiciário."],
            "blocos": [{"id": b["id"], "titulo": b["titulo"], "pergunta": b["pergunta"],
                        "criterios": [{"id": cid, "dimensao": dim, "nome": n, "como_pontua": como} for cid, dim, n, como in b["criterios"]]} for b in BLOCOS],
        },
        "estados": estados,
    }
    gravar_json(SAIDA_TRANSPARENCIA, saida, compacto=False, indent=1)
    com = [e for e in estados if e["indice"] is not None]
    log(f"Índice de Transparência: site/dados/indice_transparencia.json — {len(com)} estados com nota geral, "
        f"{len(estados) - len(com)} com algum bloco a conferir")
    return saida
