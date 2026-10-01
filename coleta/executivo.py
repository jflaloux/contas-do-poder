"""Robô do Poder Executivo federal: presidente, vice-presidente e ministros de Estado.

Fonte: Portal da Transparência do Governo Federal (CGU), arquivos de download.
- Servidores, mensal (~80 MB): BASE/servidores/AAAAMM_Servidores_SIAPE
    Cadastro.csv: quem ocupa cada cargo no mês; Remuneracao.csv: quanto recebeu.
- Honorários (jetons), mensal: BASE/servidores/AAAAMM_Honorarios_Jetons
    o que cada um recebeu por participar de conselhos (estatais, Sistema S...).
- Viagens a serviço, anual (~150 MB): BASE/viagens/AAAA
    Viagem.csv: diárias, passagens e outros gastos de cada viagem.

Os arquivos são grandes, mas só interessam ~40 pessoas. Guardamos só as linhas delas em
dados/portal_transparencia/ (poucos KB por mês). Essa pasta vai para o Git: assim o robô semanal só
baixa os meses novos, sem pedir ao Portal os 40 meses de novo. O arquivo baixado é descartado.
O Portal publica os salários com uns 2 meses de atraso; mês ainda não publicado é pulado.

Educação com o Portal: no máximo um download a cada 30 s. Se o Portal pedir verificação
humana (bloqueio temporário, resposta 405/429), o robô NÃO tenta contornar: para de baixar e usa o
que já está no cache. Na semana seguinte continua de onde parou.
"""
import csv
import io
import time
import zipfile

import pandas as pd
import requests

from .config import ANOS, BRUTOS, DADOS, meses_da_legislatura
from .util import _sessao, cache_valido, ler_json, log, normalizar_nome, numero_br, salvar_json, verificar_prazo

BASE = "https://portaldatransparencia.gov.br/download-de-dados"
C = DADOS / "portal_transparencia"
INTERVALO = 30  # segundos entre downloads do Portal (com menos que isso ele pede verificação humana)
_ultimo_download = [0.0]
CARGOS = {"PRESIDENTE DA REPUBLICA": "presidente", "VICE-PRESIDENTE DA REPUBLICA": "vice",
          "MINISTRO DE ESTADO": "ministro"}
# colunas da remuneração que usamos (nome do Portal, sem acentos, em maiúsculas -> nome curto)
REMUNERACAO = {
    "REMUNERACAO BASICA BRUTA (R$)": "bruta",
    "ABATE-TETO (R$)": "abate_teto",
    "GRATIFICACAO NATALINA (R$)": "natalina",
    "ABATE-TETO DA GRATIFICACAO NATALINA (R$)": "abate_natalina",
    "FERIAS (R$)": "ferias",
    "OUTRAS REMUNERACOES EVENTUAIS (R$)": "eventuais",
    "TOTAL DE VERBAS INDENIZATORIAS (R$)(*)": "indenizatorias",
}


class NaoPublicado(Exception):
    """O Portal ainda não publicou este arquivo."""


class PortalBloqueou(Exception):
    """O Portal pediu verificação humana (bloqueio temporário por excesso de pedidos)."""


def _baixar_zip(caminho, tentativas=3):
    """Baixa um zip do Portal. O endereço redireciona para o arquivo; 403/404 = ainda não publicado."""
    verificar_prazo()
    for i in range(tentativas):
        espera = _ultimo_download[0] + INTERVALO - time.time()
        if espera > 0:
            time.sleep(espera)
        _ultimo_download[0] = time.time()
        try:
            r = _sessao().get(f"{BASE}/{caminho}", timeout=300)
            if r.status_code in (403, 404):
                raise NaoPublicado(caminho)
            if r.status_code in (405, 429) or b"Human Verification" in r.content[:3000]:
                raise PortalBloqueou(caminho)
            r.raise_for_status()
            return zipfile.ZipFile(io.BytesIO(r.content))
        except requests.RequestException:
            if i == tentativas - 1:
                raise
            time.sleep(5 * (i + 1))


def _texto(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin1")


def _linhas(z, final, filtro):
    """Cabeçalho e linhas (já separadas em colunas) do CSV que termina em `final`, só as que passam no filtro (bytes)."""
    nome = next(n for n in z.namelist() if n.endswith(final))
    with z.open(nome) as f:
        cab = next(csv.reader([_texto(next(f))], delimiter=";"))
        saida = [next(csv.reader([_texto(l)], delimiter=";")) for l in f if filtro(l)]
    return cab, saida


_bloqueado = [False]


def _avisar_bloqueio():
    if not _bloqueado[0]:
        log("  ATENÇÃO: o Portal da Transparência pediu verificação humana (excesso de pedidos). "
            "Paramos de baixar e usamos o que já está no cache; o resto fica para a próxima vez.")
    _bloqueado[0] = True


# ---------------------------------------------------------------- mês a mês
def _mes(ano, mes):
    """Quem ocupava os cargos no mês, quanto recebeu e os jetons. Guarda em cache."""
    aaaamm = f"{ano}{mes:02d}"
    arq = C / f"{aaaamm}.json"
    recente = (ano * 12 + mes) >= (time.localtime().tm_year * 12 + time.localtime().tm_mon - 4)
    if cache_valido(arq, 30 if recente else None) or (_bloqueado[0] and arq.exists()):
        return ler_json(arq)
    if _bloqueado[0]:
        return None
    try:
        z = _baixar_zip(f"servidores/{aaaamm}_Servidores_SIAPE")
    except NaoPublicado:
        return None
    except PortalBloqueou:
        _avisar_bloqueio()
        return ler_json(arq) if arq.exists() else None
    cab, linhas = _linhas(z, "_Cadastro.csv", lambda l: b"MINISTRO DE ESTADO" in l or b"PRESIDENTE DA REPUBLICA" in l)
    i = {c: k for k, c in enumerate(cab)}
    pessoas = {}
    for r in linhas:
        cargo = CARGOS.get(r[i["DESCRICAO_CARGO"]].strip().upper())
        if not cargo:
            continue
        p = pessoas.setdefault(r[i["Id_SERVIDOR_PORTAL"]], {"nome": r[i["NOME"]].strip(), "cpf": r[i["CPF"]], "cargos": [], "remuneracao": None})
        uorg = r[i["UORG_EXERCICIO"]] if r[i["UORG_EXERCICIO"]] not in ("Inválido", "Sem informação") else r[i["UORG_LOTACAO"]]
        p["cargos"].append({"cargo": cargo, "cod_orgao": r[i["COD_ORG_EXERCICIO"]], "orgao": r[i["ORG_EXERCICIO"]], "uorg": uorg,
                            "nomeacao": r[i.get("DATA_NOMEACAO_CARGOFUNCAO", i["DATA_INGRESSO_CARGOFUNCAO"])] or r[i["DATA_INGRESSO_CARGOFUNCAO"]]})
    ids = {f'"{id_}"'.encode() for id_ in pessoas}
    cab, linhas = _linhas(z, "_Remuneracao.csv", lambda l: (lambda p: len(p) > 2 and p[2] in ids)(l.split(b";", 3)))
    col = {REMUNERACAO[normalizar_nome(c)]: k for k, c in enumerate(cab) if normalizar_nome(c) in REMUNERACAO}
    for r in linhas:
        p = pessoas[r[2]]
        valores = {nome: numero_br(r[k]) or 0.0 for nome, k in col.items()}
        if p["remuneracao"]:  # mais de uma linha: soma
            valores = {k: round(v + p["remuneracao"].get(k, 0.0), 2) for k, v in valores.items()}
        p["remuneracao"] = valores
    del z
    # jetons (arquivo pequeno)
    try:
        zj = _baixar_zip(f"servidores/{aaaamm}_Honorarios_Jetons")
        cab, linhas = _linhas(zj, ".csv", lambda l: (lambda p: len(p) > 2 and p[2] in ids)(l.split(b";", 3)))
        i = {c: k for k, c in enumerate(cab)}
        for r in linhas:
            pessoas[r[i["Id_SERVIDOR_PORTAL"]]].setdefault("jetons", []).append(
                {"empresa": r[i["EMPRESA"]].strip(), "valor": numero_br(r[i["VALOR"]]) or 0.0})
    except NaoPublicado:
        pass
    except PortalBloqueou:
        _avisar_bloqueio()
        return None  # sem os jetons o mês fica incompleto: tenta de novo na próxima vez
    dados = {"ano": ano, "mes": mes, "pessoas": pessoas}
    salvar_json(arq, dados)
    return dados


# ---------------------------------------------------------------- viagens
def _viagens(ano, quem):
    """Viagens do ano feitas pelas pessoas em `quem` ({(cpf, nome_normalizado): id}). Soma por pessoa e mês de início."""
    arq = C / f"viagens_{ano}.json"
    atual = ano >= time.localtime().tm_year - (1 if time.localtime().tm_mon <= 3 else 0)
    chave_quem = sorted(f"{c}|{n}" for c, n in quem)
    if cache_valido(arq, 6 if atual else 45) or (_bloqueado[0] and arq.exists()):
        dados = ler_json(arq)
        if dados.get("quem") == chave_quem or _bloqueado[0]:
            return dados["linhas"]
    try:
        if _bloqueado[0]:
            raise PortalBloqueou(ano)
        z = _baixar_zip(f"viagens/{ano}")
    except NaoPublicado:
        return []
    except PortalBloqueou:
        _avisar_bloqueio()
        return ler_json(arq)["linhas"] if arq.exists() else []
    nomes = {n.encode("latin1", "ignore") for _, n in quem} | {n.encode() for _, n in quem}
    cab, linhas = _linhas(z, "_Viagem.csv", lambda l: any(n in l.upper() for n in nomes))
    del z
    i = {normalizar_nome(c): k for k, c in enumerate(cab)}
    soma = {}
    for r in linhas:
        id_ = quem.get((r[i["CPF VIAJANTE"]], normalizar_nome(r[i["NOME"]])))
        if not id_ or normalizar_nome(r[i["SITUACAO"]]) != "REALIZADA":
            continue
        d, m, a = r[i["PERIODO - DATA DE INICIO"]].split("/")
        s = soma.setdefault((id_, int(a), int(m)), {"viagens": 0, "diarias": 0.0, "passagens": 0.0, "outros": 0.0, "devolucao": 0.0})
        s["viagens"] += 1
        s["diarias"] += numero_br(r[i["VALOR DIARIAS"]]) or 0.0
        s["passagens"] += numero_br(r[i["VALOR PASSAGENS"]]) or 0.0
        s["outros"] += numero_br(r[i["VALOR OUTROS GASTOS"]]) or 0.0
        s["devolucao"] += numero_br(r[i["VALOR DEVOLUCAO"]]) or 0.0
    saida = [{"id": k[0], "ano": k[1], "mes": k[2], **{c: round(v, 2) if isinstance(v, float) else v for c, v in s.items()}}
             for k, s in sorted(soma.items())]
    salvar_json(arq, {"quem": chave_quem, "linhas": saida})
    return saida


# ---------------------------------------------------------------- principal
def coletar():
    C.mkdir(parents=True, exist_ok=True)
    log("Executivo: presidente, vice e ministros (Portal da Transparência)")
    meses, pessoas = [], {}
    for ano, mes in meses_da_legislatura():
        d = _mes(ano, mes)
        if not d:
            log(f"  {mes:02d}/{ano}: ainda não publicado")
            continue
        meses.append(d)
        for id_, p in d["pessoas"].items():
            pessoas.setdefault(id_, {"id": id_, "nome": p["nome"], "cpf": p["cpf"], "meses": []})["meses"].append(ano * 100 + mes)
    if not meses:
        raise RuntimeError("Nenhum mês do Portal da Transparência disponível")
    ultimo = max(d["ano"] * 100 + d["mes"] for d in meses)
    log(f"  {len(meses)} meses, até {ultimo % 100:02d}/{ultimo // 100}; {len(pessoas)} pessoas")

    cargos, rem, jet = [], [], []
    for d in meses:
        for id_, p in d["pessoas"].items():
            for c in p["cargos"]:
                cargos.append({"id_portal": id_, "ano": d["ano"], "mes": d["mes"], **c})
            if p.get("remuneracao"):
                rem.append({"id_portal": id_, "ano": d["ano"], "mes": d["mes"], **p["remuneracao"]})
            for j in p.get("jetons", []):
                jet.append({"id_portal": id_, "ano": d["ano"], "mes": d["mes"], **j})

    quem = {(p["cpf"], normalizar_nome(p["nome"])): id_ for id_, p in pessoas.items()}
    via = []
    for ano in ANOS:
        via += _viagens(ano, quem)
    for p in pessoas.values():
        p["em_exercicio"] = ultimo in p["meses"]
        p["ultimo_mes_publicado"] = ultimo

    salvar_json(BRUTOS / "executivo_pessoas.json", sorted(pessoas.values(), key=lambda p: p["nome"]))
    pd.DataFrame(cargos).to_csv(BRUTOS / "executivo_cargos.csv", index=False)
    pd.DataFrame(rem).to_csv(BRUTOS / "executivo_remuneracao.csv", index=False)
    pd.DataFrame(jet, columns=["id_portal", "ano", "mes", "empresa", "valor"]).to_csv(BRUTOS / "executivo_jetons.csv", index=False)
    pd.DataFrame(via, columns=["id", "ano", "mes", "viagens", "diarias", "passagens", "outros", "devolucao"]) \
        .rename(columns={"id": "id_portal"}).to_csv(BRUTOS / "executivo_viagens.csv", index=False)
    log(f"Executivo: {len(rem)} meses de salário, {len(jet)} jetons, {len(via)} meses com viagens")
