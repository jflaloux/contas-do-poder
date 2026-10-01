"""Fotos das candidaturas no TSE: Portal de Dados Abertos do TSE, licença Creative Commons Atribuição.

O TSE publica, por eleição e UF, um zip com as fotos "divulgáveis" das candidaturas (FUF<SQ_CANDIDATO>_div.jpg):
https://dadosabertos.tse.jus.br/dataset/candidatos-2022 e .../candidatos-2024. O zip é grande (o de SP de 2024 tem
2,3 GB), por isso é lido por pedaços (HTTP Range): o índice do zip e só as fotos que faltam no site.
A foto só é usada quando o nome civil da pessoa é exatamente o de um único candidato do mesmo cargo e lugar.
"""
import csv
import io
import re
import zipfile

from .config import CACHE
from .util import TempoEsgotado, _sessao, log, normalizar_nome

URL = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes{ano}/fotos/foto_cand{ano}_{uf}_div.zip"
PAGINA = "https://dadosabertos.tse.jus.br/dataset/candidatos-{ano}"
LICENCA = "http://www.opendefinition.org/licenses/cc-by"
CONSULTA = {2022: CACHE / "assembleias" / "consulta_cand_2022.zip", 2024: CACHE / "municipios" / "consulta_cand_2024.zip"}


class ZipRemoto(io.RawIOBase):
    """Arquivo remoto lido por blocos (HTTP Range), com o último bloco guardado. `bloco` grande para o índice do zip
    (milhares de entradas seguidas) e pequeno para as fotos."""

    def __init__(self, url, bloco=1 << 20):
        self.s, self.url, self.pos, self.bloco, self.cache = _sessao(), url, 0, bloco, (0, b"")
        r = self.s.get(url, headers={"Range": "bytes=0-0"}, timeout=60)
        r.raise_for_status()
        self.tam = int(r.headers["content-range"].split("/")[1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.tam + off)
        return self.pos

    def readinto(self, buf):
        if self.pos >= self.tam or not len(buf):
            return 0
        ini, dados = self.cache
        if not (ini <= self.pos < ini + len(dados)):
            fim = min(self.pos + max(len(buf), self.bloco), self.tam) - 1
            r = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{fim}"}, timeout=180)
            r.raise_for_status()
            self.cache = ini, dados = self.pos, r.content
        b = dados[self.pos - ini:self.pos - ini + len(buf)]
        buf[:len(b)] = b
        self.pos += len(b)
        return len(b)


def candidatos(ano, uf, cargos, municipio=None, chave="NM_CANDIDATO"):
    """{nome normalizado: [SQ, ...]} dos candidatos de `ano` na UF, nos cargos (CD_CARGO) e, se dado, no município.
    chave: NM_CANDIDATO (nome civil) ou NM_URNA_CANDIDATO (nome de urna)."""
    saida = {}
    arq = CONSULTA[ano]
    if not arq.exists():
        return saida
    alvo = normalizar_nome(municipio) if municipio else None
    with zipfile.ZipFile(arq) as z, z.open(f"consulta_cand_{ano}_{uf}.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            if l["CD_CARGO"] not in cargos or (alvo and normalizar_nome(l["NM_UE"]) != alvo):
                continue
            lista = saida.setdefault(normalizar_nome(l[chave]), [])
            if l["SQ_CANDIDATO"] not in lista:
                lista.append(l["SQ_CANDIDATO"])
    return saida


def baixar(ano, uf, alvos):
    """alvos: {id da pessoa no site: SQ}. Salva site/fotos/<id>.webp e o crédito; devolve quantas fotos novas."""
    from . import fotos as F
    alvos = {pid: sq for pid, sq in alvos.items() if not (F.PASTA / f"{pid}.webp").exists()}
    if not alvos:
        return 0
    dados = F.ler_json(F.CREDITOS) if F.CREDITOS.exists() else {}
    creditos = dados.setdefault("fotos", {})
    novas = 0
    try:
        remoto = ZipRemoto(URL.format(ano=ano, uf=uf))
        z = zipfile.ZipFile(remoto)
        nomes = {re.sub(r"\D", "", n): n for n in z.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png"))}
        remoto.bloco = 1 << 16
        for pid, sq in alvos.items():
            arquivo = nomes.get(str(sq))
            if not arquivo:
                continue
            (F.PASTA / f"{pid}.webp").write_bytes(F._ajustar(z.read(arquivo)))
            creditos[pid] = {"arquivo": arquivo, "autor": f"Tribunal Superior Eleitoral (foto da candidatura de {ano})",
                             "licenca": "CC BY", "url_licenca": LICENCA, "pagina": PAGINA.format(ano=ano)}
            novas += 1
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — foto é opcional
        log(f"  fotos do TSE ({ano}, {uf}): {e}")
    finally:
        F.salvar_json(F.CREDITOS, dados)
    return novas


def por_nome(ano, uf, pessoas, cargos, municipio=None):
    """pessoas: [{id, nc, n}] sem foto. Casa pelo nome civil exato (um único SQ) ou, se não houver, pelo nome de urna
    exato (também um único SQ) e baixa as fotos."""
    civis = candidatos(ano, uf, cargos, municipio)
    urnas = None
    alvos = {}
    for p in pessoas:
        sqs = civis.get(normalizar_nome(p.get("nc") or ""), [])
        if not sqs:
            urnas = urnas if urnas is not None else candidatos(ano, uf, cargos, municipio, chave="NM_URNA_CANDIDATO")
            sqs = urnas.get(normalizar_nome(p.get("n") or ""), [])
        if len(sqs) == 1:
            alvos[p["id"]] = sqs[0]
    return baixar(ano, uf, alvos)
