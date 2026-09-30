"""Rio de Janeiro: remuneração dos servidores do Estado (https://www.rj.gov.br/remuneracao/), pela API que a própria
página usa. A busca pelo nome é muito lenta (passa de 60 s e o servidor desiste), então consultamos pela matrícula de
cada um, mês a mês: a folha mensal, o adiantamento do 13º (em junho) e o 13º (em dezembro, cheio; o adiantamento é
descontado ali, e tiramos também na conta do site). Para o abate-teto, lemos os descontos de cada folha e guardamos só
o do teto. O governador em exercício desde março de 2026 (o presidente do Tribunal de Justiça) é pago pelo Tribunal e
não aparece nesta folha. O CPF (mascarado) da resposta não é guardado. Só abre de dentro do Brasil."""
from . import _http, comum

UF = "RJ"
FONTE = "https://www.rj.gov.br/remuneracao/"
API = "https://www.rj.gov.br/remuneracao/api/rest/remuneracoes"
# matrícula de cada um (achada uma vez pela busca do portal, que é lenta demais para rodar todo mês)
MATRICULAS = {"CLAUDIO BOMFIM DE CASTRO E SILVA": "50980505-2", "THIAGO PAMPOLHA GONCALVES": "50869230-4"}


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel(), refazer=3)  # o último mês sai aos poucos
    linhas, feitos = [], []
    ocup = [o for o in comum.ocupantes(UF) if MATRICULAS.get(o.get("folha_nome"))]
    try:
        for am in meses:
            quem = {o["folha_nome"]: ("vice" if o["cargo"] == "vice" else "gov") for o in ocup if comum.no_cargo(o, am)}
            for nome, papel in quem.items():
                d = _http.get(API, params={"page": 0, "size": 10, "ano": am // 100, "mes": am % 100, "matricula": MATRICULAS[nome]}, timeout=70) or {}
                rows = d.get("remuneracoes") or []
                if not rows:
                    continue
                p, redutor, cargo = {k: 0.0 for k in comum.PARTES}, 0.0, ""
                for x in rows:
                    v = float(x.get("totalVantagens") or 0)
                    ref = comum.normalizar_nome(x.get("folhaRef"))
                    p["decimo" if "13" in ref else "salario" if ref == "MENSAL" else "outros"] += v
                    det = _http.get(f"{API}/detalhe", params={"numCcSigrh": x["numCcSigrh"], "sistemaOrigem": x["sistemaOrigem"], "folhaRef": x["folhaRef"]}) or {}
                    redutor += sum(abs(float(val or 0)) for k, val in (det.get("descontos") or {}).items() if comum.eh_redutor(k))
                    cargo = x.get("funcaoCargo") or x.get("vinculo") or cargo
                linhas.append(comum.linha(am, papel, rows[0]["nomeServidor"], f'{cargo} ({rows[0].get("orgao")})', sum(p.values()), p, redutor))
            feitos.append(am)
    finally:
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
