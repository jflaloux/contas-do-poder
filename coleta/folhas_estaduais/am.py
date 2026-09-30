"""Amazonas: Portal da Transparência, remuneração dos servidores, pela API que o próprio portal usa (sem chave).
Busca pelo nome e ano (vêm todos os meses do ano): remuneração bruta total e desconto do teto. Não separa salário, 13º
e férias. O vice Tadeu de Souza é procurador do Estado e recebeu como vice pelo cargo de origem.
Só abre de dentro do Brasil. https://www.transparencia.am.gov.br/pessoal/"""
from . import _http, comum

UF = "AM"
FONTE = "https://www.transparencia.am.gov.br/pessoal/"
API = "https://www.transparencia.am.gov.br/wp-json/transparencia/v1/remuneracoes"


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel())
    if not meses:
        return 0
    linhas, feitos = [], set()
    for o in comum.ocupantes(UF):
        nome = o.get("folha_nome")
        meus = [am for am in meses if comum.no_cargo(o, am, folga=0)]
        if not nome or not meus:
            continue
        papel = "vice" if o["cargo"] == "vice" else "gov"
        por_mes = {}
        for ano in sorted({am // 100 for am in meus}):
            pagina = 0
            while True:
                d = _http.get(API, params={"nome": nome, "ano": ano, "page": pagina, "size": 100}) or {}
                for x in d.get("content") or []:
                    am = int(x["competenciaAno"]) * 100 + int(x["competenciaMes"])
                    if am not in meus or comum.normalizar_nome(x["nomeFuncionario"]) != comum.normalizar_nome(nome):
                        continue
                    t = por_mes.setdefault(am, {"bruto": 0.0, "redutor": 0.0, "cargo": set()})
                    t["bruto"] += float(x.get("remuneracaoLegalTotal") or 0)
                    t["redutor"] += abs(float(x.get("descontoTeto") or 0))
                    t["cargo"].add(" / ".join(dict.fromkeys(c for c in (x.get("funcao"), x.get("cargo")) if c and c != "NAO INFORMADO")))
                pagina += 1
                if pagina >= int(d.get("totalPages") or 0):
                    break
        for am, t in sorted(por_mes.items()):
            linhas.append(comum.linha(am, papel, nome, "; ".join(sorted(t["cargo"])), t["bruto"], None, t["redutor"]))
            feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
