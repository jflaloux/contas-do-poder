"""Funções auxiliares: acesso à internet com cache, números em formato brasileiro, nomes."""
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

import requests

from .config import USER_AGENT


class TempoEsgotado(Exception):
    """A coleta parou porque atingiu o tempo máximo; rode de novo para continuar."""


_prazo = None


def _ao_receber_sigterm(*_):
    raise TempoEsgotado()


def definir_prazo(segundos):
    """Tempo máximo da coleta. Com prazo, um SIGTERM (o `timeout` do shell) também vira TempoEsgotado, para os robôs
    gravarem o que já pegaram antes de sair."""
    global _prazo
    _prazo = time.time() + segundos if segundos else None
    if segundos:
        import signal
        try:
            signal.signal(signal.SIGTERM, _ao_receber_sigterm)
        except ValueError:  # fora da thread principal
            pass


def verificar_prazo():
    if _prazo and time.time() > _prazo:
        raise TempoEsgotado()


def restante():
    """Segundos até o prazo (None = sem prazo)."""
    return None if not _prazo else _prazo - time.time()


def dormir(segundos):
    """time.sleep que não passa do prazo: se a pausa acabaria depois dele, para já (TempoEsgotado)."""
    r = restante()
    if r is not None and segundos >= r:
        raise TempoEsgotado()
    time.sleep(segundos)


_local = threading.local()


# ---------------------------------------------------------------- robots.txt
class BloqueadoRobots(Exception):
    """O robots.txt do site não deixa robôs abrirem este endereço: não abrimos (regra do projeto, ver CLAUDE.md)."""


# APIs feitas para robôs, com regras próprias de uso (a da Wikimedia pede só um User-Agent identificado e ritmo
# moderado); o robots.txt desses sites é para quem varre as páginas, não para a API
APIS_LIBERADAS = ("https://commons.wikimedia.org/w/api.php", "https://www.wikidata.org/w/api.php")
# Exceções ao robots.txt (regra no CLAUDE.md): dados que a LAI manda publicar e abrir para acesso automatizado
# (Lei 12.527/2011, art. 8º, § 3º, III). Cada uma: (começo do endereço, motivo, segundos entre pedidos naquele site).
# A leitura é mínima (o cache faz cada página ser baixada no máximo uma vez por semana), o robô se identifica pelo
# User-Agent e para se o site bloquear. Em paralelo, há um pedido pela LAI dos mesmos dados (NOTAS-PRIVADAS).
EXCECOES_ROBOTS = [
    ("https://www.camara.leg.br/deputados/",
     "Câmara dos Deputados: salário, 13º, férias, diárias e pessoal de gabinete de cada deputado (remuneração de "
     "agente público, que a LAI manda publicar; o robots.txt proíbe /deputados/*/* desde 18/09/2026)", 0.25),
    ("https://dados.prefeitura.sp.gov.br/",
     "Prefeitura de São Paulo: folha de pagamento nos dados abertos (o robots.txt do portal tem Disallow: /)", 10),
    ("https://www.transparencia.pr.gov.br/pte/",
     "Paraná: remuneração do governador e do vice no Portal da Transparência (o robots.txt tem Disallow: /pte)", 2),
]
_robots, _robots_trava, _ultimo_pedido, _trava_host = {}, threading.Lock(), {}, {}


def excecao_robots(url):
    """(motivo, pausa) se o endereço está na lista de exceções ao robots.txt; senão None."""
    for comeco, motivo, pausa in EXCECOES_ROBOTS:
        if str(url).startswith(comeco):
            return motivo, pausa
    return None


def _esperar_vez(origem, intervalo):
    """Reserva o próximo horário livre para um pedido naquele site (no máximo um a cada `intervalo` segundos, mesmo com
    vários pedidos em paralelo) e espera até ele."""
    with _robots_trava:
        vez = max(time.time(), _ultimo_pedido.get(origem, 0) + intervalo)
        _ultimo_pedido[origem] = vez
    espera = vez - time.time()
    if espera > 0:
        dormir(espera)


def _regras_robots(texto):
    """O grupo de regras que vale para nós (o que cita "ContasDoPoder" ou, se nenhum, o "*"):
    {"regras": [(permite?, padrão)], "atraso": segundos ou None}."""
    grupos, atual, lendo_ua = [], None, False
    for linha in texto.splitlines():
        linha = linha.split("#", 1)[0].strip()
        if ":" not in linha:
            continue
        chave, valor = (x.strip() for x in linha.split(":", 1))
        chave = chave.lower()
        if chave == "user-agent":
            if not lendo_ua:
                atual = {"ua": [], "regras": [], "atraso": None}
                grupos.append(atual)
            atual["ua"].append(valor.lower())
            lendo_ua = True
            continue
        lendo_ua = False
        if atual is None:
            continue
        if chave in ("allow", "disallow") and valor:
            atual["regras"].append((chave == "allow", valor))
        elif chave == "crawl-delay":
            try:
                atual["atraso"] = float(valor.replace(",", "."))
            except ValueError:
                pass
    nosso = USER_AGENT.lower()
    for g in grupos:
        if any(u not in ("*", "") and u in nosso for u in g["ua"]):
            return g
    for g in grupos:
        if "*" in g["ua"]:
            return g
    return {"regras": [], "atraso": None}


def _casa(padrao, caminho):
    rx = "^" + re.escape(padrao).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    return re.match(rx, caminho) is not None


def permitido(url, regras):
    """A regra mais longa que casa com o caminho decide; empate: vale a que permite (RFC 9309)."""
    from urllib.parse import urlsplit
    u = urlsplit(url)
    caminho = (u.path or "/") + (f"?{u.query}" if u.query else "")
    melhor = None
    for permite, padrao in regras["regras"]:
        if _casa(padrao, caminho):
            chave = (len(padrao), permite)
            if melhor is None or chave > melhor:
                melhor = chave
    return melhor is None or melhor[1]


def _robots_de(origem, sessao):
    with _robots_trava:
        if origem in _robots:
            return _robots[origem]
    try:
        r = requests.Session.request(sessao, "GET", f"{origem}/robots.txt", timeout=30, allow_redirects=True)
        if r.status_code >= 500:
            regras = {"regras": [(False, "/")], "atraso": None}  # servidor com erro: não abre nada agora (RFC 9309)
        elif r.status_code >= 400 or "<html" in r.text[:600].lower():
            regras = {"regras": [], "atraso": None}  # sem robots.txt: tudo permitido
        else:
            regras = _regras_robots(r.text)
    except requests.RequestException:
        regras = {"regras": [(False, "/")], "atraso": None}
    with _robots_trava:
        _robots[origem] = regras
    return regras


class SessaoEducada(requests.Session):
    """requests.Session que lê o robots.txt de cada site antes do primeiro pedido: não abre o que ele proíbe
    (BloqueadoRobots), a não ser os endereços de EXCECOES_ROBOTS (com pausa entre os pedidos), e respeita o
    Crawl-delay (um pedido por vez naquele site, com a pausa pedida)."""

    def request(self, method, url, *args, **kwargs):
        from urllib.parse import urlsplit
        u = urlsplit(str(url))
        origem = f"{u.scheme}://{u.netloc}"
        if not str(url).startswith(APIS_LIBERADAS):
            regras = _robots_de(origem, self)
            exc = excecao_robots(url)
            if exc:  # exceção: lê mesmo com o robots.txt proibindo, com a pausa (e o Crawl-delay, se houver)
                _esperar_vez(origem, max(exc[1], regras["atraso"] or 0))
                return super().request(method, url, *args, **kwargs)
            if not permitido(str(url), regras):
                raise BloqueadoRobots(f"o robots.txt de {u.netloc} não permite robôs em {u.path}")
            if regras["atraso"]:
                with _robots_trava:
                    trava = _trava_host.setdefault(origem, threading.Lock())
                with trava:
                    espera = _ultimo_pedido.get(origem, 0) + regras["atraso"] - time.time()
                    if espera > 0:
                        dormir(espera)
                    _ultimo_pedido[origem] = time.time()
                    return super().request(method, url, *args, **kwargs)
        return super().request(method, url, *args, **kwargs)


def _sessao():
    if not hasattr(_local, "s"):
        s = SessaoEducada()
        s.headers["User-Agent"] = USER_AGENT
        _local.s = s
    return _local.s


def baixar(url, params=None, tentativas=4, timeout=90, **kw):
    """GET com novas tentativas em caso de erro temporário."""
    verificar_prazo()
    for i in range(tentativas):
        try:
            r = _sessao().get(url, params=params, timeout=timeout, **kw)
            if r.status_code == 404:
                r.raise_for_status()
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code} em {r.url}", response=r)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise
            if i == tentativas - 1:
                raise
        except requests.RequestException:
            if i == tentativas - 1:
                raise
        time.sleep(3 * (i + 1))


def cache_valido(caminho: Path, max_idade_dias=None):
    """Existe no cache e (se max_idade_dias for dado) não está velho demais."""
    if not caminho.exists():
        return False
    if max_idade_dias is None:
        return True
    return (time.time() - caminho.stat().st_mtime) < max_idade_dias * 86400


def salvar_json(caminho: Path, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(caminho)


def ler_json(caminho: Path):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def numero_br(texto):
    """'R$ 46.366,19' -> 46366.19 ; '' -> None."""
    if texto is None:
        return None
    t = str(texto).replace("R$", "").replace("\xa0", " ").strip()
    if t in ("", "-", "—"):
        return None
    t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def normalizar_nome(nome):
    """Maiúsculas, sem acentos e sem espaços duplos — para comparar nomes de fontes diferentes."""
    if not nome:
        return ""
    t = unicodedata.normalize("NFKD", str(nome))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, flush=True)


def recursos_ckan(pagina, pausa=10):
    """Arquivos de um conjunto de dados de um portal CKAN, pela página do conjunto (/dataset/<nome>): [{id, name, url}].
    O robots.txt desses portais não deixa robôs usarem a API (/api/) e pede 10 s entre os pedidos (Crawl-delay); a
    página do conjunto e os arquivos (/dataset/.../download/...) são permitidos."""
    from bs4 import BeautifulSoup
    verificar_prazo()
    r = _sessao().get(pagina, timeout=120)
    r.raise_for_status()
    dormir(pausa)
    saida, sopa = [], BeautifulSoup(r.text, "lxml")
    for li in sopa.select("li.resource-item"):
        titulo, baixar_ = li.select_one("a.heading"), li.select_one("a.resource-url-analytics")
        if titulo and baixar_ and baixar_.get("href"):
            nome = titulo.get("title") or titulo.get_text(" ", strip=True)
            saida.append({"id": li.get("data-id"), "name": re.sub(r"\s+", " ", nome).strip(), "url": baixar_["href"]})
    if not saida:  # tema diferente (Fortaleza): os links de download direto, com o nome do arquivo
        vistos = set()
        for a in sopa.select('a[href*="/resource/"][href*="/download/"]'):
            if a["href"] not in vistos:
                vistos.add(a["href"])
                m = re.search(r"/resource/([^/]+)/download/([^/?#]+)", a["href"])
                saida.append({"id": m.group(1) if m else None, "name": m.group(2) if m else a["href"], "url": a["href"]})
    if not saida:
        raise ValueError(f"{pagina}: nenhum arquivo na página do conjunto de dados (o leiaute mudou?)")
    return saida
