"""Assembleia Legislativa do Rio Grande do Norte (ALRN): deputado estadual por deputado estadual.

Fontes:
- Deputados: a lista de parlamentares do sistema legislativo da ALRN, a que a página "Transparência Legislativa"
  (https://transparencialegislativa.al.rn.leg.br/) usa: nome parlamentar, nome civil, vigência e as filiações
  partidárias com as datas (o partido de hoje é a filiação sem fim). A resposta traz também o CPF e a data de nascimento
  de cada um: só o nome, a vigência e o partido são lidos, nada mais é guardado. A página de cada deputado é a da lista
  https://www.al.rn.leg.br/deputados.
- Subsídio: Lei 11.315/2022 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Verba e folha: o Portal da Transparência da ALRN (https://transparencia.al.rn.leg.br/verbas, nota a nota, e
  /servidores-pagamentos) lê tudo de uma API que exige autenticação, e ela não é usada (regra do projeto). A verba e a
  folha de cada deputado ficam de fora, e o salário é o da lei.
Quem está no cargo: a lista atual da ALRN (24 deputados), desde jan/2025 ou desde o início da vigência. A lista não traz
quem saiu nem as licenças; os 24 de hoje são os mesmos desde o começo de 2025 (conferido com os eleitos de 2022: George
Soares deixou a vaga antes de 2025 e Vivaldo Costa, suplente, está no lugar).
"""
import re
import time

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "RN"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
LISTA = "https://api-transparencialegislativa.al.rn.leg.br/elegis-api-transp-legislativa/parlamentar"
SITE = "https://www.al.rn.leg.br/deputados"
PASTA = DADOS / "assembleias" / "rn"
CFG = {
    "cod": COD, "n": "Rio Grande do Norte", "uf": UF, "casa": "Assembleia Legislativa do Rio Grande do Norte", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 11.315/2022), proporcional aos dias no cargo. A folha da ALRN só sai por uma "
                     "consulta que pede uma chave de acesso, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba de gabinete",
    "verba_notas": ["A ALRN publica a verba de cada deputado nota a nota no Portal da Transparência, mas a página lê os dados "
                    "de um serviço que pede uma chave de acesso. A verba não entra."],
    "conferir_gastos": False,
    "pagina": SITE,
    "notas": ["Quem está no cargo: a lista atual de deputados da ALRN (sem as licenças e sem quem saiu), desde janeiro de 2025.",
              "Partido: o da filiação em vigor no sistema legislativo da ALRN."],
    "fontes": {"deputados": SITE, "lista": "https://transparencialegislativa.al.rn.leg.br/",
               "subsidio": "https://www.al.rn.leg.br/storage/legislacao/2023/es2r5o18f7ve1pnah0ckgc15wtj8q7.pdf",
               "verba": "https://transparencia.al.rn.leg.br/verbas"},
}


def _pedir(url, **kw):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().get(url, timeout=90, **kw)
            r.raise_for_status()
            dormir(2)
            return r
        except TempoEsgotado:
            raise
        except Exception:  # noqa: BLE001 — a API da lista às vezes responde 502: espera e tenta de novo
            if tentativa == 3:
                raise
            dormir(20)


def _data(t):
    return str(t or "")[:10]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = PASTA / "deputados.csv"
    if arq.exists() and time.time() - arq.stat().st_mtime < 86400:
        return
    try:
        dados = _pedir(LISTA).json()["dados"]
        paginas = _pedir(SITE).text
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"  ALRN: a lista de deputados não abriu ({type(e).__name__}); fica o que já estava gravado")
        return
    links = {re.sub(r"[^a-z]", "", s): f"https://www.al.rn.leg.br/deputado/{i}/{s}" for i, s in re.findall(r"/deputado/(\d+)/([a-z0-9-]+)", paginas)}
    linhas = []
    for x in dados:  # só o nome, a vigência e o partido (a resposta traz também o CPF e a data de nascimento: não são lidos)
        nome = re.sub(r"^\s*DEPUTAD[OA]\s+", "", x.get("nomeParlamentar") or "", flags=re.I).strip()
        filiacoes = sorted(x.get("filiacoes") or [], key=lambda f: _data((f.get("vigencia") or {}).get("inicio")))
        atual = [f for f in filiacoes if not (f.get("vigencia") or {}).get("fim")]
        partido = ((atual or filiacoes or [{}])[-1].get("partido") or {}).get("nome") or ""
        vig = x.get("vigencia") or {}
        linhas.append({"id": x["id"], "nome": nome, "nome_civil": ((x.get("pessoa") or {}).get("nome") or "").strip(),
                       "genero": "F" if re.match(r"^\s*DEPUTADA\b", x.get("nomeParlamentar") or "", re.I) else "M",
                       "inicio": _data(vig.get("inicio")), "fim": _data(vig.get("fim")), "partido": partido,
                       "pagina": links.get(re.sub(r"[^a-z]", "", normalizar_nome(nome).lower()), "")})
    if len(linhas) < 20:
        log(f"  ALRN: a lista veio com {len(linhas)} deputados; fica o que já estava gravado")
        return
    gravar_csv(pd.DataFrame(linhas).sort_values("nome"), arq)
    log(f"  ALRN: {len(linhas)} deputados na lista")


def montar(tipos):
    arq = PASTA / "deputados.csv"
    if not arq.exists():
        return None
    dep = pd.read_csv(arq, dtype=str).fillna("")
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    ultimo = vc.ultimo_mes_fechado()
    hoje = time.strftime("%Y-%m-%d")
    ver, mandatos = [], []
    for r in dep.itertuples():
        t = por_civil.get(normalizar_nome(r.nome_civil)) or comum.achar(r.nome, tse) or {}
        codigo = comum.codigo_de(r.nome_civil or r.nome, t)
        nome = re.sub(r"\b(Pt|Pl|Pv|Mdb)\b", lambda m: m.group(1).upper(), vc.titulo(r.nome))  # "Francisco do PT"
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(r.nome_civil or t.get("nome") or r.nome),
                    "partido": r.partido, "genero": r.genero or t.get("genero") or ("F" if feminino(r.nome_civil) else "M"),
                    "eleito": t.get("eleito", ""), "pagina": r.pagina or CFG["pagina"]})
        inicio = max(r.inicio or "2025-01-01", f"{INICIO // 100}-{INICIO % 100:02d}-01")
        fim = r.fim if r.fim and r.fim < hoje else ""
        mandatos.append({"codigo": codigo, "inicio": inicio, "fim": fim})
    cfg = dict(CFG, ultimo_mes=ultimo)
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos))
