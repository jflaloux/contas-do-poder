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
# User-Agent e para se o site bloquear.
EXCECOES_ROBOTS = [
    ("https://www.camara.leg.br/deputados/",
     "Câmara dos Deputados: salário, 13º, férias, diárias e pessoal de gabinete de cada deputado (remuneração de "
     "agente público, que a LAI manda publicar; o robots.txt proíbe /deputados/*/* desde 18/09/2026)", 0.25),
    ("https://dados.prefeitura.sp.gov.br/",
     "Prefeitura de São Paulo: folha de pagamento nos dados abertos (o robots.txt do portal tem Disallow: /)", 10),
    ("https://www.transparencia.pr.gov.br/pte/",
     "Paraná: remuneração do governador e do vice no Portal da Transparência (o robots.txt tem Disallow: /pte)", 2),
    ("https://dadosabertos.almg.gov.br/ws/",
     "Assembleia de Minas Gerais: deputados e verba indenizatória nos dados abertos da ALMG (serviço feito para acesso "
     "automatizado; o robots.txt tem Disallow: /)", 1),
    ("https://docigp.alerj.rj.gov.br/",
     "Assembleia do Rio de Janeiro: verba indenizatória de cada deputado no DOCIGP, o portal de transparência da verba "
     "(o robots.txt tem Disallow: /)", 0.5),
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
    der = _sessao().get(url, timeout=60).content  # pela sessão do projeto (robots.txt, User-Agent), como todo pedido
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


def _ler_tabela(caminho, sep=None):
    import pandas as pd
    if sep is None:
        import gzip
        abrir = gzip.open if str(caminho).endswith(".gz") else open
        with abrir(caminho, "rt", encoding="utf-8", errors="replace") as f:
            cab = f.readline()
        sep = ";" if cab.count(";") > cab.count(",") else ","
    try:
        return pd.read_csv(caminho, sep=sep, dtype=str, keep_default_na=False, low_memory=False, encoding="utf-8",
                           encoding_errors="replace")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (pd.errors.ParserError, UnicodeError, OSError) as e:
        raise _Ilegivel(str(e)) from e


def _colunas_mes(df, comuns, mes=None):
    cols = {c.lower(): c for c in df.columns if c in comuns}
    if mes:
        return _aaaamm(df[mes]) if mes in df.columns else None
    if "ano" in cols and "mes" in cols:
        import pandas as pd
        return pd.to_numeric(df[cols["ano"]], errors="coerce") * 100 + pd.to_numeric(df[cols["mes"]], errors="coerce")
    for c in (*COLUNAS_MES, "data"):
        if c in cols:
            return _aaaamm(df[cols[c]])
    return None


def _cobertura_csv(df, comuns, mes=None, entidade=None, retrato=False):
    """{grupo (mês ou "arquivo"): (entidades, linhas)}."""
    if not len(df):
        return {}
    ent = entidade if entidade in comuns else next((c for c in COLUNAS_ENTIDADE if c in comuns), None)
    meses = None if retrato else _colunas_mes(df, comuns, mes)
    chave = df[ent] if ent else df.astype(str).agg("|".join, axis=1)
    if meses is None:
        return {"arquivo": (int(chave.nunique()), len(df))}
    g = chave.groupby(meses.fillna(0).astype(int))
    n, t = g.nunique(), g.size()
    return {int(k): (int(n[k]), int(t[k])) for k in n.index}


def _cobertura_json(dados, grupo=None, chaves=None):
    """{grupo: quantidade}: a lista "p" (e outras listas de objetos) por cidade, órgão, estado ou tipo; outras listas e
    dicionários pelo tamanho; um dicionário com muitas chaves (ids, municípios), pelo número de chaves. chaves: só estas
    chaves do primeiro nível contam (as outras podem encolher sem aviso)."""
    out = {}
    if chaves and isinstance(dados, dict):
        dados = {k: v for k, v in dados.items() if k in chaves}

    def lista(nome, v):
        objetos = [x for x in v[:300] if isinstance(x, dict)]
        ch = None
        if objetos and len(objetos) == len(v[:300]):
            ch = grupo or next((g for g in GRUPOS_JSON if sum(g in x for x in objetos) >= 0.8 * len(objetos)), None)
        if ch:
            for x in v:
                k = f"{nome}/{ch}={x.get(ch)}" if nome else f"{ch}={x.get(ch)}"
                out[k] = out.get(k, 0) + 1
        else:
            out[nome or "lista"] = len(v)

    if isinstance(dados, list):
        lista("", dados)
    elif isinstance(dados, dict):
        itens = [(k, v) for k, v in dados.items() if k not in ("meta", "_sobre") and isinstance(v, (list, dict))]
        if len(itens) > 50:
            out["chaves"] = len(itens)
        for k, v in itens if len(itens) <= 50 else []:
            if isinstance(v, list):
                lista(k, v)
            else:
                out[k] = len(v)
    return out


def _cobertura(caminho, tipo, comuns=None, **opcoes):
    if tipo == "json":
        try:
            dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as e:
            raise _Ilegivel(str(e)) from e
        return {k: (v, v) for k, v in _cobertura_json(dados, opcoes.get("grupo"), opcoes.get("chaves")).items()}
    df = _ler_tabela(caminho, opcoes.get("sep"))
    return _cobertura_csv(df, df.columns if comuns is None else comuns, opcoes.get("mes"), opcoes.get("entidade"),
                          opcoes.get("retrato", False))


def _nome_grupo(g):
    if isinstance(g, int):
        return "sem mês" if g == 0 else f"mês {g % 100:02d}/{g // 100}"
    return "o arquivo" if g == "arquivo" else g


def perdas_de_cobertura(antes, depois, tipo="csv", **opcoes):
    """Compara o arquivo anterior com o novo. Devolve [(grupo, antes, depois, unidade)] (vazia: pode trocar).
    opcoes: mes (coluna do mês), entidade (coluna da entidade), retrato (compara sem o mês), grupo (JSON), sep (CSV)."""
    comuns = None
    if tipo == "csv":
        try:
            ca = list(_ler_tabela(antes, opcoes.get("sep")).columns)
        except _Ilegivel:
            return []  # o anterior não se lê: não há com o que comparar
        cn = list(_ler_tabela(depois, opcoes.get("sep")).columns)
        comuns = [c for c in cn if c in ca]
    try:
        a = _cobertura(antes, tipo, comuns, **opcoes)
    except _Ilegivel:
        return []
    d = _cobertura(depois, tipo, comuns, **opcoes)  # o novo ilegível: _Ilegivel sobe (recusa)
    unidade = "linhas" if tipo == "csv" else "itens"
    if a and not d:
        return [("arquivo", sum(t for _, t in a.values()), 0, unidade)]
    if tipo == "csv" and not opcoes.get("retrato") and len(a) == 1 and len(d) == 1 and set(a) != set(d) \
            and all(isinstance(k, int) and k for k in (*a, *d)) and max(d) > max(a):
        # retrato do último mês (só um mês antes e depois): compara sem o mês
        sem_mes = {k: v for k, v in opcoes.items() if k != "retrato"}
        a = _cobertura(antes, tipo, comuns, retrato=True, **sem_mes)
        d = _cobertura(depois, tipo, comuns, retrato=True, **sem_mes)
    perdas = []
    for g, (ea, la) in sorted(a.items(), key=lambda x: str(x[0])):
        ed, ld = d.get(g, (0, 0))
        if la and not ld:
            perdas.append((g, la, 0, unidade))
        elif ea - ed >= MINIMO_ENTIDADES and ed < (1 - PERDA_ENTIDADES) * ea:
            perdas.append((g, ea, ed, "entidades" if tipo == "csv" else "itens"))
        elif la - ld >= MINIMO_LINHAS and ld < (1 - PERDA_LINHAS) * la:
            perdas.append((g, la, ld, "linhas"))
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


def gravar_com(caminho, escrever, *, motivo=None, tipo=None, **opcoes):
    """Grava um arquivo de dados com segurança: escrever(tmp) grava o novo num arquivo temporário ao lado; se não perde
    cobertura grande (ver acima) ou se `motivo` explica a redução, o novo troca o anterior. Devolve True se trocou; se
    recusou, o anterior fica, a recusa vai para o log, para a situação (e para a fonte em coleta) e a função devolve
    False, sem erro: a rodada segue. tipo: "csv" ou "json" (sem ele, pela extensão; .gz conta como csv)."""
    from datetime import datetime
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tipo = tipo or ("json" if caminho.suffix == ".json" else "csv")
    tmp = caminho.parent / f".novo.{caminho.name}"
    rel = _rel(caminho)
    try:
        escrever(tmp)
        perdas = []
        if caminho.exists() and caminho.stat().st_size:
            try:
                perdas = perdas_de_cobertura(caminho, tmp, tipo, **opcoes)
            except _Ilegivel as e:
                perdas = [("ilegível", 0, 0, f"o novo arquivo não se lê ({str(e)[:80]})")]
        agora = datetime.now().isoformat(timespec="seconds")
        if perdas and not motivo:
            texto = _texto_perdas(perdas)
            log(f"  RECUSADO por perda de cobertura: {rel}: {texto}. Fica o arquivo anterior.")
            _recusas.append({"arquivo": rel, "fonte": _fonte_atual, "perdas": perdas, "texto": texto})
            _anotar(rel, {"estado": "recusado", "quando": agora, "fonte": _fonte_atual, "texto": texto,
                          "perdas": [[str(g), a, d, u] for g, a, d, u in perdas[:20]]})
            return False
        if perdas:
            log(f"  {rel}: redução aceita ({motivo}): {_texto_perdas(perdas)}")
        tmp.replace(caminho)
        _anotar(rel, {"estado": "aceito", "quando": agora, "fonte": _fonte_atual})
        return True
    finally:
        if tmp.exists():
            tmp.unlink()


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
