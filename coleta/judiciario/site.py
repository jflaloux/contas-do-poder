"""site/dados/judiciario.json: as pessoas da composição (dados/judiciario/composicao.json) com o pagamento mês a mês de
cada órgão (dados/judiciario/<orgao>/folha.csv), no mesmo formato de site/dados/assembleias.json (o site reusa a página
de pessoa), com "orgaos" no lugar de "estados".

Uma página por pessoa e órgão: quem está no TSE vindo do STF ou do STJ tem duas páginas ligadas por "rel", e cada uma
mostra só o que aquele órgão paga (nada é somado duas vezes). Quem integra o CNJ e é pago pelo próprio tribunal
(presidente, corregedor, vaga do TST) não ganha página no CNJ: a função aparece na página do tribunal. Campos além dos
do formato das Assembleias: "org" (sigla do órgão), "tc" (partes de cada mês em reais inteiros, na ordem de meta.partes; null = a fonte não separa), "ti" (nome de
cada parcela, quando a fonte dá: índice em meta.tipos e valor), "fn" (funções: presidente, vice, corregedor), "rel" e
"nm" (notas de um mês). O cargo de cada mês sai da lotação na folha.
"""
import csv
import json
import re
from calendar import monthrange
from datetime import datetime

from ..config import RAIZ
from ..util import gravar_json, log, normalizar_nome
from . import comum

SAIDA = RAIZ / "site" / "dados" / "judiciario.json"
FOTOS = RAIZ / "site" / "fotos"
ORDEM = ["STF", "STJ", "TST", "STM", "TSE", "CNJ", "PGR"]
PARTES_SITE = [*comum.PARTES, "diarias"]
CATEGORIAS = {
    "subsidio": {"grupo": "ganha", "nome": "Subsídio"},
    "vantagens_pessoais": {"grupo": "ganha", "nome": "Vantagens pessoais (adicional por tempo de serviço, VPNI)"},
    "abono_permanencia": {"grupo": "ganha", "nome": "Abono de permanência"},
    "indenizacoes": {"grupo": "ganha", "nome": "Indenizações (parcelas classificadas como indenizatórias)"},
    "vantagens_eventuais": {"grupo": "ganha", "nome": "Vantagens eventuais"},
    "ferias": {"grupo": "ganha", "nome": "Férias (1/3 e indenização de férias)"},
    "decimo_terceiro": {"grupo": "ganha", "nome": "13º salário"},
    "outras": {"grupo": "ganha", "nome": "Outros pagamentos"},
    "diarias": {"grupo": "custa", "nome": "Diárias de viagens oficiais"},
}
NOTAS_GERAIS = [
    "Valores brutos, mês a mês, como cada fonte separa: antes do abate-teto e sem os descontos (imposto, previdência, "
    "descontos pessoais); o líquido não é mostrado. As diárias de viagem ficam à parte, fora do total.",
    "Parcelas que os tribunais classificam como indenizatórias (por exemplo PVTAC e GECJAO, na Resolução Conjunta CNJ/CNMP "
    "14/2026) não entram no cálculo do abate-teto na própria folha; por isso o total do mês pode passar do subsídio de "
    "ministro do STF (R$ 46.366,19 desde fev/2025).",
    "Quem está no TSE vindo do STF ou do STJ recebe o subsídio no tribunal de origem: cada página mostra só o que aquele órgão paga.",
]
NOTAS = {
    "STF": ["Fonte: a cópia do arquivo oficial do STF (consulta egesp-portal.stf.jus.br) guardada pelo DadosJusBr (licença CC BY "
            "4.0). O robô do Contas do Poder ainda não lê a consulta do STF.",
            "Em dez/2025 o arquivo do STF repete cada coluna e cada linha (valores iguais): vale uma de cada. O pacote padronizado do "
            "DadosJusBr daquele mês ficou com as colunas trocadas; por isso os valores aqui saem da cópia do arquivo oficial.",
            "Em jul/2026, para dois ministros, a coluna Férias traz um valor que os totais do próprio arquivo subtraem; aqui ele "
            "entra com sinal negativo (o DadosJusBr soma).",
            "A partir de jul/2026, o arquivo traz valores em vantagens pessoais para 9 dos 10 ministros (de 5% a 35% do subsídio)."],
    "STJ": ["Fonte: a API da página de transparência do STJ (Detalhamento da folha de pagamento).",
            "Desde mai/2026 a página dá o nome de cada parcela (por exemplo PVTAC e GECJAO, classificadas como indenizatórias). "
            "Antes, só o total de cada grupo: o abono de permanência fica nas vantagens pessoais, e as férias e o 13º, nas eventuais."],
    "TST": ["Fonte: o arquivo mensal de remuneração do TST (CSV).",
            "O arquivo não separa o abono de permanência (fica nas vantagens pessoais), nem o 1/3 de férias e o 13º (ficam nas "
            "vantagens eventuais ou nas gratificações), nem dá o nome de cada indenização.",
            "Jan/2026 não está na lista de arquivos do TST. Em fev/2025, para 13 ministros, o total de rendimentos do próprio "
            "arquivo difere da soma das partes; aqui fica a soma das partes."],
    "STM": ["Fonte: a planilha que o STM manda ao Painel de Remuneração dos Magistrados do CNJ, coletada pelo DadosJusBr (licença "
            "CC BY 4.0). Os meses que o DadosJusBr não tem vêm da consulta oficial do STM (só abre de dentro do Brasil)."],
    "TSE": ["Fonte: a planilha que o TSE manda ao Painel de Remuneração dos Magistrados do CNJ, coletada pelo DadosJusBr (licença "
            "CC BY 4.0). O site do TSE responde 403 a robôs.",
            "Aqui só o que o TSE paga: quem vem do STF ou do STJ recebe o subsídio no tribunal de origem e, no TSE, a "
            "gratificação eleitoral ou o jeton. Os substitutos só aparecem nos meses em que recebem.",
            "Jan/2025: a planilha do TSE não traz ministros. Fev/2026 não está no DadosJusBr."],
    "CNJ": ["Fonte: a página da folha de pagamento do CNJ.",
            "Conselheiros que vêm de um tribunal recebem o salário no órgão de origem e, no CNJ, só a diferença de subsídio; os de "
            "fora (advogados e cidadãos indicados pela Câmara e pelo Senado) recebem o subsídio no CNJ. O presidente (presidente do "
            "STF), o corregedor nacional (ministro do STJ) e o conselheiro da vaga do TST são pagos pelos seus tribunais: a "
            "função aparece na página deles.",
            "As diárias de quem mora em outra cidade e viaja a Brasília ficam à parte.",
            "Nov/2025: a página lista o mês, mas não traz ninguém (conferido em 02/10/2026)."],
    "PGR": ["Fonte: as planilhas do MPF (remuneração dos membros ativos e verbas indenizatórias). No arquivo, o PGR aparece com o "
            "cargo de carreira (subprocurador-geral da República) e a lotação PGR.",
            "O total do arquivo não inclui as verbas indenizatórias nem as outras remunerações temporárias; aqui o total soma tudo."],
}
VIA = {"STF": "DadosJusBr", "STM": "DadosJusBr", "TSE": "DadosJusBr", "STJ": "oficial", "TST": "oficial", "CNJ": "oficial", "PGR": "oficial"}
FONTE = {"STF": "https://egesp-portal.stf.jus.br/transparencia/rendimento_folha", "STJ": "https://transparencia.web.stj.jus.br/",
         "TST": "https://transparencia-remuneracao.tst.jus.br/", "STM": "https://www2.stm.jus.br/rem_web/index.php/ctrl_remuneracao",
         "TSE": "https://www.tse.jus.br/transparencia-e-prestacao-de-contas", "CNJ": "https://www.cnj.jus.br/remuneracao/",
         "PGR": "https://transparencia.mpf.mp.br/"}
NOTAS_MES = re.compile(r"sinal foi trocado|diferente da soma|a conferir|não batem|subsídio como|abate-teto")


def _am(texto):
    return int(str(texto).replace("-", "")[:6]) if texto else None


def _r(v):
    return int(round(float(v or 0)))


def _funcao(orgao, lotacao, fem):
    l = normalizar_nome(lotacao)
    if "VICE" in l and "PRESID" in l:
        return f"Vice-presidente do {orgao}"
    if "PRESID" in l:
        return f"Presidente do {orgao}"
    if "CORREGEDORIA" in l:
        return ("Corregedora-geral" if fem else "Corregedor-geral") + {"TST": " da Justiça do Trabalho", "TSE": " da Justiça Eleitoral"}.get(orgao, "")
    return None


def _periodos(meses_fn, sem_dados=()):
    """[(am, funcao)] -> [[funcao, de, ate]] (ate None = até o último mês). Um mês sem folha publicada no meio (TST em
    jan/2026, STM em jan, mar e abr/2026) não interrompe a função."""
    sem_dados = set(sem_dados)
    saida = []
    for f, am in sorted((f, am) for am, f in meses_fn):
        if saida and saida[-1][0] == f:
            x = comum.mes_mais(saida[-1][2])
            while x in sem_dados and x < am:
                x = comum.mes_mais(x)
            if x == am:
                saida[-1][2] = am
                continue
        saida.append([f, am, am])
    return sorted(saida, key=lambda s: (s[1], s[0]))


def montar():
    comp = comum.composicao()
    tipos, idx_tipo = [], {}

    def tipo(nome):
        if nome not in idx_tipo:
            idx_tipo[nome] = len(tipos)
            tipos.append(nome)
        return idx_tipo[nome]

    membros = comp.get("membros", [])
    por_nome = {}
    for m in membros:
        for n in [m["nome_civil"], *m.get("folha", [])]:
            por_nome[(m["orgao"], normalizar_nome(n))] = m
    fora = {o: {normalizar_nome(x["nome"]) for x in xs} for o, xs in comp.get("fora", {}).items()}
    metas, pessoas = {}, []
    for org in ORDEM:
        linhas = comum.ler(org)
        fontes = comum.ler_fontes(org)
        if not linhas:
            continue
        ultimo = max(int(l["ano_mes"]) for l in linhas)
        por_pessoa, sem = {}, set()
        for l in linhas:
            m = por_nome.get((org, normalizar_nome(l["nome"])))
            if m is None:
                if normalizar_nome(l["nome"]) not in fora.get(org, set()):
                    sem.add(l["nome"])
                continue
            por_pessoa.setdefault(m["id"], []).append(l)
        if sem:
            log(f"  Judiciário {org}: na folha e fora da composição (dados/judiciario/composicao.json): {', '.join(sorted(sem))}")
        oc = comp["orgaos"].get(org, {})
        lidos = {int(f["ano_mes"]): int(f["pessoas"] or 0) for f in fontes}
        janela = comum.meses(comum.INICIO, ultimo)
        sem_dados = [am for am in janela if not lidos.get(am)]
        no_cargo = 0
        for m in [x for x in membros if x["orgao"] == org]:
            ls = sorted(por_pessoa.get(m["id"], []), key=lambda l: int(l["ano_mes"]))
            fem = bool(m.get("fem"))
            ini, fim = _am(m.get("inicio")), _am(m.get("fim"))
            x = 1 if fim is None else 0
            no_cargo += x
            tc, ti, nm, serie, fn = [], {}, {}, [], []
            for l in ls:
                am = int(l["ano_mes"])
                vals = [float(l[p]) if l[p] not in ("", None) else None for p in comum.PARTES]
                diarias = float(l["diarias"] or 0)
                tc.append([am, [None if v is None else _r(v) for v in vals] + [_r(diarias)]])
                serie.append((am, float(l["total_bruto"] or 0), diarias))
                if l.get("itens"):
                    its = []
                    for it in l["itens"].split("; "):
                        mm = re.match(r"(.*) = (-?[\d.]+)$", it)
                        if mm:
                            its.append([tipo(mm.group(1)), _r(mm.group(2))])
                    if its:
                        ti[str(am)] = its
                extra = [x_ for x_ in (l.get("nota") or "").split("; ") if NOTAS_MES.search(x_)]
                if extra:
                    nm[str(am)] = "; ".join(extra)
                f = _funcao(org, l.get("lotacao") or "", fem)
                if f:
                    fn.append((am, f))
            funcoes = [[f, de, (None if ate >= ultimo and x else ate)] for f, de, ate in _periodos(fn, sem_dados)]
            for c in comp.get("funcoes", []):  # as que a folha não mostra (no STJ, a lotação é sempre o gabinete do ministro)
                if c["id"] == m["id"]:
                    funcoes.append([c["funcao"], _am(c.get("de")), _am(c.get("ate"))])
            for c in comp.get("cnj_sem_folha", []):
                if c["id"] == m["id"]:
                    funcoes.append([c["funcao"], _am(c.get("de")), _am(c.get("ate"))])
            if not ls and not funcoes:
                continue

            def bloco(filtro):
                s = [x_ for x_ in serie if filtro(x_[0])]
                if not s:
                    return None
                cats = {}
                for am, vals in tc:
                    if filtro(am):
                        for p, v in zip(PARTES_SITE, vals):
                            if v:
                                cats[p] = cats.get(p, 0.0) + v
                return {"m": len(s), "mg": sum(1 for x_ in s if abs(x_[1]) >= 0.5), "mc": sum(1 for x_ in s if x_[2] >= 0.5), "me": 0,
                        "g": _r(sum(x_[1] for x_ in s)), "c": _r(sum(x_[2] for x_ in s)), "e": 0, "pm": 0, "mp": 0, "pu": 0, "ep": 0,
                        "cats": {k: _r(v) for k, v in cats.items() if abs(_r(v)) >= 1}}

            per = {}
            for ano in sorted({am // 100 for am, *_ in serie}):
                b = bloco(lambda am, a=ano: am // 100 == a)
                if b:
                    per[str(ano)] = b
            if serie:
                per["leg"] = bloco(lambda am: True)
            de = ini or comum.INICIO
            ate = None if fim is None else fim
            oc_per = [[f"{de // 100}{de % 100:02d}01", None if ate is None else f"{ate // 100}{ate % 100:02d}{monthrange(ate // 100, ate % 100)[1]:02d}"]]
            cargo = oc.get("cargo", ["", ""])[0 if fem else 1]
            foto = FOTOS / f"{m['id']}.webp"
            pessoas.append({
                "id": m["id"], "k": "t", "cid": org, "org": org, "n": m["nome"], "nc": m.get("nome_civil") or m["nome"], "g": cargo,
                "pt": None, "uf": None, "f": f"fotos/{m['id']}.webp" if foto.exists() else None, "fc": None,
                "x": x, "o": oc.get("pagina"), "sup": 0, "oc": oc_per, "per": per,
                "t": [[am, _r(g), _r(c), 0, 0, 0] for am, g, c in serie], "dt": {}, "vb": {}, "eq": None,
                "tc": tc, "ti": ti, "fn": funcoes, "rel": m.get("rel", []), "nm": nm,
                **({"obs": m["obs"]} if m.get("obs") else {}), **({"desde_antes": 1} if ini is None else {}),
            })
        fonte_mes = {str(int(f["ano_mes"])): f["url"] for f in fontes if int(f["pessoas"] or 0)}
        # reserva: meses de um órgão com fonte oficial que vieram do DadosJusBr (a fonte oficial não abriu)
        reserva = sorted(int(f["ano_mes"]) for f in fontes if VIA[org] == "oficial" and "dadosjusbr" in (f.get("url") or "")
                         and int(f["pessoas"] or 0))
        via = "oficial e DadosJusBr" if reserva else VIA[org]
        if org == "STM" and any("stm.jus.br" in (f.get("url") or "") and int(f["pessoas"] or 0) for f in fontes):
            via = "DadosJusBr e consulta oficial"  # os meses que o DadosJusBr não tem vêm da consulta oficial (stm.py)
        notas_org = NOTAS.get(org, []) + ([
            f"Meses que vieram do DadosJusBr (licença CC BY 4.0), porque a fonte oficial não abriu para o robô: "
            f"{', '.join(f'{m % 100:02d}/{m // 100}' for m in reserva)}. Voltam a vir da fonte oficial quando ela abrir."] if reserva else [])
        # STM: os meses que o DadosJusBr não tem e que vieram da consulta oficial do STM (coleta/judiciario/stm.py)
        oficiais = sorted(int(f["ano_mes"]) for f in fontes if "stm.jus.br" in (f.get("url") or "") and int(f["pessoas"] or 0))
        if oficiais:
            notas_org.append(f"{', '.join(f'{m % 100:02d}/{m // 100}' for m in oficiais)}: pela consulta oficial do STM (Remuneração "
                             f"de Servidores, aba Ministros Ativos), porque o DadosJusBr não tem esses meses; valores antes do "
                             f"abate-teto, como nos outros meses.")
        metas[org] = {
            "n": oc.get("nome", org), "sigla": org, "vagas": oc.get("vagas"), "no_cargo": no_cargo, "inicio": comum.INICIO,
            "ultimo_mes": ultimo, "anos": [str(a) for a in sorted({am // 100 for am in janela})], "via": via,
            "fonte": FONTE[org], "composicao": oc.get("pagina"), "fonte_mes": fonte_mes, "meses_sem_dados": sem_dados,
            "notas": notas_org, "fora": comp.get("fora", {}).get(org, []),
            **({"sem_folha": [{"id": c["id"], "funcao": c["funcao"], "de": _am(c.get("de")), "ate": _am(c.get("ate"))}
                              for c in comp.get("cnj_sem_folha", [])]} if org == "CNJ" else {}),
            "fontes": {"folha": FONTE[org], "composicao": oc.get("pagina"),
                       **({"dadosjusbr": "https://dadosjusbr.org", "licenca": "CC BY 4.0 (DadosJusBr)"} if VIA[org] == "DadosJusBr" or reserva else {})},
        }
    return metas, pessoas, tipos


def _fotos(pessoas, limite):
    """Fotos com licença livre no Wikimedia Commons (as mesmas regras do governo federal). Uma foto por pessoa: a página
    do TSE de quem vem do STF ou do STJ usa a foto da outra página."""
    from .. import fotos as F
    antigo = F.CARGO_OK
    F.CARGO_OK = re.compile(r"minist|juiz|juíz|magistr|desembarg|procurador|conselheir|justice|judge|presid", re.I)
    try:
        unicas = [p for p in pessoas if p["x"] and not (p["org"] == "TSE" and p["rel"])]
        return F._governo_commons([{"id": p["id"], "nome": p["n"], "nome_civil": p["nc"], "casa": "executivo"} for p in unicas], limite=limite)
    finally:
        F.CARGO_OK = antigo


def escrever(baixar_fotos=True, limite_fotos=40):
    metas, pessoas, tipos = montar()
    if baixar_fotos and pessoas:
        try:
            novas = _fotos(pessoas, limite_fotos)
            if novas:
                log(f"  {novas} fotos novas do Judiciário (Wikimedia Commons)")
        except Exception as e:  # noqa: BLE001 — foto é opcional
            log(f"  Fotos do Judiciário: {e}")
    from ..fotos import CREDITOS
    creditos = json.loads(CREDITOS.read_text(encoding="utf-8")).get("fotos", {}) if CREDITOS.exists() else {}
    por_id = {p["id"]: p for p in pessoas}
    for p in pessoas:
        for fid in [p["id"], *p["rel"]]:  # a própria foto ou a da outra página da mesma pessoa
            c = creditos.get(fid)
            if (FOTOS / f"{fid}.webp").exists() and c and c.get("arquivo"):
                p["f"] = f"fotos/{fid}.webp"
                p["fc"] = {"a": c.get("autor"), "l": c.get("licenca"), "u": c.get("pagina")}
                break
        else:
            p["f"], p["fc"] = None, None
    pessoas.sort(key=lambda p: (ORDEM.index(p["org"]), -p["x"], normalizar_nome(p["n"])))
    dados = {"meta": {"gerado_em": datetime.now().isoformat(timespec="seconds"), "tipos": tipos,
                      "categorias": CATEGORIAS, "partes": PARTES_SITE, "notas": NOTAS_GERAIS, "orgaos": metas},
             "p": pessoas}
    if gravar_json(SAIDA, dados):  # um órgão que sumiu ou perdeu muita gente: fica o arquivo anterior (util.gravar_com)
        log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(metas)} órgãos, {len(pessoas)} páginas, "
        f"{sum(p['x'] for p in pessoas)} no cargo)")
    return dados
