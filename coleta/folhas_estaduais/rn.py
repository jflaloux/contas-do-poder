"""Rio Grande do Norte: remuneração dos servidores do Poder Executivo (SEAD), pela API do site oficial
https://remuneracao.rn.gov.br: em cada mês, a lista de órgãos e o arquivo (CSV) do Gabinete Civil (GAC) e da
Vice-Governadoria, de onde tiramos só as linhas de quem tem o cargo de governador ou de vice: remuneração do mês, outras
remunerações e o redutor do teto (art. 37 da Constituição). Os descontos pessoais não são lidos.
Não mostra o 13º nem as férias. Só abre de dentro do Brasil."""
import csv
import io

from . import _http, comum

UF = "RN"
FONTE = "https://remuneracao.rn.gov.br/"
API = "https://api.remuneracao.rn.gov.br"
ORGAOS = ("- GAC", "VICE-GOVERNADORIA")
PAUSA = 10  # a API limita os pedidos (HTTP 429 quando vêm rápido demais)


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel())
    linhas, feitos = [], []
    try:
        for am in meses:
            mes = {"mes": f"{am % 100:02d}", "ano": am // 100}
            d = _http.get(f"{API}/ObterPorOrgao", params={**mes, "pagina": 1}, vazio=(404, 204), pausa=PAUSA, tentativas=6) or {}
            ids = [x["id"] for x in d.get("itens") or [] if any(o in (x.get("orgao") or "") for o in ORGAOS)]
            if not ids:
                continue  # mês ainda não publicado
            for i in ids:
                r = _http.get(f"{API}/ExportarPorOrgao", params={**mes, "id": i}, json=False, pausa=PAUSA, tentativas=6)
                texto = r.content.decode("utf-8-sig", "replace")
                if not texto.startswith("Nome;"):  # veio outra coisa (página de erro): não marca o mês como feito
                    raise ValueError(f"ExportarPorOrgao {am} {i}: resposta inesperada")
                for x in csv.DictReader(io.StringIO(texto), delimiter=";"):
                    tp = comum.tp_do_cargo(x.get("CargoFuncao"))
                    if not tp:
                        continue
                    sal, outras = comum.num(x.get("RemuneracaoMes")), comum.num(x.get("OutrasRemuneracoes"))
                    linhas.append(comum.linha(am, tp, x["Nome"], x["CargoFuncao"], sal + outras, {"salario": sal, "outros": outras},
                                              abs(comum.num(x.get("RedutorArt.37/CF")))))
            feitos.append(am)
    finally:  # se o tempo acabar no meio, guarda os meses já feitos
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
