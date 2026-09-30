"""SAPL (Interlegis): o sistema legislativo usado por muitas câmaras. API JSON aberta em /api/.

Usado aqui só para: legislatura atual, mandatos (titulares e suplentes, com datas), e os dados de cada parlamentar
(nome parlamentar, nome completo, sexo, foto, partido atual). Os dados de cada parlamentar ficam guardados em
dados/municipios/<cidade>/sapl_parlamentares.csv: só se pergunta de novo por quem é novo, e com pausa entre os
pedidos (alguns SAPL pedem 60 s no robots.txt).
"""
import re
import time

import pandas as pd

from ..util import TempoEsgotado, baixar, log, verificar_prazo


def _get(base, caminho, params=None, pausa=2):
    verificar_prazo()
    r = baixar(f"{base}/api/{caminho}", params=params, timeout=90)
    time.sleep(pausa)
    return r.json()


def _todas(base, caminho, params, pausa):
    params = dict(params or {}, page_size=100)
    saida, pagina = [], 1
    while True:
        d = _get(base, caminho, dict(params, page=pagina), pausa)
        saida += d.get("results", [])
        if not d.get("pagination", {}).get("next_page"):
            return saida
        pagina += 1


def legislatura_atual(base, pausa=2):
    ls = _get(base, "parlamentares/legislatura/", {"o": "-numero", "page_size": 3}, pausa)["results"]
    return max(ls, key=lambda x: x["numero"])


def mandatos(base, legislatura_id, pausa=2):
    """DataFrame: parlamentar, inicio, fim, titular, votos."""
    ms = _todas(base, "parlamentares/mandato/", {"legislatura": legislatura_id}, pausa)
    nome = lambda s: re.sub(r"\s+\d+ª.*$", "", s or "").strip()  # "ALDENOR LIMA 19ª (2025 - 2028) (Atual)" -> "ALDENOR LIMA"
    return pd.DataFrame([{"parlamentar": m["parlamentar"], "nome": nome(m.get("__str__")), "inicio": m.get("data_inicio_mandato") or "",
                          "fim": m.get("data_fim_mandato") or "", "titular": bool(m.get("titular")), "votos": m.get("votos_recebidos")} for m in ms])


def parlamentares(base, ids, arquivo, pausa=2, maximo=None):
    """Dados de cada parlamentar (guardados em `arquivo`; só busca os que faltam, no máximo `maximo` por vez)."""
    antigos = pd.read_csv(arquivo, dtype=str).fillna("") if arquivo.exists() else pd.DataFrame(columns=["id"])
    ja = set(antigos["id"].astype(str))
    faltam = [i for i in ids if str(i) not in ja]
    if maximo is not None:
        faltam = faltam[:maximo]
    novos, partidos = [], {}
    try:
        for i in faltam:
            p = _get(base, f"parlamentares/parlamentar/{i}/", None, pausa)
            fil = _get(base, "parlamentares/filiacao/", {"parlamentar": i}, pausa).get("results", [])
            atual = [f for f in fil if not f.get("data_desfiliacao")] or fil
            sigla = ""
            if atual:
                pid = max(atual, key=lambda f: f.get("data") or "")["partido"]
                if pid not in partidos:
                    partidos[pid] = _get(base, f"parlamentares/partido/{pid}/", None, pausa).get("sigla", "")
                sigla = partidos[pid]
            novos.append({"id": str(i), "nome_parlamentar": (p.get("nome_parlamentar") or "").strip(), "nome_completo": (p.get("nome_completo") or "").strip(),
                          "sexo": p.get("sexo") or "", "fotografia": p.get("fotografia") or "", "partido": sigla})
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — o que já veio fica guardado
        log(f"  SAPL {base}: parou em {len(novos)} de {len(faltam)} parlamentares ({e})")
    tabela = pd.concat([antigos, pd.DataFrame(novos)], ignore_index=True) if novos else antigos
    if novos:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        tabela.to_csv(arquivo, index=False)
    return tabela
