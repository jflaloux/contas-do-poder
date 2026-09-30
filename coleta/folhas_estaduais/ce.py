"""Ceará: Ceará Transparente, remuneração dos servidores, um arquivo por mês (CSV sem linha de cabeçalho; a ordem das
colunas é a do XLSX do mesmo mês). Lemos o arquivo aos poucos, só as linhas com o nome do governador ou da vice: salário
bruto e abatimento do teto. As diárias (viagens) e os "outros descontos" (pessoais) não são guardados.
A vice Jade Romero recebeu até março de 2026 como secretária da Proteção Social e como conselheira do Detran, e só
depois como vice: entram todos os pagamentos com o nome dela.
Só abre de dentro do Brasil. O robots.txt proíbe as páginas de consulta, mas não a pasta de arquivos para download.
https://cearatransparente.ce.gov.br/portal-da-transparencia/servidores"""
from . import comum

UF = "CE"
FONTE = "https://cearatransparente.ce.gov.br/portal-da-transparencia/servidores"
URL = "https://cearatransparente.ce.gov.br/files/downloads/integration/servers/server_salaries/{am}/servidores_{am}.csv"
COLUNAS = ["servidor", "orgao", "cargo", "situacao", "total_descontos", "abate_teto", "outros_descontos", "bruto", "liquido", "diarias"]


def _texto(t):
    """Os arquivos de 2025 têm texto com a acentuação corrompida ("SECRETÃRIA"): desfaz quando dá."""
    t = (t or "").strip()
    try:
        return t.encode("latin-1").decode("utf-8") if "Ã" in t else t
    except (UnicodeEncodeError, UnicodeDecodeError):
        return t


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel())
    ocup = [o for o in comum.ocupantes(UF) if o.get("folha_nome")]
    linhas, feitos = [], set()
    for am in meses:
        nomes = {o["folha_nome"]: ("vice" if o["cargo"] == "vice" else "gov") for o in ocup if comum.no_cargo(o, am)}
        if not nomes:
            continue
        try:
            _, achadas = comum.linhas_csv(URL.format(am=am), list(nomes), encoding="utf-8", sep=",", colunas=COLUNAS)
        except Exception as e:  # noqa: BLE001 — mês ainda não publicado (404)
            if "404" in str(e):
                continue
            raise
        por_pessoa = {}
        for x in achadas:
            nome = comum.normalizar_nome(x["servidor"])
            papel = next((p for n, p in nomes.items() if comum.normalizar_nome(n) == nome), None)
            if not papel:
                continue
            t = por_pessoa.setdefault(nome, {"papel": papel, "bruto": 0.0, "redutor": 0.0, "cargos": []})
            t["bruto"] += float(x["bruto"] or 0)
            t["redutor"] += abs(float(x["abate_teto"] or 0))
            t["cargos"].append(f'{_texto(x["cargo"]) or "(sem cargo)"} ({_texto(x["orgao"])})')
        for nome, t in por_pessoa.items():
            linhas.append(comum.linha(am, t["papel"], nome, "; ".join(dict.fromkeys(t["cargos"])), t["bruto"], None, t["redutor"]))
            feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
