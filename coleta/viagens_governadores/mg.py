"""Minas Gerais: viagens do governador e do vice no sistema de diárias e passagens (SCDP), trecho por trecho, pelos
dados abertos do Estado (conjunto "viagens", CKAN: https://dados.mg.gov.br/dataset/viagens). Os arquivos são achados
pela página do conjunto (o robots.txt proíbe /api/ e pede 10 s entre os pedidos):
- dm_favorecido_scdp.csv.gz: quem viajou (o id pelo nome; o CPF mascarado do arquivo não é lido);
- ft_diarias_scdp.csv.gz (~42 MB): os trechos (documento de viagem, datas, meio de transporte, diárias e passagem);
- dm_cidade.csv.gz: o nome do destino.
Uma viagem é um documento de viagem; o valor é a soma dos trechos (diárias e passagem)."""
import gzip
import time

import pandas as pd

from ..util import _sessao, recursos_ckan, verificar_prazo
from . import comum

UF = "MG"
FONTE = "https://dados.mg.gov.br/dataset/viagens"
NOTA = ("Diárias e passagens do governador e do vice no sistema de diárias e passagens do Estado (dados abertos de Minas "
        "Gerais), viagem por viagem, somando os trechos de cada uma; o mês é o do início da viagem. Trechos aéreos sem "
        "valor de passagem são, em geral, no avião oficial, cujo custo não é publicado.")
ARQUIVOS = ("dm_favorecido_scdp.csv.gz", "ft_diarias_scdp.csv.gz", "dm_cidade.csv.gz")
AEREO = "1"  # dm_meio_transporte: 1 = AEREO, 7 = VEICULO OFICIAL


def _baixar():
    pasta = comum.C / "mg"
    pasta.mkdir(parents=True, exist_ok=True)
    faltam = [n for n in ARQUIVOS if not (pasta / n).exists() or time.time() - (pasta / n).stat().st_mtime > 6 * 86400]
    if not faltam:
        return pasta
    urls = {r["url"].rsplit("/", 1)[-1]: r["url"] for r in recursos_ckan(FONTE)}
    for nome in faltam:
        verificar_prazo()
        tmp = pasta / (nome + ".parcial")
        with _sessao().get(urls[nome], timeout=900, stream=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for b in r.iter_content(1 << 20):
                    f.write(b)
        tmp.replace(pasta / nome)
    return pasta


def coletar(nomes):
    pasta = _baixar()
    with gzip.open(pasta / "dm_favorecido_scdp.csv.gz", "rt", encoding="utf-8-sig", errors="replace") as f:
        fav = pd.read_csv(f, sep=";", dtype=str, usecols=["id_favorecido", "nome_anonimizado"])
    # alguns registros trazem o CPF escrito depois do nome ("NOME - 000.000.000-00"): só a parte do nome conta
    fav["nome"] = fav.nome_anonimizado.fillna("").str.split(" - ").str[0].map(comum.normalizar_nome)
    ids = dict(zip(fav[fav.nome.isin(nomes)].id_favorecido, fav[fav.nome.isin(nomes)].nome))
    if not ids:  # o arquivo de favorecidos veio sem os nomes (fora do ar, leiaute novo): falha, e fica o que estava gravado
        raise RuntimeError("nenhum nome do governador ou do vice no arquivo de favorecidos (dm_favorecido_scdp)")
    with gzip.open(pasta / "dm_cidade.csv.gz", "rt", encoding="utf-8-sig", errors="replace") as f:
        cid = pd.read_csv(f, sep=";", dtype=str)
    col_nome = next((c for c in cid.columns if c.lower() in ("nome", "nome_cidade", "cidade")), cid.columns[1])
    cidades = dict(zip(cid[cid.columns[0]], cid[col_nome]))
    partes = []
    with gzip.open(pasta / "ft_diarias_scdp.csv.gz", "rt", encoding="utf-8-sig", errors="replace") as f:
        for ch in pd.read_csv(f, sep=";", dtype=str, chunksize=500_000,
                              usecols=["id_favorecido", "id_documento_viagem", "id_cidade_destino", "id_meio_transporte",
                                       "ordem_trecho", "dt_inicio_trecho", "dt_fim_trecho", "vr_diaria", "vr_passagem"]):
            verificar_prazo()
            partes.append(ch[ch.id_favorecido.isin(ids) & (ch.dt_inicio_trecho >= f"{comum.INICIO // 100}-{comum.INICIO % 100:02d}-01")])
    t = pd.concat(partes) if partes else pd.DataFrame()
    linhas = []
    for doc, g in t.groupby("id_documento_viagem"):
        g = g.assign(o=pd.to_numeric(g.ordem_trecho, errors="coerce")).sort_values(["dt_inicio_trecho", "o"])
        aereo_sem_valor = ((g.id_meio_transporte == AEREO) & (pd.to_numeric(g.vr_passagem, errors="coerce").fillna(0) == 0)).any()
        destinos = [cidades.get(c, "") for c in g.id_cidade_destino]
        linhas.append({"id": f"mg-{doc}", "inicio": g.dt_inicio_trecho.min(), "fim": g.dt_fim_trecho.max(),
                       "nome": ids[g.id_favorecido.iloc[0]], "cargo": "", "destino": "; ".join(dict.fromkeys(d for d in destinos if d)),
                       "diarias": pd.to_numeric(g.vr_diaria, errors="coerce").fillna(0).sum(),
                       "passagens": pd.to_numeric(g.vr_passagem, errors="coerce").fillna(0).sum(),
                       "obs": "trecho aéreo sem valor de passagem" if aereo_sem_valor else "", "fonte": FONTE})
    return comum.gravar(UF, linhas)
