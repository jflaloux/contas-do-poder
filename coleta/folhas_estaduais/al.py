"""Alagoas: Portal da Transparência, API pública documentada (https://transparencia.al.gov.br/portal/api).
Acha o governador e o vice pelo nome na lista do mês e lê o histórico do ano de cada um (um pedido por pessoa e ano),
com a remuneração base, a comissão (é por ela que o governador recebe), os benefícios, as verbas eventuais e o
abate-teto. A folha "13" de cada ano é o 13º, que entra em dezembro. O CPF (mascarado) da resposta não é guardado.
Só abre de dentro do Brasil."""
from . import _http, comum

UF = "AL"
FONTE = "https://transparencia.al.gov.br/pessoal/servidores/"
BASE = "https://transparencia.al.gov.br/pessoal"
H = {"X-Requested-With": "XMLHttpRequest"}


def _id(nome, am):
    d = _http.get(f"{BASE}/json-servidores/", params={"ano": am // 100, "mes": f"{am % 100:02d}", "limit": 20, "offset": 0, "nome": nome}, headers=H) or {}
    for x in d.get("rows") or []:
        if comum.normalizar_nome(x["nome"]) == comum.normalizar_nome(nome):
            return x["funcionario_id"]
    return None


def coletar():
    ultimo = comum.ultimo_possivel()
    meses = comum.a_fazer(UF, ultimo)
    if not meses:
        return 0
    linhas, feitos = [], set()
    for o in comum.ocupantes(UF):
        nome = o.get("folha_nome")
        if not nome:
            continue
        meus = [am for am in meses if comum.no_cargo(o, am)]
        if not meus:
            continue
        fid = _id(nome, meus[-1]) or _id(nome, meus[0])
        if not fid:
            comum.avisar(UF, f"não achei {nome} na folha")
            continue
        papel = "vice" if o["cargo"] == "vice" else "gov"
        por_mes = {}
        for ano in sorted({am // 100 for am in meus}):
            d = _http.get(f"{BASE}/json-perfil-servidor/{fid}/", params={"ano": ano, "limit": 30, "offset": 0}, headers=H) or {}
            det = d.get("detalhe") or {}
            cargo = det.get("funcao") or det.get("cargo") or ""
            for r in d.get("rows") or []:
                a, m = (int(x) for x in r["ano_mes"].split("/"))
                n = lambda k: comum.num(r.get(k)) if r.get(k) not in (None, "") else 0.0  # "32.323,19"
                if m == 13:  # folha do 13º: entra em dezembro
                    am, partes = a * 100 + 12, {"decimo": n("remuneracao_base") + n("comissao") + n("eventuais")}
                    partes["beneficios"] = n("beneficios")
                    partes["outros"] = n("horas_extras") + n("judiciais")
                else:
                    am = a * 100 + m
                    partes = {"salario": n("remuneracao_base") + n("comissao"), "beneficios": n("beneficios"),
                              "outros": n("eventuais") + n("horas_extras") + n("judiciais")}
                if am not in meus:
                    continue
                t = por_mes.setdefault(am, {"partes": {k: 0.0 for k in comum.PARTES}, "redutor": 0.0, "cargo": cargo})
                for k, v in partes.items():
                    t["partes"][k] += v
                t["redutor"] += abs(n("teto_redutor"))
        for am, t in sorted(por_mes.items()):
            p = t["partes"]
            linhas.append(comum.linha(am, papel, nome, t["cargo"], sum(p.values()), p, t["redutor"]))
            feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
