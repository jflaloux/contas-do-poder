"""STF, STM e TSE pelo DadosJusBr (https://dadosjusbr.org, licença CC BY 4.0), enquanto a fonte oficial não abre para o
robô: a consulta do STF (egesp-portal.stf.jus.br) e a do STM (www2.stm.jus.br/rem_web) são proibidas no robots.txt (a
exceção depende de uma conversa com um advogado) e o site do TSE responde 403 a robôs (não contornamos).

O DadosJusBr coleta a folha oficial todo mês e publica um pacote por órgão e mês (contracheque.csv e remuneracao.csv,
item por item), com uma cópia do arquivo original baixado. O STF vem da consulta oficial do STF (coletor próprio do
DadosJusBr); o STM e o TSE, das planilhas que os tribunais mandam ao CNJ (Painel de Remuneração dos Magistrados).
Daqui sai só o que o órgão paga: a "remuneração do órgão de origem" (o salário do STF ou do STJ de quem está no TSE)
fica de fora e as diárias vão para a coluna própria. Os descontos (itens de tipo D) não são lidos.

STF: os valores saem da cópia do arquivo oficial que o DadosJusBr guarda (backups/), e não do pacote padronizado: em
dez/2025 o arquivo do STF repete cada coluna e cada linha, e o pacote daquele mês ficou com as colunas trocadas. Sinal
das férias: em jul/2026 o arquivo traz na coluna "Férias" um valor que os totais do próprio arquivo subtraem
(compensação de um adiantamento), e o pacote do DadosJusBr soma esse valor; o robô confere com os totais do arquivo e,
quando a conta só fecha com o sinal trocado, troca o sinal.
"""
import csv
import io
import re
import zipfile

from ..util import _sessao, dormir, log, verificar_prazo
from . import comum

API = "https://api.dadosjusbr.org/v2/dados"
S3 = "https://dadosjusbr-public.s3.amazonaws.com"
PAUSA = 1
NOTA = ("via DadosJusBr (CC BY 4.0), que copia a folha oficial do {fonte}; cópia do arquivo original: {backup}")
ORGAOS = {
    "STF": {"id": "stf", "cargo": "Ministro do Supremo Tribunal Federal", "funcao": lambda f: f.strip().upper() == "MINISTRO",
            "fonte": "STF (consulta egesp-portal.stf.jus.br)"},
    "STM": {"id": "stm", "cargo": "Ministro do Superior Tribunal Militar", "funcao": lambda f: f.strip().upper().startswith("MINISTRO DO SUPERIOR TRIBUNAL MILITAR"),
            "fonte": "STM, enviada ao Painel de Remuneração dos Magistrados do CNJ"},
    "TSE": {"id": "tse", "cargo": "Ministro do Tribunal Superior Eleitoral", "funcao": lambda f: f.strip().upper() == "MINISTRO",
            "fonte": "TSE, enviada ao Painel de Remuneração dos Magistrados do CNJ"},
}


def _get(url, **kw):
    verificar_prazo()
    r = _sessao().get(url, timeout=120, **kw)
    r.raise_for_status()
    dormir(PAUSA)
    return r


# reserva: o órgão que tem robô próprio (fonte oficial) passa a vir do DadosJusBr, só nos meses que o robô oficial não
# leu, quando a fonte oficial não abre (coleta/judiciario/__init__.py). Quando ela volta, o robô oficial relê esses meses.
RESERVA = {
    "STJ": {"id": "stj", "cargo": "Ministro do Superior Tribunal de Justiça",
            "funcao": lambda f: f.strip().upper().startswith("MINISTRO DO SUPERIOR TRIBUNAL DE JUSTI"),
            "fonte": "STJ, enviada ao Painel de Remuneração dos Magistrados do CNJ"},
    # TST e CNJ ficam sem reserva: conferido em 03/10/2026 (TST ago/2026, CNJ ago/2026), o pacote do DadosJusBr não bate
    # com a fonte oficial (no TST, metade dos ministros com valores diferentes, férias negativas e a folha suplementar à
    # parte; no CNJ, gratificações que a página do CNJ não mostra). No STJ (jun/2026), 32 de 33 iguais; no PGR, igual.
    "PGR": {"id": "mpf", "cargo": "Procurador-Geral da República", "funcao": None,  # o PGR sai pelo nome (composicao.json)
            "fonte": "MPF (planilhas de remuneração dos membros ativos)"},
}
NOTA_RESERVA = ("via DadosJusBr (CC BY 4.0), na reserva: a fonte oficial não abriu para o robô; cópia da folha do {fonte} "
                "feita pelo DadosJusBr")


def _cfg(sigla):
    return ORGAOS.get(sigla) or RESERVA[sigla]


def disponiveis(sigla):
    d = _get(f"{API}/{_cfg(sigla)['id']}").json()
    return [int(c["ano"]) * 100 + int(c["mes"]) for c in d.get("coletas") or []]


def pacote(sigla, am):
    o = _cfg(sigla)["id"]
    return f"{S3}/{o}/datapackage/{o}-{am // 100}-{am % 100}.zip"


def backup(sigla, am):
    o = _cfg(sigla)["id"]
    return f"{S3}/{o}/backups/{o}-{am // 100}-{am % 100}.zip"


def _parte_mpf(categoria, item):
    """As planilhas do MPF (pacote do DadosJusBr): as mesmas colunas que coleta/judiciario/pgr.py lê."""
    c, i = categoria.lower(), item.lower().strip()
    if c.startswith("verbas indeniz"):
        return "indenizacoes"
    if c.startswith("outras remunera"):
        return "vantagens_eventuais"
    for comeco, parte in (("remuneração do cargo efetivo", "subsidio"), ("outras verbas remunerat", "vantagens_pessoais"),
                          ("função de confiança", "outras"), ("gratificação natalina", "decimo_terceiro"), ("férias", "ferias"),
                          ("abono de perman", "abono_permanencia")):
        if i.startswith(comeco):
            return parte
    return "outras"


def _parte(sigla, categoria, item):
    """Em que parte entra um item do remuneracao.csv (tipo R/B ou R/O); None = fica de fora."""
    if sigla == "PGR":
        return _parte_mpf(categoria, item)
    c, i = categoria.lower(), item.lower().strip()
    if "órgão de origem" in i or "orgao de origem" in i:
        return None
    if i == "diárias" or i == "diarias":
        return "diarias"
    # planilha do Painel do CNJ: contracheque (subsídio), direitos pessoais, indenizações, direitos eventuais
    if c == "contracheque":
        return "subsidio" if i.startswith("subsídio") else "outras"
    if c == "direitos-pessoais":
        return "abono_permanencia" if i.startswith("abono de perman") else "vantagens_pessoais"
    if c == "indenizações" or c == "indenizacoes":
        return "indenizacoes"
    if c == "direitos-eventuais":
        if "férias" in i or "ferias" in i:
            return "ferias"
        if "natalina" in i:
            return "decimo_terceiro"
        return "vantagens_eventuais"
    return "outras"


# colunas do arquivo do STF -> partes (as de desconto, os totais e o líquido não entram)
COLUNAS_STF = {"Vencimentos / Subsídios": "subsidio", "Vantagens Pessoais": "vantagens_pessoais", "Abono de Permanência": "abono_permanencia",
               "Vantagens de natureza periódica/eventual ou relativas às lotações dos servidores": "vantagens_eventuais",
               "Exercício de cargo em comissão/função comissionada": "outras", "Férias": "ferias",
               "Gratificação natalina e antecipação": "decimo_terceiro", "Auxílios e benefícios": "indenizacoes",
               "Indenizações": "indenizacoes", "Auxílio Moradia": "indenizacoes",
               "Exercícios Anteriores e licença prêmio convertida em pecúnia": "vantagens_eventuais"}
# o que o arquivo soma em "outras verbas" (a diferença entre o bruto somado com outras verbas e o bruto após o teto)
OUTRAS_VERBAS_STF = ("Férias", "Gratificação natalina e antecipação", "Auxílios e benefícios", "Indenizações",
                     "Exercícios Anteriores e licença prêmio convertida em pecúnia", "Auxílio Moradia")


def ler_stf(conteudo_backup):
    """[{coluna: texto}] dos ministros na cópia do HTML oficial do STF. Em dez/2025 o arquivo repete cada coluna e cada
    linha (valores iguais): fica a primeira de cada."""
    import html as H
    with zipfile.ZipFile(io.BytesIO(conteudo_backup)) as z:
        nome = next(n for n in z.namelist() if n.endswith(".html"))
        s = z.read(nome).decode("utf-8", "replace")
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    limpa = lambda x: H.unescape(re.sub(r"<[^>]+>", "", x)).strip()
    tabela = next(t for t in re.findall(r"<table.*?</table>", s, re.S) if "Matricula" in t)
    cab = [limpa(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", tabela, re.S)]
    saida, vistos = [], set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabela, re.S):
        tds = [limpa(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) != len(cab):
            continue
        d = {}
        for h, v in zip(cab, tds):
            d.setdefault(h, v)
        chave = (d.get("Matricula"), d.get("Nome"))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(d)
    return saida


def mes_stf(am):
    """STF: os valores saem da cópia do arquivo oficial (backups/) e o pacote padronizado só serve de referência: em
    dez/2025 o pacote do DadosJusBr tem as colunas trocadas (o arquivo daquele mês repete cada coluna)."""
    cfg = ORGAOS["STF"]
    url = backup("STF", am)
    linhas = []
    for d in ler_stf(_get(url).content):
        if not cfg["funcao"](d.get("Situação Funcional") or d.get("Cargo Efetivo") or ""):
            continue
        partes, itens = {x: 0.0 for x in comum.PARTES}, []
        for col, parte in COLUNAS_STF.items():
            v = comum.numero(d.get(col))
            partes[parte] = round(partes[parte] + v, 2)
            if v and (parte == "indenizacoes" or col.startswith("Exercícios")):
                itens.append(("Arquivo do STF", col, v))
        nota = (f"via DadosJusBr (CC BY 4.0): cópia do arquivo oficial do {cfg['fonte']}, guardada pelo DadosJusBr; "
                f"pacote padronizado: {pacote('STF', am)}")
        outras_arquivo = round(comum.numero(d.get("Remuneração Bruta após o teto constitucional somada com outras verbas"))
                               - comum.numero(d.get("Total bruto após teto constitucional")), 2)
        outras_partes = round(sum(comum.numero(d.get(c)) for c in OUTRAS_VERBAS_STF), 2)
        fer = partes["ferias"]
        if abs(outras_arquivo - outras_partes) > 0.05:
            if fer and abs(outras_arquivo - (outras_partes - 2 * fer)) <= 0.05:
                partes["ferias"] = -fer
                nota += (f"; a coluna Férias do arquivo traz {fer:.2f}, e os totais do próprio arquivo subtraem esse valor "
                         "(o sinal foi trocado aqui, e o pacote do DadosJusBr soma)")
            else:
                nota += "; os totais do arquivo não batem com a soma das partes (a conferir)"
                log(f"  STF {am} {d.get('Nome')}: totais do arquivo ({outras_arquivo:.2f}) ≠ partes ({outras_partes:.2f})")
        if comum.numero(d.get("Abate teto")):
            nota += "; com abate-teto no arquivo (não incluído aqui)"
        linhas.append(comum.linha("STF", am, d.get("Nome"), cfg["cargo"], d.get("Lotação"), partes, None, itens, url, nota))
    return linhas


def mes(sigla, am):
    if sigla == "STF":
        return mes_stf(am)
    cfg = _cfg(sigla)
    url = pacote(sigla, am)
    z = zipfile.ZipFile(io.BytesIO(_get(url).content))
    texto = lambda n: io.StringIO(z.read(n).decode("utf-8"))
    if cfg["funcao"]:
        quem = lambda r: cfg["funcao"](r.get("funcao") or "")
    else:  # PGR: pelo nome de quem a composição diz que é o PGR
        nomes = {comum.normalizar_nome(n) for m in comum.composicao().get("membros", []) if m["orgao"] == sigla
                 for n in [m["nome_civil"], *m.get("folha", [])]}
        quem = lambda r: comum.normalizar_nome(r.get("nome")) in nomes
    fora = ("APOSENTADO", "EXONERADO", "PENSIONISTA", "INATIVO")  # na reserva do STJ, o pacote traz também quem saiu
    pessoas = {r["id_contracheque"]: r for r in csv.DictReader(texto("contracheque.csv"), delimiter=";")
               if quem(r) and not (sigla in RESERVA and (r.get("local_trabalho") or "").strip().upper() in fora)}
    por = {k: {"partes": {}, "diarias": 0.0, "itens": [] } for k in pessoas}
    for r in csv.DictReader(texto("remuneracao.csv"), delimiter=";"):
        if r["id_contracheque"] not in por or not r["tipo"].startswith("R"):
            continue  # só o que é pago (R/B e R/O); os descontos (D) não são lidos
        parte, v = _parte(sigla, r["categoria"], r["item"]), comum.numero(r["valor"])
        if parte is None or not v:
            continue
        p = por[r["id_contracheque"]]
        if parte == "diarias":
            p["diarias"] += v
            continue
        p["partes"][parte] = round(p["partes"].get(parte, 0.0) + v, 2)
        item = r["item"].strip()
        if parte in ("indenizacoes", "vantagens_eventuais", "vantagens_pessoais", "ferias"):
            grupo = r["categoria"].strip() if sigla == "PGR" else r["categoria"].replace("-", " ").capitalize()
            p["itens"].append((grupo, " ".join(item.split()) if item not in ("0", "") else "item sem nome na planilha do tribunal", v))
    linhas = []
    for k, r in pessoas.items():
        p = por[k]
        partes = {x: p["partes"].get(x, 0.0) for x in comum.PARTES}
        nota = (NOTA_RESERVA.format(fonte=cfg["fonte"]) if sigla in RESERVA else NOTA.format(fonte=cfg["fonte"], backup=backup(sigla, am)))
        linhas.append(comum.linha(sigla, am, r["nome"], cfg["cargo"], r.get("local_trabalho") or "", partes,
                                  round(p["diarias"], 2), p["itens"], url, nota))
    return linhas


def coletar(sigla):
    disp = disponiveis(sigla)
    fazer = comum.a_fazer(sigla, disp)
    linhas, lidos = [], []
    try:
        for am in fazer:
            ls = mes(sigla, am)
            linhas += ls
            lidos.append({"ano_mes": am, "pessoas": len(ls), "url": backup(sigla, am) if sigla == "STF" else pacote(sigla, am)})
    finally:
        n = comum.gravar(sigla, linhas, lidos)
        if lidos:
            log(f"  {sigla} (DadosJusBr): {len(lidos)} meses lidos ({lidos[0]['ano_mes']} a {lidos[-1]['ano_mes']}), {n} linhas")
    return n


def reserva(sigla):
    """O órgão com robô oficial (STJ, TST, CNJ, PGR) pelo DadosJusBr, só nos meses que o robô oficial não leu: chamado
    quando a fonte oficial falha. Os meses ficam marcados pela fonte (o endereço do DadosJusBr em fontes.csv) e o robô
    oficial os relê quando a fonte voltar (comum.a_fazer)."""
    oficiais = {int(x["ano_mes"]) for x in comum.ler_fontes(sigla) if "dadosjusbr" not in (x.get("url") or "")}
    fazer = [am for am in disponiveis(sigla) if am >= comum.INICIO and am not in oficiais]
    linhas, lidos = [], []
    try:
        for am in fazer:
            ls = mes(sigla, am)
            linhas += ls
            lidos.append({"ano_mes": am, "pessoas": len(ls), "url": pacote(sigla, am)})
    finally:
        n = comum.gravar(sigla, linhas, lidos)
        if lidos:
            log(f"  {sigla} pela reserva (DadosJusBr): {len(lidos)} meses ({lidos[0]['ano_mes']} a {lidos[-1]['ano_mes']}), {n} linhas")
    return n

