"""Rio Grande do Norte: remuneração dos servidores do Poder Executivo (SEAD), pela API do site oficial
https://remuneracao.rn.gov.br: em cada mês, a busca pelo nome de quem governou (a mesma consulta do campo "Nome" do
site), de onde tiramos só as linhas do Gabinete Civil (GAC) e da Vice-Governadoria: remuneração do mês, outras
remunerações e o redutor do teto (art. 37 da Constituição). Os descontos pessoais não são lidos. Não mostra o 13º nem as
férias. Só abre de dentro do Brasil.

A exportação em CSV por órgão (ExportarPorOrgao) passou a responder "429" mesmo com pausas longas (30/09/2026); a busca
pelo nome responde em JSON e aceita uma consulta a cada 10 s. A lista por órgão demora mais a sair que a busca pelo nome
(em 30/09/2026, agosto já aparecia pelo nome, mas não por órgão)."""
from . import _http, comum

UF = "RN"
FONTE = "https://remuneracao.rn.gov.br/"
API = "https://api.remuneracao.rn.gov.br"
ORGAOS = ("- GAC", "VICE-GOVERNADORIA")
PAUSA = 10  # a API limita os pedidos (HTTP 429 quando vêm rápido demais)


def _get(caminho, **params):
    """JSON da API; {} quando não há nada (a API responde "Não há registros a serem exibidos." em texto)."""
    r = _http.get(f"{API}/{caminho}", params=params, vazio=(404, 204), pausa=PAUSA, tentativas=6, json=False)
    return r.json() if r is not None and "json" in r.headers.get("content-type", "") else {}


def _por_nome(mes, nome):
    """Todas as linhas com exatamente esse nome (a busca do site acha também nomes mais longos)."""
    achadas, pagina = [], 1
    while True:
        d = _get("ObterPorNome", **mes, nome=nome, pagina=pagina)
        achadas += [x for x in d.get("itens") or [] if comum.normalizar_nome(x.get("nomeDoServidor") or "") == comum.normalizar_nome(nome)]
        if pagina >= int(d.get("ultimaPagina") or 0):
            return achadas
        pagina += 1


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel(), refazer=1)  # cada mês leva ~1 min (6 consultas, 10 s entre elas)
    linhas, feitos = [], []
    try:
        for am in meses:
            mes = {"mes": f"{am % 100:02d}", "ano": am // 100}
            antes = len(linhas)
            for nome, papel in comum.nomes_folha(UF, am).items():
                for x in _por_nome(mes, nome):
                    orgao = x.get("orgao") or ""
                    if not any(o in orgao for o in ORGAOS):
                        continue  # xará em outro órgão (há vários com o nome da governadora, aposentados e pensionistas)
                    sal, outras = comum.num(x.get("remuneracaoBruta")), comum.num(x.get("outrasRemuneracoes"))
                    linhas.append(comum.linha(am, comum.tp_do_cargo(x.get("cargo")) or papel, x["nomeDoServidor"], x.get("cargo"),
                                              sal + outras, {"salario": sal, "outros": outras}, abs(comum.num(x.get("redutor")))))
            if len(linhas) > antes:  # sem ninguém = mês ainda não publicado (tenta de novo na próxima vez)
                feitos.append(am)
    finally:  # se o tempo acabar no meio, guarda os meses já feitos
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
