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


# ---------------------------------------------------------------- robots.txt e pausas
# O robots.txt é uma convenção, não lei (decisão de 08/10/2026, ver CLAUDE.md): não impede nenhum pedido. A sessão lê o
# robots.txt de cada site só para saber o Crawl-delay e se o site prefere que robôs não entrem naquele endereço (aí, uma
# pausa entre os pedidos). O que continua valendo para todo robô: só dados públicos, leitura mínima (o cache faz cada
# página ser baixada no máximo uma vez por semana), o User-Agent "ContasDoPoder", pausas entre os pedidos, e parar se o
# órgão pedir ou bloquear (SITES_PARADOS aqui, ou BLOQUEADO_ROBOTS no módulo do robô). CAPTCHA, WAF, login e consulta
# que pede CPF continuam sendo barreiras que não se contornam.
class SiteParado(Exception):
    """O órgão pediu para o robô parar (ou bloqueou o robô): nenhum pedido sai para esse site (SITES_PARADOS)."""


# Sites que pediram para o robô parar, ou que bloquearam o robô: (começo do endereço, desde quando e por quê). Nenhum
# pedido sai para eles (SiteParado), e quem chama segue com o que já estava gravado.
SITES_PARADOS = []

# APIs feitas para robôs, com regras próprias de uso (a da Wikimedia pede só um User-Agent identificado e ritmo
# moderado): o robots.txt desses sites nem é lido
APIS_LIBERADAS = ("https://commons.wikimedia.org/w/api.php", "https://www.wikidata.org/w/api.php")
# Pausa mínima entre os pedidos em alguns endereços (começo do endereço, segundos), além do Crawl-delay. São os sites
# que, de 30/09 a 08/10/2026, eram exceções ao robots.txt (dados que a LAI manda abrir, lidos mesmo com o robots.txt
# proibindo), com a pausa que já tinham.
PAUSAS = [
    ("https://www.camara.leg.br/deputados/", 0.25),   # robots.txt proíbe /deputados/*/* desde 18/09/2026
    ("https://dados.prefeitura.sp.gov.br/", 10),      # Disallow: /
    ("https://www.transparencia.pr.gov.br/pte/", 2),  # Disallow: /pte
    ("https://dadosabertos.almg.gov.br/ws/", 1),      # Disallow: / (o serviço é feito para acesso automatizado)
    ("https://docigp.alerj.rj.gov.br/", 0.5),         # Disallow: /
]
# Endereço que o robots.txt pede que robôs não abram, sem pausa própria nem Crawl-delay: esta pausa entre os pedidos
PAUSA_SE_O_ROBOTS_PROIBE = 1.0
_robots, _robots_trava, _ultimo_pedido, _trava_host = {}, threading.Lock(), {}, {}


# ---------------------------------------------------------------- disjuntor por site
# Um site que para de responder (por queda ou porque bloqueou o nosso endereço) não pode prender a rodada: sem isto, cada
# um dos milhares de pedidos esperava 90 s, 4 vezes, e a rodada do GitHub de 06/10/2026 passou das 2h30 do limite. Depois
# de DISJUNTOR_FALHAS falhas de conexão seguidas (sem nenhuma resposta, nem de erro) num site, os pedidos seguintes a ele
# falham de imediato (HostIndisponivel) durante DISJUNTOR_PAUSA segundos; passado o tempo, um pedido tenta de novo e,
# se falhar, o site volta a ficar fechado. Não é tentativa de passar por bloqueio: ao contrário, é parar de insistir.
# A falha chega a quem chamou como erro de conexão comum (a fonte fica "com falha" e continua na próxima rodada).
DISJUNTOR_FALHAS = 6
DISJUNTOR_PAUSA = 900
CONEXAO_TIMEOUT = 20  # segundos para abrir a conexão (a leitura da resposta tem o prazo de cada chamada)
_disjuntor, _disjuntor_trava = {}, threading.Lock()


class HostIndisponivel(requests.exceptions.ConnectionError):
    """O site não respondeu a vários pedidos seguidos: os próximos nem são tentados por um tempo."""


def _disjuntor_antes(origem):
    with _disjuntor_trava:
        d = _disjuntor.get(origem)
        if d and d["aberto_ate"] > time.time():
            raise HostIndisponivel(f"{origem} não responde (várias falhas seguidas); sem novos pedidos por "
                                   f"{int((d['aberto_ate'] - time.time()) / 60) + 1} min")


def _disjuntor_depois(origem, respondeu):
    with _disjuntor_trava:
        d = _disjuntor.setdefault(origem, {"falhas": 0, "aberto_ate": 0})
        if respondeu:
            d["falhas"], d["aberto_ate"] = 0, 0
            return
        d["falhas"] += 1
        if d["falhas"] >= DISJUNTOR_FALHAS and d["aberto_ate"] <= time.time():
            d["aberto_ate"] = time.time() + DISJUNTOR_PAUSA
            log(f"  {origem}: {d['falhas']} falhas de conexão seguidas; sem novos pedidos por {DISJUNTOR_PAUSA // 60} min")


def _pedir(origem, funcao, *args, **kwargs):
    """Faz o pedido (funcao) com o disjuntor do site e o prazo para abrir a conexão."""
    _disjuntor_antes(origem)
    t = kwargs.get("timeout")
    if t is None:
        kwargs["timeout"] = (CONEXAO_TIMEOUT, 120)
    elif isinstance(t, (int, float)):
        kwargs["timeout"] = (min(CONEXAO_TIMEOUT, t), t)
    try:
        r = funcao(*args, **kwargs)
    except requests.exceptions.SSLError:
        _disjuntor_depois(origem, True)  # o servidor respondeu (a falha é de certificado): não é site fora do ar
        raise
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
        # em redirecionamento, a falha é do endereço do salto que falhou (e.request), não do endereço pedido
        falhou = origem
        pedido = getattr(e, "request", None)
        if pedido is not None and getattr(pedido, "url", None):
            from urllib.parse import urlsplit
            u = urlsplit(pedido.url)
            falhou = f"{u.scheme}://{u.netloc}"
        _disjuntor_depois(falhou, False)
        raise
    except requests.RequestException:
        _disjuntor_depois(origem, True)  # o site respondeu (ou abriu a conexão), mas a resposta falhou
        raise
    _disjuntor_depois(origem, True)
    return r


def pausa_do_endereco(url):
    """Segundos de pausa própria daquele endereço (PAUSAS), ou None."""
    for comeco, pausa in PAUSAS:
        if str(url).startswith(comeco):
            return pausa
    return None


def site_parado(url):
    """(começo, motivo) se o site pediu para o robô parar (SITES_PARADOS); senão None."""
    for comeco, motivo in SITES_PARADOS:
        if str(url).startswith(comeco):
            return comeco, motivo
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


ROBOTS_INACESSIVEL_SEGUNDOS = 300  # um robots.txt que não abriu vale por 5 min (nada é aberto nesse site); depois tenta de novo
_robots_falhou = {}


def _robots_de(origem, sessao):
    with _robots_trava:
        if origem in _robots:
            return _robots[origem]
        falhou = _robots_falhou.get(origem)
        if falhou and time.time() - falhou["quando"] < ROBOTS_INACESSIVEL_SEGUNDOS:
            return falhou["regras"]
    try:
        r = _pedir(origem, requests.Session.request, sessao, "GET", f"{origem}/robots.txt", timeout=30, allow_redirects=True)
        if r.status_code >= 500:
            # servidor com erro: vale como se o site pedisse que robôs não entrem (RFC 9309), ou seja, com pausa
            regras = {"regras": [(False, "/")], "atraso": None}
        elif r.status_code >= 400 or "<html" in r.text[:600].lower():
            regras = {"regras": [], "atraso": None}  # sem robots.txt: tudo permitido
        else:
            regras = _regras_robots(r.text)
    except HostIndisponivel:
        raise
    except requests.RequestException:
        # robots.txt que não abriu (site fora do ar, ou bloqueio): nada é aberto nesse site (o site não responde, e o
        # Crawl-delay não é conhecido) por ROBOTS_INACESSIVEL_SEGUNDOS, e depois se tenta ler de novo; quem pede recebe
        # erro de conexão
        regras = {"regras": [(False, "/")], "atraso": None, "inacessivel": True}
        with _robots_trava:
            _robots_falhou[origem] = {"quando": time.time(), "regras": regras}
        return regras
    with _robots_trava:
        _robots[origem] = regras
    return regras


class SessaoEducada(requests.Session):
    """requests.Session que lê o robots.txt de cada site antes do primeiro pedido, só para as pausas: o Crawl-delay (um
    pedido por vez naquele site, com a pausa pedida), a pausa própria do endereço (PAUSAS) ou, onde o robots.txt pede
    que robôs não entrem, PAUSA_SE_O_ROBOTS_PROIBE. O robots.txt não impede nenhum pedido (regra no CLAUDE.md); o que
    impede é o site ter pedido para o robô parar (SITES_PARADOS -> SiteParado)."""

    def request(self, method, url, *args, **kwargs):
        from urllib.parse import urlsplit
        u = urlsplit(str(url))
        origem = f"{u.scheme}://{u.netloc}"
        parado = site_parado(url)
        if parado:
            raise SiteParado(f"{u.netloc}: o robô não abre este site ({parado[1]})")
        if str(url).startswith(APIS_LIBERADAS):
            return _pedir(origem, super().request, method, url, *args, **kwargs)
        regras = _robots_de(origem, self)
        if regras.get("inacessivel"):  # o site não respondeu nem ao robots.txt: sem pedidos por um tempo
            raise requests.exceptions.ConnectionError(f"o robots.txt de {u.netloc} não abriu (site fora do ar ou bloqueado)")
        pausa = pausa_do_endereco(url)
        if pausa is not None:  # pausa própria do endereço (e o Crawl-delay, se for maior)
            _esperar_vez(origem, max(pausa, regras["atraso"] or 0))
            return _pedir(origem, super().request, method, url, *args, **kwargs)
        if regras["atraso"]:
            with _robots_trava:
                trava = _trava_host.setdefault(origem, threading.Lock())
            with trava:
                espera = _ultimo_pedido.get(origem, 0) + regras["atraso"] - time.time()
                if espera > 0:
                    dormir(espera)
                _ultimo_pedido[origem] = time.time()
                return _pedir(origem, super().request, method, url, *args, **kwargs)
        if not permitido(str(url), regras):  # o site prefere que robôs não entrem aqui: lemos, com pausa
            _esperar_vez(origem, PAUSA_SE_O_ROBOTS_PROIBE)
        return _pedir(origem, super().request, method, url, *args, **kwargs)


def _sessao():
    if not hasattr(_local, "s"):
        s = SessaoEducada()
        s.headers["User-Agent"] = USER_AGENT
        _local.s = s
    return _local.s


def ca_com_intermediario(host, nome):
    """Arquivo de certificados (as raízes do certifi mais um certificado intermediário) para um servidor que não manda o
    intermediário (cadeia incompleta). O intermediário vem do endereço "CA Issuers" (AIA) do próprio certificado do
    servidor e só entra se for o emissor desse certificado, for assinado por uma das raízes do certifi, estiver na
    validade e for de uma autoridade certificadora. A verificação do certificado nunca é desligada (regra do CLAUDE.md):
    o certificado do servidor é lido só para achar o endereço do intermediário, e todos os pedidos verificam a cadeia com
    este arquivo. Fica em dados/cache/certificados/<nome>.pem, refeito a cada 30 dias.
    Uso: sessao.verify = ca_com_intermediario("tomeconta.tce.pe.gov.br", "tcepe")."""
    import ssl
    import warnings
    from datetime import datetime, timezone

    import certifi
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import AuthorityInformationAccessOID

    from .config import CACHE
    destino = CACHE / "certificados" / f"{nome}.pem"
    raizes_pem = Path(certifi.where()).read_bytes()
    if cache_valido(destino, 30) and destino.read_bytes().startswith(raizes_pem[:4096]):
        return str(destino)
    folha = x509.load_pem_x509_certificate(ssl.get_server_certificate((host, 443), timeout=30).encode())
    aia = folha.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
    url = next(d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS)
    der = _sessao().get(url, timeout=60).content  # pela sessão do projeto (pausas, User-Agent), como todo pedido
    inter = x509.load_der_x509_certificate(der) if not der.lstrip().startswith(b"-----") else x509.load_pem_x509_certificate(der)
    assinado = False
    for bloco in re.findall(rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", raizes_pem, re.S):
        try:
            with warnings.catch_warnings():  # uma ou outra raiz antiga do certifi tem número de série fora da norma
                warnings.simplefilter("ignore")
                raiz = x509.load_pem_x509_certificate(bloco)
            if raiz.subject != inter.issuer:
                continue
            inter.verify_directly_issued_by(raiz)
            assinado = True
            break
        except Exception:  # noqa: BLE001 — outra raiz com o mesmo nome, ou raiz que não se lê
            continue
    agora = datetime.now(timezone.utc)
    ca = inter.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    if not (assinado and ca and inter.subject == folha.issuer
            and inter.not_valid_before_utc <= agora <= inter.not_valid_after_utc):
        raise RuntimeError(f"o certificado intermediário de {host} ({url}) não confere com as raízes do certifi")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(raizes_pem.rstrip(b"\n") + b"\n\n# intermediario de " + host.encode() + b": " + url.encode() + b"\n"
                    + inter.public_bytes(Encoding.PEM))
    tmp.replace(destino)
    return str(destino)


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
        except HostIndisponivel:
            raise  # o site não responde: não adianta tentar de novo agora
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
    """Cache e arquivos de controle (troca de uma vez, sem comparar). Arquivo de dados: gravar_json."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(caminho)


# ---------------------------------------------------------------- gravação segura
# Todo arquivo de dados (dados/ e site/dados/; cache e controle ficam de fora) é gravado por gravar_csv, gravar_json,
# gravar_texto ou gravar_com. O novo vai para um arquivo temporário ao lado, é comparado com o anterior e só troca o
# anterior se não perder cobertura grande. Recusa (fica o anterior, a falha vai para a situação, a rodada segue):
#   - o novo vem vazio e o anterior tinha linhas;
#   - um mês (CSV) ou um grupo (JSON: cidade, estado, órgão) que existia some;
#   - um mês ou grupo perde mais de 20% das entidades (pessoas, gabinetes, municípios), com pelo menos 3 a menos;
#   - um mês ou grupo perde mais da metade das linhas, com pelo menos 10 a menos.
# Redução legítima: quem chama passa motivo="..." (nunca por padrão); a redução vai para o log com o motivo.
# Arquivo "retrato" (só o último mês, como cargos_gabinetes.csv): com um mês só antes e depois, compara sem o mês.
PERDA_ENTIDADES, MINIMO_ENTIDADES = 0.2, 3
PERDA_LINHAS, MINIMO_LINHAS = 0.5, 10
# entidade de cada linha: a primeira destas colunas que existe no arquivo anterior e no novo (sem nenhuma: as linhas)
COLUNAS_ENTIDADE = ("cod_ibge", "id_deputado", "id_senador", "codigo_senador", "id_politico", "id_portal", "id_cota",
                    "id_funcional", "vereador_id", "setor_id", "id", "matricula", "gabinete", "deputado", "vereador",
                    "parlamentar", "nome", "token", "lotacao", "codigo", "chave", "carteira", "referencia", "orcamento",
                    "processo", "docid")
COLUNAS_MES = ("ano_mes", "aaaamm", "competencia", "mes_referencia")  # além de "ano" + "mes" e, por último, "data"
GRUPOS_JSON = ("cid", "org", "uf", "k")  # nos JSON do site, a lista "p" se divide por cidade, órgão, estado ou tipo
_fonte_atual = None  # a fonte em coleta (onde.registrar põe e tira), para a falha ir para a fonte certa
_recusas = []  # recusas desta execução: [{"arquivo", "fonte", "perdas"}]
_eventos = None  # dados/processados/recusas_<lugar>.json, lido uma vez


class _Ilegivel(Exception):
    pass


def _rel(caminho):
    from .config import RAIZ
    try:
        return str(Path(caminho).resolve().relative_to(RAIZ))
    except ValueError:
        return str(caminho)


def _aaaamm(serie):
    """'2026-08', '202608', '08/2026', '15/08/2026', '2026-08-15' -> 202608 (float; NaN quando não é mês)."""
    import pandas as pd
    s = serie.astype(str).str.strip()
    out = pd.Series(float("nan"), index=s.index)
    for rx, a, m in ((r"^(\d{4})-?(\d{2})(?:\D|$|\d{2}$)", 0, 1), (r"^(?:\d{1,2}/)?(\d{1,2})/(\d{4})", 1, 0)):
        x = s.str.extract(rx)
        if x.shape[1] < 2:
            continue
        ano, mes = pd.to_numeric(x[a], errors="coerce"), pd.to_numeric(x[m], errors="coerce")
        ok = out.isna() & ano.between(1990, 2100) & mes.between(1, 12)
        out[ok] = ano[ok] * 100 + mes[ok]
    return out


def _ler_tabela(caminho, sep=None, nrows=None):
    """O CSV como texto (dtype=str). Arquivo que não se lê (corrompido, gzip quebrado, codificação) -> _Ilegivel."""
    import gzip
    import zlib

    import pandas as pd
    try:
        if sep is None:
            abrir = gzip.open if str(caminho).endswith(".gz") else open
            with abrir(caminho, "rt", encoding="utf-8", errors="replace") as f:
                cab = f.readline()
            sep = ";" if cab.count(";") > cab.count(",") else ","
        return pd.read_csv(caminho, sep=sep, dtype=str, keep_default_na=False, low_memory=False, encoding="utf-8",
                           encoding_errors="replace", nrows=nrows)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (pd.errors.ParserError, UnicodeError, OSError, EOFError, zlib.error) as e:
        raise _Ilegivel(f"{type(e).__name__}: {e}") from e


def _colunas_mes(df, comuns, mes=None):
    """O mês (AAAAMM) de cada linha, pela coluna dada ou pelas de costume ("ano" + "mes", "ano_mes", "aaaamm"...). O
    formato é normalizado antes ("08", "8" e "2026-08" na coluna "mes" dão o mesmo mês)."""
    import pandas as pd
    cols = {c.lower(): c for c in df.columns if c in comuns}
    if mes:
        return _aaaamm(df[mes]) if mes in df.columns else None
    if "ano" in cols and "mes" in cols:
        ano = pd.to_numeric(df[cols["ano"]], errors="coerce")
        m = pd.to_numeric(df[cols["mes"]], errors="coerce")
        saida = ano * 100 + m.where(m.between(1, 12))
        completo = _aaaamm(df[cols["mes"]])  # "2026-08" na coluna do mês
        return saida.fillna(completo)
    for c in (*COLUNAS_MES, "data"):
        if c in cols:
            return _aaaamm(df[cols[c]])
    return None


# colunas que não são valor (códigos, datas, números de documento): fora da conferência de valores
_NAO_VALOR = re.compile(r"^(ano|mes|ano_mes|aaaamm|competencia|mes_referencia|data\w*|inicio|fim|lido_em|visto_em|"
                        r"pedido_em|cod\w*|id|id_\w+|\w+_id|matricula|cnpj\w*|cpf\w*|documento|numero|num_\w+|nota|nf|"
                        r"processo|empenho|docid|orcamento|token|carteira|sq\w*|ue|referencia|lote|folha|tp|parcial|"
                        r"x|achados|registros|linhas\w*|pessoas)$", re.I)


def _colunas_valor(df):
    """Colunas de valor: as que não são código nem data e têm número em pelo menos 80% das células preenchidas."""
    import pandas as pd
    saida = []
    for c in df.columns:
        if _NAO_VALOR.match(str(c)):
            continue
        s = df[c][df[c].astype(str).str.strip() != ""]
        if len(s) and pd.to_numeric(s, errors="coerce").notna().mean() >= 0.8:
            saida.append(c)
    return saida


def _cobertura_csv(df, comuns, mes=None, entidade=None, retrato=False, valores=None):
    """{grupo (mês ou "arquivo"): (entidades, linhas, {coluna de valor: células com valor diferente de zero})}."""
    import pandas as pd
    if not len(df):
        return {}
    ent = entidade if entidade in comuns else next((c for c in COLUNAS_ENTIDADE if c in comuns), None)
    meses = None if retrato else _colunas_mes(df, comuns, mes)
    chave = df[ent] if ent else df.astype(str).agg("|".join, axis=1)
    grupo = pd.Series(0, index=df.index) if meses is None else meses.fillna(0).astype(int)
    g = chave.groupby(grupo)
    n, t = g.nunique(), g.size()
    nz = {c: (pd.to_numeric(df[c], errors="coerce").fillna(0).abs() > 0.004).groupby(grupo).sum()
          for c in (valores or []) if c in df.columns}
    nome = (lambda k: "arquivo") if meses is None else int
    return {nome(k): (int(n[k]), int(t[k]), {c: int(s.get(k, 0)) for c, s in nz.items()}) for k in n.index}


def _cheio(v):
    return not (v is None or v == "" or v == [] or v == {} or (isinstance(v, (int, float)) and not isinstance(v, bool)
                                                                and abs(v) < 0.004))


def _cobertura_json(dados, grupo=None, chaves=None, pessoas=()):
    """{grupo: (itens, {campo: itens com o campo preenchido})}. Uma lista de objetos ("p") se divide por cidade, órgão,
    estado ou tipo (GRUPOS_JSON ou `grupo`); um dicionário de dicionários ou de listas (municípios em "m", cidades em
    vereadores/<uf>.json), por chave: cada chave é um grupo; nos dicionários de pessoas (`pessoas`: os nomes, ou True
    para o primeiro nível), que podem sair do cargo, conta o número de chaves. Os campos de cada objeto são conferidos
    (valor que vira vazio ou zero em todos). A mesma estrutura vale para qualquer tamanho. chaves: só estas chaves do
    primeiro nível contam."""
    out = {}

    def campos(objs):
        c = {}
        for x in objs:
            if isinstance(x, dict):
                for k, v in x.items():
                    c[k] = c.get(k, 0) + (1 if _cheio(v) else 0)
        return c

    def lista(nome, v):
        objs = [x for x in v[:300] if isinstance(x, dict)]
        ch = None
        if objs and len(objs) == len(v[:300]):
            ch = grupo or next((g for g in GRUPOS_JSON if sum(g in x for x in objs) >= 0.8 * len(objs)), None)
        if ch:
            por = {}
            for x in v:
                por.setdefault(f"{nome}/{ch}={x.get(ch)}" if nome else f"{ch}={x.get(ch)}", []).append(x)
            for k, xs in por.items():
                out[k] = (len(xs), campos(xs))
        else:
            out[nome or "lista"] = (len(v), campos(v))

    def dicionario(nome, v, de_pessoas):
        recipientes = [x for x in v.values() if isinstance(x, (dict, list))]
        if de_pessoas or not v or len(recipientes) < 0.8 * len(v):
            out[nome or "chaves"] = (len(v), campos(v.values()))
            return
        for k, x in v.items():
            itens = (sum(1 for y in x.values() if _cheio(y)) if isinstance(x, dict) else len(x)) if isinstance(x, (dict, list)) \
                else (1 if _cheio(x) else 0)
            out[f"{nome}/{k}" if nome else str(k)] = (itens, campos(x) if isinstance(x, list) else {})

    if isinstance(dados, list):
        lista("", dados)
    elif isinstance(dados, dict):
        if chaves:
            dados = {k: v for k, v in dados.items() if k in chaves}
        topo = {k: v for k, v in dados.items() if k not in ("meta", "_sobre") and isinstance(v, (list, dict))}
        if pessoas is True:
            dicionario("", topo, True)
        elif topo and all(isinstance(v, dict) for v in topo.values()) and len(topo) > 1 and \
                not any(k in ("p", "m", "e", "antigos", "estados", "saidos", "fotos") for k in topo):
            dicionario("", topo, False)  # o primeiro nível é feito de entidades (cidades em vereadores/<uf>.json)
        else:
            for k, v in topo.items():
                if isinstance(v, list):
                    lista(k, v)
                else:
                    dicionario(k, v, k in (pessoas or ()))
    return out


def _cobertura(caminho, tipo, comuns=None, valores=None, **opcoes):
    if tipo == "json":
        try:
            dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError) as e:
            raise _Ilegivel(f"{type(e).__name__}: {e}") from e
        return {k: (n, n, c) for k, (n, c) in
                _cobertura_json(dados, opcoes.get("grupo"), opcoes.get("chaves"), opcoes.get("pessoas", ())).items()}
    df = _ler_tabela(caminho, opcoes.get("sep"))
    return _cobertura_csv(df, df.columns if comuns is None else comuns, opcoes.get("mes"), opcoes.get("entidade"),
                          opcoes.get("retrato", False), valores)


def _nome_grupo(g):
    if isinstance(g, int):
        return "sem mês" if g == 0 else f"mês {g % 100:02d}/{g // 100}"
    return "o arquivo" if g == "arquivo" else g


def perdas_de_cobertura(antes, depois, tipo="csv", **opcoes):
    """Compara o arquivo anterior com o novo. Devolve [(grupo, antes, depois, unidade)] (vazia: pode trocar). O novo
    que não se lê sobe como _Ilegivel (recusa), qualquer que seja o anterior; o anterior que não se lê não impede nada.
    opcoes: mes (coluna do mês), entidade (coluna da entidade), retrato (compara sem o mês), sep (CSV); grupo, chaves e
    pessoas (JSON, ver _cobertura_json)."""
    comuns = valores = None
    if tipo == "csv":
        novo = _ler_tabela(depois, opcoes.get("sep"))  # o novo primeiro: ilegível, recusa
        try:
            velho = _ler_tabela(antes, opcoes.get("sep"))
        except _Ilegivel:
            return []  # o anterior não se lê: não há com o que comparar
        comuns = [c for c in novo.columns if c in velho.columns]
        valores = [c for c in _colunas_valor(velho) if c in comuns]
        d = _cobertura_csv(novo, comuns, opcoes.get("mes"), opcoes.get("entidade"), opcoes.get("retrato", False), valores)
        a = _cobertura_csv(velho, comuns, opcoes.get("mes"), opcoes.get("entidade"), opcoes.get("retrato", False), valores)
    else:
        d = _cobertura(depois, tipo, **opcoes)
        try:
            a = _cobertura(antes, tipo, **opcoes)
        except _Ilegivel:
            return []
    unidade = "linhas" if tipo == "csv" else "itens"
    if a and not d:
        return [("arquivo", sum(x[1] for x in a.values()), 0, unidade)]
    if tipo == "csv" and not opcoes.get("retrato") and len(a) == 1 and len(d) == 1 and set(a) != set(d) \
            and all(isinstance(k, int) and k for k in (*a, *d)) and max(d) > max(a):
        # retrato do último mês (só um mês antes e depois): compara sem o mês
        a = _cobertura_csv(velho, comuns, None, opcoes.get("entidade"), True, valores)
        d = _cobertura_csv(novo, comuns, None, opcoes.get("entidade"), True, valores)
    perdas = []
    for g, (ea, la, va) in sorted(a.items(), key=lambda x: str(x[0])):
        ed, ld, vd = d.get(g, (0, 0, {}))
        if la and not ld:
            perdas.append((g, la, 0, unidade))
        elif ea - ed >= MINIMO_ENTIDADES and ed < (1 - PERDA_ENTIDADES) * ea:
            perdas.append((g, ea, ed, "entidades" if tipo == "csv" else "itens"))
        elif la - ld >= MINIMO_LINHAS and ld < (1 - PERDA_LINHAS) * la:
            perdas.append((g, la, ld, "linhas"))
        else:
            # valores: a coluna (CSV) ou o campo (JSON) que tinha valor e ficou vazio ou zero (campo que deixou de
            # existir em todos os objetos é mudança de formato, feita no código, e não entra)
            for c, n in sorted(va.items()):
                if c not in vd:
                    continue
                m = vd[c]
                if (n >= MINIMO_ENTIDADES and m == 0) or (n - m >= MINIMO_LINHAS and m < (1 - PERDA_LINHAS) * n):
                    perdas.append((g, n, m, f"com \"{c}\" preenchido"))
                    break
    return perdas


def _texto_perdas(perdas, n=3):
    t = "; ".join(u if g == "ilegível" else f"{_nome_grupo(g)}: {a} para {d} {u}" for g, a, d, u in perdas[:n])
    return t + (f" (e mais {len(perdas) - n})" if len(perdas) > n else "")


def _arquivo_eventos(lugar):
    from .config import PROCESSADOS
    return PROCESSADOS / f"recusas_{lugar}.json"


def _lugar():
    import os
    return os.environ.get("CONTAS_ONDE") or ("exterior" if os.environ.get("GITHUB_ACTIONS") else "brasil")


def ler_recusas():
    """{arquivo: último evento} juntando os dois lugares: o evento mais recente vale ("recusado" ou "aceito")."""
    juntos = {}
    for lugar in ("exterior", "brasil"):
        arq = _arquivo_eventos(lugar)
        try:
            d = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
        except ValueError:
            d = {}
        for k, ev in d.items():
            if k not in juntos or ev.get("quando", "") > juntos[k].get("quando", ""):
                juntos[k] = {**ev, "lugar": lugar}
    return juntos


def _anotar(rel, evento):
    """Guarda a recusa (ou o aceite de um arquivo que tinha sido recusado) em dados/processados/recusas_<lugar>.json."""
    global _eventos
    lugar = _lugar()
    arq = _arquivo_eventos(lugar)
    if _eventos is None:
        try:
            _eventos = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
        except ValueError:
            _eventos = {}
    if evento["estado"] == "aceito":
        ultimo = ler_recusas().get(rel)
        if not ultimo or ultimo["estado"] != "recusado":
            return
    _eventos[rel] = evento
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dict(sorted(_eventos.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _preparar(caminho, escrever, motivo, tipo, opcoes):
    """Grava o novo no temporário e compara com o anterior: {caminho, tmp, rel, perdas, motivo}."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tipo = tipo or ("json" if caminho.suffix == ".json" else "csv")
    p = {"caminho": caminho, "tmp": caminho.parent / f".novo.{caminho.name}", "rel": _rel(caminho), "motivo": motivo,
         "perdas": []}
    escrever(p["tmp"])
    try:
        if caminho.exists() and caminho.stat().st_size:
            p["perdas"] = perdas_de_cobertura(caminho, p["tmp"], tipo, **opcoes)
        elif tipo == "json":
            _cobertura(p["tmp"], tipo, **opcoes)  # sem anterior, o novo ainda tem de se ler
    except _Ilegivel as e:
        p["perdas"] = [("ilegível", 0, 0, f"o novo arquivo não se lê ({str(e)[:80]})")]
    return p


def _recusar(p, junto=""):
    from datetime import datetime
    texto = _texto_perdas(p["perdas"]) + junto
    log(f"  RECUSADO por perda de cobertura: {p['rel']}: {texto}. Fica o arquivo anterior.")
    _recusas.append({"arquivo": p["rel"], "fonte": _fonte_atual, "perdas": p["perdas"], "texto": texto})
    _anotar(p["rel"], {"estado": "recusado", "quando": datetime.now().isoformat(timespec="seconds"),
                       "fonte": _fonte_atual, "texto": texto,
                       "perdas": [[str(g), a, d, u] for g, a, d, u in p["perdas"][:20]]})


def _trocar(p):
    from datetime import datetime
    if p["perdas"]:
        log(f"  {p['rel']}: redução aceita ({p['motivo']}): {_texto_perdas(p['perdas'])}")
    p["tmp"].replace(p["caminho"])
    _anotar(p["rel"], {"estado": "aceito", "quando": datetime.now().isoformat(timespec="seconds"), "fonte": _fonte_atual})


def gravar_com(caminho, escrever, *, motivo=None, tipo=None, **opcoes):
    """Grava um arquivo de dados com segurança: escrever(tmp) grava o novo num arquivo temporário ao lado; se não perde
    cobertura grande (ver acima) ou se `motivo` explica a redução, o novo troca o anterior. Devolve True se trocou; se
    recusou, o anterior fica, a recusa vai para o log, para a situação (e para a fonte em coleta) e a função devolve
    False, sem erro: a rodada segue. tipo: "csv" ou "json" (sem ele, pela extensão; .gz conta como csv)."""
    p = None
    try:
        p = _preparar(caminho, escrever, motivo, tipo, opcoes)
        if p["perdas"] and not motivo:
            _recusar(p)
            return False
        _trocar(p)
        return True
    finally:
        tmp = Path(caminho).parent / f".novo.{Path(caminho).name}"
        if tmp.exists():
            tmp.unlink()


def gravar_varios(itens):
    """Vários arquivos que andam juntos (os dados e o arquivo de controle que diz o que já foi lido): todos ou nenhum.
    itens: [(DataFrame, caminho) ou (DataFrame, caminho, {argumentos do to_csv, motivo, mes, entidade, retrato})], com
    o controle por último. Compara todos antes de trocar; se um for recusado, nenhum é trocado (devolve False)."""
    prep = []
    try:
        for item in itens:
            df, caminho, op = item[0], item[1], dict(item[2]) if len(item) > 2 else {}
            motivo = op.pop("motivo", None)
            comp = {k: op.pop(k) for k in ("mes", "entidade", "retrato") if k in op}
            op.setdefault("index", False)
            prep.append(_preparar(caminho, lambda tmp, df=df, op=op: df.to_csv(tmp, **op), motivo, "csv",
                                  {**comp, "sep": op.get("sep")}))
        ruins = [p for p in prep if p["perdas"] and not p["motivo"]]
        if ruins:
            outros = [p["rel"] for p in prep if p not in ruins]
            for p in ruins:
                _recusar(p, f" (e não foram trocados: {', '.join(outros)})" if outros else "")
            return False
        for p in prep:
            _trocar(p)
        return True
    finally:
        for p in prep:
            if p["tmp"].exists():
                p["tmp"].unlink()


def gravar_csv(df, caminho, *, motivo=None, mes=None, entidade=None, retrato=False, **to_csv):
    """DataFrame -> CSV pela gravação segura. to_csv: os argumentos do DataFrame.to_csv (index=False por padrão)."""
    to_csv.setdefault("index", False)
    return gravar_com(caminho, lambda tmp: df.to_csv(tmp, **to_csv), motivo=motivo, tipo="csv", mes=mes,
                      entidade=entidade, retrato=retrato, sep=to_csv.get("sep"))


def gravar_linhas(caminho, campos, linhas, *, delimiter=",", motivo=None, dicionarios=True, extrasaction="raise",
                  lineterminator="\r\n", **opcoes):
    """Lista de dicionários (ou de listas, com dicionarios=False) -> CSV (módulo csv) pela gravação segura."""
    import csv

    def escrever(tmp):
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            if dicionarios:
                w = csv.DictWriter(f, fieldnames=campos, delimiter=delimiter, extrasaction=extrasaction,
                                   lineterminator=lineterminator)
                w.writeheader()
            else:
                w = csv.writer(f, delimiter=delimiter, lineterminator=lineterminator)
                if campos:
                    w.writerow(campos)
            w.writerows(linhas)
    return gravar_com(caminho, escrever, motivo=motivo, tipo="csv", sep=delimiter, **opcoes)


def gravar_texto(caminho, texto, *, motivo=None, tipo=None, **opcoes):
    """Texto já pronto (JSON ou CSV) pela gravação segura."""
    return gravar_com(caminho, lambda tmp: Path(tmp).write_text(texto, encoding="utf-8"), motivo=motivo, tipo=tipo,
                      **opcoes)


def gravar_json(caminho, dados, *, compacto=True, indent=None, final="", motivo=None, **opcoes):
    """Objeto -> JSON pela gravação segura. compacto: sem espaços (os arquivos do site); senão, com `indent`."""
    texto = (json.dumps(dados, ensure_ascii=False, separators=(",", ":")) if compacto and indent is None
             else json.dumps(dados, ensure_ascii=False, indent=indent)) + final
    return gravar_texto(caminho, texto, motivo=motivo, tipo="json", **opcoes)


def recusas_desde(marca, fonte=None):
    """As recusas desta execução a partir da posição `marca` (de len(util._recusas)), só as da fonte, se dada."""
    return [r for r in _recusas[marca:] if fonte is None or r["fonte"] == fonte]


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
    O robots.txt desses portais pede que robôs não usem a API (/api/) e 10 s entre os pedidos (Crawl-delay); a página do
    conjunto e os arquivos (/dataset/.../download/...) bastam, e são o caminho usado desde antes de 08/10/2026."""
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
