"""Piauí: Portal da Transparência, API REST pública (https://api.transparencia.pi.gov.br/docs/).
Busca o nome exato no mês ("referência" 1 a 12) e na folha do 13º (referência 13, que entra em dezembro): remuneração
básica e variável (o subsídio), eventual (1/3 de férias, adiantamento do 13º) e a bruta. Sem CPF no que guardamos.
Só abre de dentro do Brasil."""
from . import _http, comum

UF = "PI"
FONTE = "https://transparencia.pi.gov.br/"
API = "https://api.transparencia.pi.gov.br/api/v2/servidores"


def _achar(nome, ano, ref):
    d = _http.get(f"{API}/{ano}/{ref}/", params={"nome__exact": nome, "page_size": 10}) or {}
    return d.get("results") or []


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel())
    if not meses:
        return 0
    # referências publicadas em cada ano: [{"referencia": 13}, {"referencia": 12}, ...] (13 = folha do 13º)
    refs = {ano: {int(r["referencia"]) for r in _http.get(f"{API}/referencias/{ano}/") or []} for ano in sorted({am // 100 for am in meses})}
    linhas, feitos = [], set()
    for o in comum.ocupantes(UF):
        nome = o.get("folha_nome")
        meus = [am for am in meses if comum.no_cargo(o, am)]
        if not nome or not meus:
            continue
        papel = "vice" if o["cargo"] == "vice" else "gov"
        for am in meus:
            ano, mes = divmod(am, 100)
            if refs.get(ano) and mes not in refs[ano]:
                continue
            p = {k: 0.0 for k in comum.PARTES}
            bruto, cargo = 0.0, ""
            for x in _achar(nome, ano, mes):
                p["salario"] += float(x.get("remuneracao_basica") or 0) + float(x.get("remuneracao_variavel") or 0)
                p["outros"] += float(x.get("remuneracao_eventual") or 0)
                bruto += float(x.get("remuneracao_bruta") or 0)
                cargo = x.get("cargo_nome") or f'{"Vice-governador" if papel == "vice" else "Governador"} ({x.get("orgao_nome")})'
            if mes == 12 and 13 in refs.get(ano, set()):
                for x in _achar(nome, ano, 13):
                    p["decimo"] += float(x.get("remuneracao_bruta") or 0)
                    bruto += float(x.get("remuneracao_bruta") or 0)
            if not bruto:
                continue
            if abs(sum(p.values()) - bruto) > 1:  # as partes não fecham com o total: fica só o total
                p = None
            linhas.append(comum.linha(am, papel, nome, cargo, bruto, p))
            feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
