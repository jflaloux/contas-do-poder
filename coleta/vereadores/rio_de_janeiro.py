"""Câmara Municipal do Rio de Janeiro: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro; os servidores só respondem para endereços do Brasil):
- Vereadores da legislatura (a 12ª, 2025–2028), inclusive os que já saíram: https://www.camara.rio/vereadores/anteriores
  (todos os vereadores, com as legislaturas de cada um); no cargo hoje:
  https://www.camara.rio/includes_php/vereadores_atuais.php
- Nome civil, partido e foto: https://www.camara.rio/vereadores/<nome>; períodos no cargo, com as datas de posse e de
  saída (licenças, suplentes que assumem): https://www.camara.rio/vereadores/<nome>/mandatos
- Gabinete de cada vereador (Nº 01 a Nº 51): https://transparencia.camara.rj.gov.br/vereadores/gabinetes-dos-vereadores/lotacao
- Subsídio: R$ 26.080,98 por mês, o valor dos contracheques da Câmara
  (https://aplicsc.camara.rj.gov.br/scriptcase/sistemas/contracheque/Ctrl_Pesquisa/, um contracheque por vez, pelo
  nome civil; não pede CPF). A página "Salário dos Vereadores" do Portal da Transparência ainda mostra R$ 19.127,52
  (valor antigo). Nos meses inteiros no cargo vale o subsídio (conferido numa amostra de contracheques); nos meses em
  que o vereador ficou só parte do mês no cargo, o contracheque do mês é baixado (uma vez só) e vale o que ele pagou.
  Só o bruto é guardado: descontos, líquido e matrícula ficam de fora.
- Vale-refeição/alimentação, por nome e por mês (publicado desde out/2025):
  https://transparencia.camara.rj.gov.br/vereadores/cota-de-gabinete/auxilio-alimentacao
- Cota de combustível (abastecimento, lubrificação, lavagem, troca de óleo e manutenção dos veículos do mandato),
  por vereador e por mês: https://transparencia.camara.rj.gov.br/vereadores/cota-de-gabinete/abastecimento-e-manutencao
  Não há verba de gabinete em dinheiro, como a CEAP.
- Servidores lotados em cada gabinete, retrato do dia (dados abertos, JSON):
  https://aplicsc.camara.rj.gov.br/scriptcase/Sistemas/Portal_Transparencia/DadosAbertos/Cons_Relacao_Servidores_API_json/
  Guardamos só o número de pessoas e os cargos de cada gabinete, sem nomes.
- Gênero e situação na eleição (eleito ou suplente): TSE (eleição de 2024).

Os servidores da Câmara (*.camara.rio e *.camara.rj.gov.br) não mandam o certificado intermediário da Sectigo.
O robô baixa esse certificado do endereço oficial da Sectigo (o mesmo que o próprio certificado do site indica),
confere que ele é assinado por uma raiz do certifi e monta um arquivo de certificados (certifi + intermediário) em
dados/cache/cmrj/, usado em todos os pedidos. A verificação do certificado nunca é desligada.
"""
import base64
import html as html_lib
import io
import json
import re
import subprocess
import time
import warnings
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from ..config import CACHE, DADOS, HOJE, USER_AGENT
from ..util import SessaoEducada, TempoEsgotado, cache_valido, log, normalizar_nome, verificar_prazo
from . import comum

COD = 3304557
INICIO = 202501
LEGISLATURA = "12"  # 12ª legislatura: 2025–2028
SITE = "https://www.camara.rio"
TRANSP = "https://transparencia.camara.rj.gov.br"
APLIC = "https://aplicsc.camara.rj.gov.br"
CONTRACHEQUE = f"{APLIC}/scriptcase/sistemas/contracheque/"
SERVIDORES = f"{APLIC}/scriptcase/Sistemas/Portal_Transparencia/DadosAbertos/Cons_Relacao_Servidores_API_json/"
NUCLEOS = f"{TRANSP}/996-tabela-atual-de-nucleos-dos-gabinetes/file"
PASTA = DADOS / "municipios" / "rio_de_janeiro"
C = CACHE / "cmrj"
# subsídio pelos contracheques (a conta bate com 75% de 75% do subsídio dos deputados federais: R$ 44.008,52 até
# janeiro de 2025 e R$ 46.366,19 desde fevereiro de 2025).
SUBSIDIOS = [[202501, 24754.79], [202502, 26080.98]]


def _subsidio(aaaamm):
    return [v for de, v in SUBSIDIOS if aaaamm >= de][-1]


# certificado intermediário que os servidores da Câmara não mandam (endereço "CA Issuers" do próprio certificado)
INTERMEDIARIO = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt"
# planilhas por ano no Portal da Transparência: (pasta, palavra no endereço do arquivo, arquivos de reserva). A pasta
# de cada ano lista o arquivo (o endereço muda quando a Câmara publica uma versão nova).
ARQUIVOS = {
    "combustivel": ("/vereadores/cota-de-gabinete/abastecimento-e-manutencao", "combust",
                    {2025: "/2025-6/964-tabela-combustivel-2025/file", 2026: "/2026-1/1005-tabela-combustivel-2026/file"}),
    "alimentacao": ("/vereadores/cota-de-gabinete/auxilio-alimentacao", "aliment",
                    {2025: "/2025-7/978-auxilio-alimentacao-2025/file", 2026: "/2026/982-auxilio-alimentacao-2026/file"}),
}
# contracheques conferidos além dos meses de troca (nome civil, ano, mês): meses inteiros no cargo (o ano de 2025 de
# uma titular, dezembro, o mês seguinte a uma volta) e meses de licença. Cada um é baixado uma vez só (fica no cache).
# Só o bruto é guardado.
AMOSTRA_CONTRACHEQUES = [("CARLOS NANTES BOLSONARO", 2025, 3), ("ROSA MARIA ORLANDO FERNANDES", 2025, 11),
                         ("ROSA MARIA ORLANDO FERNANDES", 2025, 12), ("ROSA MARIA ORLANDO FERNANDES", 2026, 1),
                         ("ROSA MARIA ORLANDO FERNANDES", 2026, 7), ("CARLO FERREIRA DE CAIADO CASTRO", 2025, 12),
                         ("CARLO FERREIRA DE CAIADO CASTRO", 2026, 7), ("JOYCE TRINDADE DE FARIA GAMA", 2026, 5),
                         ("FLAVIO DAS GRAÇAS MIRANDA", 2025, 2), ("FLAVIO DAS GRAÇAS MIRANDA", 2025, 3),
                         ("FLAVIO DAS GRAÇAS MIRANDA", 2025, 11), ("ROGÉRIO DE CASTRO LOPES", 2025, 2),
                         ("TATIANA MARINS ROQUE", 2025, 2), ("TATIANA MARINS ROQUE", 2025, 3), ("LUIS ANTONIO DA COSTA RAMOS", 2025, 9),
                         ("MARCIO SANTOS DE ARAUJO", 2025, 3), ("MARCIO SANTOS DE ARAUJO", 2025, 11), ("MARCIO SANTOS DE ARAUJO", 2026, 7),
                         ("MARCIO SANTOS DE ARAUJO", 2026, 3), ("LUIS ANTONIO DA COSTA RAMOS", 2026, 2), ("JOYCE TRINDADE DE FARIA GAMA", 2026, 4),
                         ("TATIANA MARINS ROQUE", 2026, 4), ("DIEGO DE ANDRADE FARO TELES", 2026, 2), ("DIEGO DE ANDRADE FARO TELES", 2026, 5),
                         ("FLAVIO DAS GRAÇAS MIRANDA", 2026, 6)] + [("ROSA MARIA ORLANDO FERNANDES", 2025, m) for m in range(1, 11)]
MESES_NOME = {normalizar_nome(n): i for i, n in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                                                           "Setembro", "Outubro", "Novembro", "Dezembro"], 1)}
CFG = {
    "cod": COD, "n": "Rio de Janeiro", "uf": "RJ", "casa": "Câmara Municipal do Rio de Janeiro", "vagas": 51, "inicio": INICIO,
    "subsidio": SUBSIDIOS,
    "salario_nota": ("Subsídio de R$ 26.080,98 por mês desde fevereiro de 2025 (R$ 24.754,79 em janeiro de 2025), o valor dos "
                     "contracheques da Câmara; a página “Salário dos Vereadores” do Portal da Transparência ainda mostra R$ 19.127,52, "
                     "um valor antigo. Nos contracheques conferidos de meses inteiros no cargo, o bruto é exatamente o subsídio, sem 13º "
                     "nem férias. Nos meses em que o vereador ficou só parte do mês no cargo (licenças e suplentes), vale o que o "
                     "contracheque do mês pagou: a folha fecha antes do fim do mês e às vezes paga o mês inteiro, às vezes nada (quem "
                     "está licenciado e volta por poucos dias não aparece na folha). Soma-se o vale-refeição/alimentação, que a Câmara "
                     "publica por nome desde outubro de 2025 e que não aparece no contracheque."),
    "verba_nome": "Cota de combustível",
    "verba_regra": ("Até 1.000 litros de combustível por mês, pelo preço de referência da ANP, para abastecimento, lubrificação, lavagem, "
                    "troca de óleo e manutenção dos veículos usados no mandato (Resoluções da Mesa Diretora 1.369/1990 e 4.553/2002)."),
    "verba_notas": ["A Câmara publica o valor usado por vereador e por mês, sem as notas.",
                    "A Câmara do Rio não tem verba de gabinete em dinheiro, como a cota dos deputados: por vereador, publica a cota de "
                    "combustível e o vale-refeição/alimentação. O reembolso do aluguel de carro blindado, que alguns vereadores recebem, não entra aqui."],
    "conferir_gastos": False,  # a planilha de combustível sai com meses de atraso
    "equipe_nota": ("Servidores lotados no gabinete, pela relação de servidores da Câmara (dados abertos), no dia da coleta. Cada gabinete "
                    "tem 20 cargos em comissão, que a Mesa Diretora pode desmembrar sem aumentar a despesa (Lei 8.058/2023): por isso há "
                    "gabinetes com mais de 30 pessoas. A Câmara não publica o custo da equipe de cada gabinete; pela tabela de símbolos "
                    "da Câmara, os 20 cargos somam cerca de R$ 135 mil brutos por mês (estimativa, sem encargos nem auxílios)."),
    "credito_foto": "Câmara Municipal do Rio de Janeiro", "pagina": f"{SITE}/vereadores/quem-sao",
    "fontes": {"vereadores": f"{SITE}/vereadores/anteriores", "subsidio": CONTRACHEQUE + "Ctrl_Pesquisa/",
               "alimentacao": TRANSP + ARQUIVOS["alimentacao"][0], "combustivel": TRANSP + ARQUIVOS["combustivel"][0],
               "gabinetes": f"{TRANSP}/vereadores/gabinetes-dos-vereadores/lotacao", "servidores": f"{TRANSP}/recursos-humanos/relacao-de-servidores"},
}


# ---------------------------------------------------------------- acesso (certificado e pedidos)
_s = None


def _ca():
    """Arquivo de certificados para os servidores da Câmara: os do certifi mais o intermediário da Sectigo, que eles não
    mandam. O intermediário só entra se for mesmo assinado por uma das raízes do certifi."""
    import certifi
    destino = C / "ca_cmrj.pem"
    raizes_pem = Path(certifi.where()).read_bytes()
    if cache_valido(destino, 30) and destino.read_bytes().startswith(raizes_pem[:4096]):
        return str(destino)
    verificar_prazo()
    der = requests.get(INTERMEDIARIO, headers={"User-Agent": USER_AGENT}, timeout=60).content
    pem = _conferir_intermediario(der, raizes_pem, certifi.where())
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(raizes_pem.rstrip(b"\n") + b"\n\n# Sectigo Public Server Authentication CA OV R36 (" + INTERMEDIARIO.encode() + b")\n" + pem)
    tmp.replace(destino)
    log("  Rio de Janeiro: certificado intermediário da Sectigo conferido e guardado")
    return str(destino)


def _conferir_intermediario(der, raizes_pem, arquivo_raizes):
    """Confere o certificado intermediário (DER) contra as raízes do certifi e devolve o PEM. Usa o pacote cryptography;
    sem ele, o openssl da máquina. Se não der para conferir, para (nunca desliga a verificação)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
    except ImportError:
        x509 = None
    if x509 is not None:
        inter = x509.load_der_x509_certificate(der)
        emissores = []
        for bloco in re.findall(rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", raizes_pem, re.S):
            try:
                with warnings.catch_warnings():  # uma ou outra raiz antiga do certifi tem número de série fora da norma
                    warnings.simplefilter("ignore")
                    raiz = x509.load_pem_x509_certificate(bloco)
            except Exception:  # noqa: BLE001
                continue
            if raiz.subject == inter.issuer:
                emissores.append(raiz)
        assinado = False
        for raiz in emissores:
            try:
                inter.verify_directly_issued_by(raiz)
                assinado = True
                break
            except Exception:  # noqa: BLE001 — outra raiz com o mesmo nome
                continue
        agora = datetime.now(timezone.utc)
        ca = inter.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        if not (assinado and ca and inter.not_valid_before_utc <= agora <= inter.not_valid_after_utc):
            raise RuntimeError(f"o certificado baixado de {INTERMEDIARIO} não confere com as raízes do certifi")
        return inter.public_bytes(Encoding.PEM)
    pem = subprocess.run(["openssl", "x509", "-inform", "DER"], input=der, capture_output=True, check=True).stdout
    tmp = C / "intermediario.pem"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(pem)
    r = subprocess.run(["openssl", "verify", "-CAfile", arquivo_raizes, str(tmp)], capture_output=True, text=True)
    tmp.unlink()
    if r.returncode != 0 or not r.stdout.strip().endswith("OK"):
        raise RuntimeError(f"o certificado baixado de {INTERMEDIARIO} não confere com as raízes do certifi")
    return pem


def _sessao():
    global _s
    if _s is None:
        _s = SessaoEducada()  # lê o robots.txt e respeita o Crawl-delay
        _s.headers["User-Agent"] = USER_AGENT
        _s.verify = _ca()
    return _s


def _pedir(url, arquivo=None, dias=None, metodo="GET", tentativas=3, **kw):
    """Conteúdo (bytes) de um endereço da Câmara, com cache opcional e 1 s de pausa entre pedidos."""
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_bytes()
    verificar_prazo()
    for tentativa in range(tentativas):
        try:
            r = _sessao().request(metodo, url, timeout=(20, 180), **kw)
            r.raise_for_status()
            break
        except requests.RequestException as e:
            resp = getattr(e, "response", None)
            if tentativa == tentativas - 1 or (resp is not None and resp.status_code in (403, 404)):
                raise
            time.sleep(5 * (tentativa + 1))
    time.sleep(1)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = arquivo.with_suffix(arquivo.suffix + ".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(arquivo)
    return r.content


def _texto(conteudo, cod="utf-8"):
    return conteudo.decode(cod, errors="replace")


def _limpo(t):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def _json(arquivo, dias, fazer):
    """Resultado guardado em JSON no cache (para retomar a coleta de onde parou)."""
    if cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    d = fazer()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


# ---------------------------------------------------------------- coleta: vereadores, mandatos e fotos
def _lista_legislatura():
    """{cvd: nome} de quem teve mandato na legislatura atual (página "Vereadores anteriores", que traz todos)."""
    t = _texto(_pedir(f"{SITE}/vereadores/anteriores", C / "anteriores.html", 5))
    i = t.find('class="TabelaPadrao')
    saida = {}
    for tr in re.findall(r"<tr>.*?</tr>", t[i:t.find("</table>", i)], re.S):
        a = re.search(r"cvd=(\d+)'?\"?>([^<]+)</a>", tr)
        if a and re.search(r"<b>\s*%s\s*ª" % LEGISLATURA, tr):
            saida[int(a.group(1))] = html_lib.unescape(a.group(2)).strip()
    return saida


def _atuais():
    """{cvd: (nome, partido)} dos vereadores no cargo hoje (titulares e suplentes em exercício)."""
    t = _texto(_pedir(f"{SITE}/includes_php/vereadores_atuais.php?imprimir=N", C / "atuais.html", 1), "latin1")
    saida = {}
    for tr in re.findall(r"<tr>.*?</tr>", t, re.S):
        nomes = re.findall(r"vereador\.php\?cvd=(\d+)' target='_top'>([^<]+)</a>", tr)
        partido = re.search(r'foto-partido.*?alt="([^"]*)"', tr, re.S)
        if nomes:
            cvd, nome = nomes[0]
            saida[int(cvd)] = (html_lib.unescape(nome).strip(), partido.group(1).strip() if partido else "")
    return saida


def _perfil(cvd):
    """Endereço, nome civil e partido do vereador (e a foto, guardada em site/fotos)."""
    def fazer():
        red = _texto(_pedir(f"{SITE}/includes_php/vereador.php?cvd={cvd}"))
        slug = re.search(r'location\.href\s*=\s*"(/vereadores/[^"]+)"', red).group(1)
        t = _texto(_pedir(SITE + slug))
        linhas = [l.strip() for l in html_lib.unescape(re.sub(r"<[^>]+>", "\n", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))).split("\n") if l.strip()]

        def depois(rotulo):
            return next((linhas[i + 1] for i, l in enumerate(linhas[:-1]) if l == rotulo), "")
        foto = re.search(r"<img src=['\"]data:image/[a-z]+;base64,([A-Za-z0-9+/=]+)['\"] width=['\"]195", t)
        _salvar_foto(cvd, base64.b64decode(foto.group(1)) if foto else None)
        return {"slug": slug, "nome_civil": depois("Nome civil:"), "partido": depois("Partido:")}
    return _json(C / "perfil" / f"{cvd}.json", 60, fazer)


def _salvar_foto(cvd, conteudo):
    """Igual a comum.fotos, mas a foto vem dentro da página (data:image), e não de um endereço."""
    from ..fotos import _ajustar
    destino = comum.FOTOS / f"ver-{COD}-{cvd}.webp"
    if destino.exists() or not conteudo:
        return
    try:
        comum.FOTOS.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(_ajustar(conteudo))
    except Exception as e:  # noqa: BLE001 — sem foto, o site mostra as iniciais
        log(f"  foto do vereador {cvd}: {e}")


def _mandatos(cvd, slug):
    """Partidos e períodos no cargo na legislatura atual: [["AAAA-MM-DD", "AAAA-MM-DD" ou ""], ...]."""
    def fazer():
        t = _texto(_pedir(f"{SITE}{slug}/mandatos"))
        i = t.find('class="TabelaPadrao')
        for tr in re.findall(r"<tr>.*?</tr>", t[i:t.find("</table>", i)], re.S):
            cel = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(cel) >= 2 and _limpo(cel[0]).replace("ª", "") == LEGISLATURA:
                texto = _limpo(cel[1])
                per = [[_iso(a), "" if "presente" in b else _iso(b)]
                       for a, b in re.findall(r"\((\d{2}/\d{2}/\d{4})\s+até\s+(\d{2}/\d{2}/\d{4}|a\s+presente\s+data)\s*\)", texto)]
                return {"partidos": re.sub(r"\s*\(.*$", "", texto).strip(), "periodos": per}
        return {"partidos": "", "periodos": []}
    return _json(C / "mandatos" / f"{cvd}.json", 7, fazer)


def _iso(dmy):
    d, m, a = dmy.split("/")
    return f"{a}-{m}-{d}"


def vereadores():
    leg = _lista_legislatura()
    atuais = _atuais()
    linhas, per = [], []
    for cvd in sorted(set(leg) | set(atuais)):
        p = _perfil(cvd)
        m = _mandatos(cvd, p["slug"])
        nome = atuais.get(cvd, (leg.get(cvd, ""), ""))[0] or leg.get(cvd, "")
        linhas.append({"codigo": cvd, "nome": re.sub(r"\bMst\b", "MST", nome), "nome_civil": p["nome_civil"],
                       "partido": atuais.get(cvd, ("", ""))[1] or p["partido"] or m["partidos"].split(",")[-1].strip(),
                       "partidos_legislatura": m["partidos"],
                       "pagina": SITE + p["slug"], "no_cargo_hoje": cvd in atuais})
        for ini, fim in m["periodos"]:
            per.append({"codigo": cvd, "inicio": ini, "fim": fim})
    df = pd.DataFrame(linhas)
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "vereadores.csv", index=False)
    pd.DataFrame(per, columns=["codigo", "inicio", "fim"]).to_csv(PASTA / "mandatos.csv", index=False)
    sem = df[~df.codigo.isin({x["codigo"] for x in per})].nome.tolist()
    log(f"  Rio de Janeiro: {len(df)} vereadores na legislatura ({len(atuais)} no cargo hoje), {len(per)} períodos no cargo"
        + (f"; sem período: {', '.join(sem)}" if sem else ""))
    return df


def gabinetes():
    """Núcleo e número de cada gabinete, com o vereador titular e o suplente em exercício (tabela atual da Câmara)."""
    d = pd.read_excel(io.BytesIO(_pedir(NUCLEOS, C / "nucleos.xls", 5)), header=None, dtype=str).fillna("")
    linhas = []
    for r in d.itertuples(index=False):
        num = re.search(r"N[º°o]\s*(\d+)", str(r[1]))
        nucleo = re.sub(r"\.0$", "", str(r[0]).strip())
        if re.fullmatch(r"\d{6}", nucleo) and num:
            linhas.append({"nucleo": nucleo, "gabinete": int(num.group(1)), "titular": str(r[2]).strip(),
                           "suplente": str(r[3]).strip() if len(r) > 3 else ""})
    PASTA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_csv(PASTA / "gabinetes.csv", index=False)
    log(f"  Rio de Janeiro: {len(linhas)} gabinetes")


# ---------------------------------------------------------------- coleta: planilhas do Portal da Transparência
def _arquivos_do_ano(tipo, ano):
    """Endereços das planilhas publicadas na pasta do ano (a página lista os arquivos; se mudar, usa o de reserva)."""
    pagina, palavra, reserva = ARQUIVOS[tipo]
    try:
        t = _texto(_pedir(f"{TRANSP}{pagina}/{ano}"))
        achados = [u for u in dict.fromkeys(re.findall(r'href="(/[^"]+/file)"', t)) if palavra in u.lower()]
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"  Rio de Janeiro: a pasta {pagina}/{ano} não abriu ({e})")
        achados = []
    return achados or ([reserva[ano]] if ano in reserva else [])


def _planilhas(tipo):
    """[(ano, conteúdo)] das planilhas de cada ano (o ano corrente é baixado de novo a cada 5 dias)."""
    ate = comum.ultimo_mes_fechado()
    saida = []
    for ano in range(INICIO // 100, ate // 100 + 1):
        dias = 5 if ano >= HOJE.year - (1 if HOJE.month <= 2 else 0) else 60
        arq = C / f"{tipo}_{ano}.bin"
        if not cache_valido(arq, dias):
            for i, url in enumerate(_arquivos_do_ano(tipo, ano)):
                _pedir(TRANSP + url, arq if i == 0 else C / f"{tipo}_{ano}_{i}.bin", 0)
        for extra in [arq] + sorted(C.glob(f"{tipo}_{ano}_*.bin")):
            if extra.exists():
                saida.append((ano, extra.read_bytes()))
    return saida


def _numero(v):
    if v is None or v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if not t or set(t) <= set("-–— "):
        return None
    try:
        return float(t.replace(".", "").replace(",", ".")) if "," in t else float(t)
    except ValueError:
        return None


def _mes_da_coluna(v, ano):
    if v is None or v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.year, v.month
    m = MESES_NOME.get(normalizar_nome(v))
    return (ano, m) if m else None


def alimentacao():
    """Vale-refeição/alimentação de cada vereador, mês a mês, e o abono de Natal (em dezembro)."""
    linhas, conferencia = [], []
    for ano, conteudo in _planilhas("alimentacao"):
        d = pd.read_excel(io.BytesIO(conteudo), header=None)
        cab = next(i for i in range(len(d)) if any(normalizar_nome(x) == "BENEFICIARIO" for x in d.iloc[i] if isinstance(x, str)))
        col_nome = next(j for j, x in enumerate(d.iloc[cab]) if isinstance(x, str) and normalizar_nome(x) == "BENEFICIARIO")
        colunas = {}
        for j, x in enumerate(d.iloc[cab]):
            if j == col_nome or x is None or (isinstance(x, float) and pd.isna(x)):
                continue
            if isinstance(x, str) and "NATAL" in normalizar_nome(x):
                colunas[j] = (ano, 12, "abono_natal")
            elif _mes_da_coluna(x, ano):
                colunas[j] = (*_mes_da_coluna(x, ano), "mensal")
        for i in range(cab + 1, len(d)):
            nome = d.iat[i, col_nome]
            if not isinstance(nome, str) or not nome.strip():
                continue
            if normalizar_nome(nome).startswith("TOTAL"):
                for j, (a, m, t) in colunas.items():
                    conferencia.append((a, m, t, _numero(d.iat[i, j]) or 0.0))
                break
            for j, (a, m, t) in colunas.items():
                v = _numero(d.iat[i, j])
                if v:
                    linhas.append({"ano": a, "mes": m, "nome": re.sub(r"\s+", " ", nome).strip(), "tipo": t, "valor": round(v, 2)})
    # se a pasta do ano tiver mais de uma planilha com o mesmo mês, vale a primeira da lista
    df = pd.DataFrame(linhas, columns=["ano", "mes", "nome", "tipo", "valor"]).drop_duplicates(["ano", "mes", "nome", "tipo"])
    for (a, m, t), total in {(a, m, t): v for a, m, t, v in reversed(conferencia)}.items():
        soma = df[(df.ano == a) & (df.mes == m) & (df.tipo == t)].valor.sum()
        if abs(soma - total) > 0.05:
            log(f"  Rio de Janeiro: alimentação {m:02d}/{a} ({t}) soma {soma:.2f}, mas a planilha diz {total:.2f}")
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "alimentacao.csv", index=False)
    log(f"  Rio de Janeiro: vale-alimentação, {len(df)} linhas ({len(set(zip(df.ano, df.mes)))} meses)")


def combustivel():
    """Cota de combustível usada por vereador e por mês (R$), a cota em litros e o preço de referência da ANP."""
    linhas, precos, conferencia = [], [], []
    for ano, conteudo in _planilhas("combustivel"):
        d = pd.read_excel(io.BytesIO(conteudo), header=None, sheet_name=0)
        pos = [(i, j) for i in range(len(d)) for j in range(d.shape[1]) if isinstance(d.iat[i, j], str) and normalizar_nome(d.iat[i, j]) == "VEREADORES"]
        if not pos:
            log(f"  Rio de Janeiro: combustível de {ano} sem a linha de cabeçalho (\"Vereadores\")")
            continue
        cab, col_nome = pos[0]
        colunas = {j: _mes_da_coluna(x, ano) for j, x in enumerate(d.iloc[cab]) if j > col_nome + 1 and _mes_da_coluna(x, ano)}
        ref = next((i for i in range(cab) if isinstance(d.iat[i, col_nome], str) and "A.N.P" in d.iat[i, col_nome].upper()), None)
        if ref is not None:
            for j, (a, m) in colunas.items():
                p = _numero(d.iat[ref, j])
                if p:
                    precos.append({"ano": a, "mes": m, "preco_anp": p})
        for i in range(cab + 1, len(d)):
            nome = d.iat[i, col_nome]
            if not isinstance(nome, str) or not nome.strip():
                continue
            if normalizar_nome(nome).startswith("TOTAL"):
                for j, (a, m) in colunas.items():
                    conferencia.append((a, m, _numero(d.iat[i, j]) or 0.0))
                break
            litros = _numero(d.iat[i, col_nome + 1])
            for j, (a, m) in colunas.items():
                v = _numero(d.iat[i, j])
                if v is not None:
                    linhas.append({"ano": a, "mes": m, "nome": nome.strip(), "litros": litros if litros is not None else "", "valor": round(v, 2)})
    df = pd.DataFrame(linhas, columns=["ano", "mes", "nome", "litros", "valor"]).drop_duplicates(["ano", "mes", "nome"])
    conferencia = [(a, m, v) for (a, m), v in {(a, m): v for a, m, v in reversed(conferencia)}.items()]
    for a, m, total in conferencia:
        soma = df[(df.ano == a) & (df.mes == m)].valor.sum()
        if abs(soma - total) > 0.05:
            log(f"  Rio de Janeiro: combustível {m:02d}/{a} soma {soma:.2f}, mas a planilha diz {total:.2f}")
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "combustivel.csv", index=False)
    pd.DataFrame(precos, columns=["ano", "mes", "preco_anp"]).drop_duplicates(["ano", "mes"]).to_csv(PASTA / "combustivel_preco_anp.csv", index=False)
    meses_com = sorted({(a, m) for a, m, t in conferencia if t})
    log(f"  Rio de Janeiro: combustível, {len(df)} linhas" + (f", até {meses_com[-1][1]:02d}/{meses_com[-1][0]}" if meses_com else ""))


# ---------------------------------------------------------------- coleta: servidores dos gabinetes (sem nomes)
def _cargo(cargo, vinculo):
    c = re.sub(r"\s+[A-D]$", "", re.sub(r"\s+", " ", cargo or "").strip())  # "ASSESSOR D" e "ASSESSOR" são o mesmo cargo
    if c:
        return comum.titulo(c).replace("Assessor-especial", "Assessor especial")
    v = normalizar_nome(vinculo)
    if v.startswith("REQUISITADO"):
        return "Servidor cedido por outro órgão (sem cargo em comissão)"
    return "Servidor efetivo da Câmara (sem cargo em comissão)"


def equipe():
    """Retrato de hoje: quantas pessoas e quais cargos em cada gabinete parlamentar (os nomes não são guardados)."""
    arq = PASTA / "equipe_cargos.csv"
    if arq.exists() and str(pd.read_csv(arq, nrows=1).data.iloc[0]) == HOJE.isoformat():
        return  # já coletado hoje
    verificar_prazo()
    t = _texto(_pedir(SERVIDORES, params={"ANOINGRESSO": "0"}))
    destino = re.search(r"location\s*=\s*'([^']+\.json)'", t)
    url = APLIC + destino.group(1) if destino else f"{APLIC}/scriptcase/tmp/Relacao_Servidores.json"
    dados = json.loads(_pedir(url).decode("utf-8-sig"))
    contagem = {}
    for x in dados:
        g = re.match(r"Gabinete Parlamentar N[º°o]\s*(\d+)", (x.get("Lotação") or "").strip())
        if g:
            k = (int(g.group(1)), _cargo(x.get("Cargo ou Função Gratificada"), x.get("Vínculo")))
            contagem[k] = contagem.get(k, 0) + 1
    del dados
    df = pd.DataFrame([{"data": HOJE.isoformat(), "gabinete": g, "cargo": c, "pessoas": n} for (g, c), n in sorted(contagem.items())])
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(arq, index=False)
    log(f"  Rio de Janeiro: {int(df.pessoas.sum()) if len(df) else 0} servidores em {df.gabinete.nunique() if len(df) else 0} gabinetes")


# ---------------------------------------------------------------- coleta: conferência de alguns contracheques
_RUBRICAS = {  # só os rendimentos brutos; líquido e descontos ficam de fora
    "RENDIMENTOS DO CARGO EFETIVO - CMRJ": "subsidio", "CARGO COMISSIONADO / FUNCAO GRATIFICADA": "cargo_comissionado",
    "EVENTUAIS/BENEFICIOS": "eventuais", "INDENIZACOES DE ALIMENTACAO/TRANSPORTES/SAUDE": "indenizacoes",
    "REEMBOLSO EDUCACAO": "reembolso_educacao", "ENCARGO ESPECIAL": "encargo_especial",
    "ENCARGO ESPECIAL DE ATIVIDADE PARLAMENTAR": "encargo_atividade_parlamentar", "ADICIONAL DE FERIAS": "adicional_ferias",
    "ABONO PERMANENCIA": "abono_permanencia", "DECIMO TERCEIRO SALARIO": "decimo_terceiro",
}


def _contracheque(nome, ano, mes):
    """Rendimentos brutos do contracheque de um vereador num mês, pelo nome civil (o mesmo caminho da página:
    ano, pesquisa, confirmação e contracheque). {"nao_encontrado": 1} se o nome não estiver na folha do mês; None se
    a página não abrir ou pedir o CPF.
    O sistema é em ISO-8859-1: as páginas são lidas e os campos são mandados nessa codificação."""
    ref = {"Referer": CONTRACHEQUE + "Ctrl_Pesquisa/", "Origin": APLIC}
    t = _texto(_pedir(CONTRACHEQUE + "Ctrl_Pesquisa/"), "latin1")
    init = re.search(r'name="script_case_init" value="(\d+)"', t).group(1)
    sessao = re.search(r'name="script_case_session" value="([^"]*)"', t).group(1)
    csrf = html_lib.unescape(re.search(r'name="csrf_token" value="([^"]*)"', t).group(1))
    a, m = str(ano), f"{mes:02d}"

    def ajax(funcao, args):
        dados = [("rs", funcao), ("rst", ""), ("rsrnd", str(int(time.time() * 1000)))] + [("rsargs[]", x.encode("latin1", "replace")) for x in args]
        return _texto(_pedir(CONTRACHEQUE + "Ctrl_Pesquisa/", metodo="POST", data=dados, headers=dict(ref, **{"X-Requested-With": "XMLHttpRequest"})), "latin1")
    # a página só aceita os meses do ano escolhido: atualiza a lista de meses e pesquisa (folha 1, "Normal")
    ajax("ajax_Ctrl_Pesquisa_refresh_cmp_ano", [a, "", "cmp_mes_#fld#_cmp_tipo_folha", init])
    r = ajax("ajax_Ctrl_Pesquisa_submit_form", [nome, a, m, "1", "1", "", "", "1", "", "alterar", "", "", "", init, csrf])
    red = re.search(r'\\"redirInfo\\":\{(.*?)\}', r)
    if not red:
        return {"nao_encontrado": 1} if "encontrado" in r else None  # "Nome não encontrado": fora da folha do mês

    def campo(k):
        x = re.search(r'\\"%s\\":\\"(.*?)\\"' % k, red.group(1))
        return x.group(1).replace("\\\\/", "/").replace("\\/", "/") if x else ""
    t = _texto(_pedir(APLIC + campo("action"), metodo="POST", headers=ref,
                      data={"nmgp_parms": campo("nmgp_parms"), "nmgp_url_saida": campo("nmgp_url_saida"),
                            "script_case_init": campo("script_case_init"), "script_case_session": sessao}), "latin1")
    if re.search(r"cpf", re.sub(r"Ctrl_Cpf", "", t), re.I) or "Fredir" not in t:
        log(f"  Rio de Janeiro: o contracheque de {nome} ({m}/{a}) pede o CPF ou não abriu; fica de fora")
        return None
    f = dict(re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t))
    acao = re.search(r'Fredir\.action\s*=\s*"([^"]+)"', t)
    t = _texto(_pedir(APLIC + (acao.group(1) if acao else "/scriptcase/sistemas/contracheque/Ctrl_ContraCheque/"), metodo="POST",
                      data={k: html_lib.unescape(v).encode("latin1", "replace") for k, v in f.items()},
                      headers=dict(ref, Referer=APLIC + campo("action"))), "latin1")
    corpo = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t[t.find("<body"):], flags=re.S)
    linhas = [l.strip() for l in html_lib.unescape(re.sub(r"<[^>]+>", "\n", corpo)).split("\n") if l.strip()]
    if normalizar_nome(nome) not in {normalizar_nome(l) for l in linhas}:
        return None
    saida = {"cargo": next((linhas[i + 1] for i, l in enumerate(linhas[:-1]) if l == "Cargo"), "")}
    for i, l in enumerate(linhas[:-1]):
        k = _RUBRICAS.get(normalizar_nome(l))
        v = re.fullmatch(r"R\$\s*(-?[\d.]+,\d{2})", linhas[i + 1])
        if k and v and k not in saida:
            saida[k] = float(v.group(1).replace(".", "").replace(",", "."))
    return saida


def _meses_a_conferir():
    """[(código, nome civil, ano, mês)] dos contracheques a baixar: os meses em que o vereador ficou só parte do mês
    no cargo (licenças, suplentes que entram e saem), o último mês inteiro no cargo de cada um desses vereadores (para
    saber se o nome dele está na folha) e a amostra fixa de meses inteiros (AMOSTRA_CONTRACHEQUES)."""
    if not ((PASTA / "vereadores.csv").exists() and (PASTA / "mandatos.csv").exists()):
        return []
    vdf = pd.read_csv(PASTA / "vereadores.csv", dtype=str).fillna("")
    mand = pd.read_csv(PASTA / "mandatos.csv", dtype=str).fillna("")
    civil = dict(zip(vdf.codigo, vdf.nome_civil))
    cod = {normalizar_nome(n): int(c) for c, n in civil.items() if n}
    alvo = []
    for c, g in mand.groupby("codigo"):
        ps = [(date.fromisoformat(i), date.fromisoformat(f) if f else None) for i, f in zip(g.inicio, g.fim)]
        inteiros = []
        for a, m in comum.meses(INICIO, comum.ultimo_mes_fechado()):
            d = comum.dias_no_mes(ps, a, m)
            if 0 < d < monthrange(a, m)[1]:
                alvo.append((int(c), civil.get(c, ""), a, m))
            elif d:
                inteiros.append((a, m))
        if inteiros and any(x[0] == int(c) for x in alvo):
            alvo.append((int(c), civil.get(c, ""), *inteiros[-1]))
    alvo += [(cod.get(normalizar_nome(n)), n, a, m) for n, a, m in AMOSTRA_CONTRACHEQUES if a * 100 + m <= comum.ultimo_mes_fechado()]
    return list(dict.fromkeys(x for x in alvo if x[0] and x[1]))


def contracheques():
    """Rendimentos brutos dos contracheques de _meses_a_conferir(), ou "nao_encontrado" quando a pesquisa da Câmara
    não acha o nome na folha do mês. Cada um é baixado uma vez só (fica no cache); descontos e líquido não são guardados."""
    linhas = []
    for codigo, nome, ano, mes in _meses_a_conferir():
        arq = C / "contracheque" / f"{ano}{mes:02d}_{normalizar_nome(nome).replace(' ', '_')}.json"
        if cache_valido(arq):
            d = json.loads(arq.read_text(encoding="utf-8"))
        else:
            erro = ""
            try:
                d = _contracheque(nome, ano, mes)
            except TempoEsgotado:
                raise
            except Exception as e:  # noqa: BLE001 — sem o contracheque, vale o subsídio pelos dias no cargo
                d, erro = None, f" ({e})"
            if d is None:
                log(f"  Rio de Janeiro: o contracheque de {nome} ({mes:02d}/{ano}) não abriu{erro}")
                continue
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        for k, v in d.items():
            if k != "cargo" and v:
                linhas.append({"ano": ano, "mes": mes, "codigo": codigo, "nome_civil": nome, "rubrica": k, "valor": v})
    df = pd.DataFrame(linhas, columns=["ano", "mes", "codigo", "nome_civil", "rubrica", "valor"]).sort_values(["codigo", "ano", "mes", "rubrica"])
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "contracheques.csv", index=False)
    outros = sorted(set(df.rubrica) - {"subsidio", "nao_encontrado"})
    # meses inteiros no cargo: o bruto tem de ser o subsídio (senão, avisa)
    mand = pd.read_csv(PASTA / "mandatos.csv", dtype=str).fillna("")
    per = {int(c): [(date.fromisoformat(i), date.fromisoformat(f) if f else None) for i, f in zip(g.inicio, g.fim)] for c, g in mand.groupby("codigo")}
    sub = df[df.rubrica == "subsidio"]
    inteiros = [r for r in sub.itertuples() if comum.dias_no_mes(per.get(int(r.codigo), []), int(r.ano), int(r.mes)) == monthrange(int(r.ano), int(r.mes))[1]]
    diferentes = [f"{r.nome_civil} {int(r.mes):02d}/{int(r.ano)} ({r.valor:.2f})" for r in inteiros if abs(r.valor - _subsidio(int(r.ano) * 100 + int(r.mes))) > 0.01]
    log(f"  Rio de Janeiro: {df[['codigo', 'ano', 'mes']].drop_duplicates().shape[0]} contracheques "
        f"({(df.rubrica == 'nao_encontrado').sum()} fora da folha do mês); nos {len(inteiros)} meses inteiros no cargo, "
        + (f"bruto diferente do subsídio em {', '.join(diferentes)}" if diferentes else "o bruto é o subsídio")
        + (f"; outros rendimentos: {', '.join(outros)}" if outros else ""))


def coletar():
    _pedir(f"{SITE}/includes_php/vereadores_atuais.php?imprimir=N", C / "atuais.html", 1, tentativas=1)  # fora do Brasil, para já aqui
    vereadores()
    gabinetes()
    alimentacao()
    combustivel()
    equipe()
    contracheques()


# ---------------------------------------------------------------- montagem
def _ler(nome, **kw):
    arq = PASTA / nome
    return pd.read_csv(arq, **kw) if arq.exists() else None


def montar(tipos):
    if not (PASTA / "vereadores.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    vdf = _ler("vereadores.csv", dtype=str).fillna("")
    mand = _ler("mandatos.csv", dtype=str).fillna("")
    alim = _ler("alimentacao.csv")
    comb = _ler("combustivel.csv")
    precos = _ler("combustivel_preco_anp.csv")
    gabs = _ler("gabinetes.csv", dtype=str)
    eqc = _ler("equipe_cargos.csv")
    tse = comum.candidatos_tse("RJ", "Rio de Janeiro")
    tse_civil = {normalizar_nome(n): r for n, r in zip(tse.nome, tse.to_dict("records"))}

    linhas_v, sem_tse = [], []
    for r in vdf.itertuples():
        t = tse_civil.get(normalizar_nome(r.nome_civil))
        if t is None:
            achado = comum.achar_no_tse(r.nome, tse)
            t = achado.to_dict() if achado is not None else None
        if t is None:
            sem_tse.append(r.nome)
        linhas_v.append({"codigo": int(r.codigo), "nome": r.nome, "nome_civil": comum.titulo(r.nome_civil) if r.nome_civil else (comum.titulo(t["nome"]) if t else ""),
                         "partido": r.partido or (t["partido"] if t else ""), "genero": t["genero"] if t else "",
                         "eleito": t["situacao"] if t else "", "pagina": r.pagina})
    ver = pd.DataFrame(linhas_v)
    if sem_tse:
        log(f"  Rio de Janeiro: sem correspondência no TSE: {', '.join(sem_tse)}")
    opcoes_civil = [(n, int(c)) for n, c in zip(vdf.nome_civil, vdf.codigo) if n] + [(n, int(c)) for n, c in zip(vdf.nome, vdf.codigo)]
    opcoes_nome = [(n, int(c)) for n, c in zip(vdf.nome, vdf.codigo)]
    por_civil = {normalizar_nome(n): int(c) for n, c in zip(vdf.nome_civil, vdf.codigo) if n}
    por_nome = {comum.chave_nome(n): int(c) for n, c in zip(vdf.nome, vdf.codigo)}

    def pelo_civil(n):
        return por_civil.get(normalizar_nome(n)) or por_nome.get(comum.chave_nome(n)) or comum.achar_parecido(n, opcoes_civil)

    def pelo_nome(n):
        return por_nome.get(comum.chave_nome(n)) or comum.achar_parecido(n, opcoes_nome)

    # períodos no cargo (datas da página de mandatos de cada vereador) e gabinete de cada um
    periodos = {}
    for r in mand.itertuples():
        periodos.setdefault(int(r.codigo), []).append((date.fromisoformat(r.inicio), date.fromisoformat(r.fim) if r.fim else None))
    gab_de, dono_hoje = _gabinetes(gabs, vdf, pelo_nome) if gabs is not None else ({}, {})
    mandatos_df = pd.DataFrame([{"codigo": c, "inicio": i.isoformat(), "fim": f.isoformat() if f else "", "gabinete": str(gab_de[c]) if c in gab_de else None}
                                for c, ps in periodos.items() for i, f in ps], columns=["codigo", "inicio", "fim", "gabinete"])

    # o que ganha: o subsídio (o contracheque do mês, quando foi baixado; senão, o subsídio pelos dias no cargo)
    # + o vale-alimentação publicado por nome
    folha = _folha()
    ganha_l = []
    for c, ps in periodos.items():
        for a, m in comum.meses(INICIO, ate):
            f = folha.get((c, a * 100 + m))
            dias = comum.dias_no_mes(ps, a, m)
            if f is not None and "nao_encontrado" in f and dias == monthrange(a, m)[1]:
                log(f"  Rio de Janeiro: {vdf.set_index('codigo').nome.get(str(c), c)} fora da folha em {m:02d}/{a}, mas no cargo o mês inteiro: vale o subsídio")
                f = None
            if f is not None:
                for rubrica, v in f.items():
                    categoria = _CATEGORIA_RUBRICA.get(rubrica, "outros_rendimentos")
                    if categoria:
                        ganha_l.append({"ano": a, "mes": m, "codigo": c, "categoria": categoria, "valor": v})
                continue
            if dias:
                ganha_l.append({"ano": a, "mes": m, "codigo": c, "categoria": "salario", "valor": round(_subsidio(a * 100 + m) * dias / monthrange(a, m)[1], 2)})
    fora_do_cargo = []
    if alim is not None and len(alim):
        alim = alim.assign(codigo=alim.nome.map(pelo_civil))
        sem = sorted(set(alim[alim.codigo.isna()].nome))
        if sem:
            log(f"  Rio de Janeiro: no vale-alimentação e não na legislatura: {', '.join(sem)}")
        for r in alim[alim.codigo.notna()].itertuples():
            c = int(r.codigo)
            if r.tipo == "mensal" and not comum.dias_no_mes(periodos.get(c, []), int(r.ano), int(r.mes)):
                fora_do_cargo.append((c, int(r.ano) * 100 + int(r.mes)))
            ganha_l.append({"ano": int(r.ano), "mes": int(r.mes), "codigo": c, "categoria": "auxilios", "valor": float(r.valor)})
    ganha = pd.DataFrame(ganha_l, columns=["ano", "mes", "codigo", "categoria", "valor"])
    if fora_do_cargo:
        nomes = ver.set_index("codigo").nome
        quem = {}
        for c, am in fora_do_cargo:
            quem.setdefault(nomes.get(c, str(c)), []).append(f"{am % 100:02d}/{am // 100}")
        log("  Rio de Janeiro: vale-alimentação em mês fora do cargo: " + "; ".join(f"{n} ({', '.join(ms)})" for n, ms in quem.items()))

    # cota de combustível (a "verba" do gabinete)
    despesas = None
    if comb is not None and len(comb):
        comb = comb.assign(codigo=comb.nome.map(pelo_nome))
        sem = sorted(set(comb[comb.codigo.isna()].nome))
        if sem:
            log(f"  Rio de Janeiro: no combustível e não na legislatura: {', '.join(sem)}")
        comb = comb[comb.codigo.notna() & (comb.valor > 0)]
        despesas = comb.assign(codigo=comb.codigo.astype(int), tipo="Combustível e manutenção de veículos", fornecedor="", cnpj_cpf="")[
            ["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]

    # equipe: retrato do dia, gabinete por gabinete, para quem ocupa o gabinete hoje
    cargos, equipe_em = None, ""
    if eqc is not None and len(eqc):
        cargos = eqc.assign(codigo=eqc.gabinete.map(lambda g: dono_hoje.get(int(g))))
        sem = sorted(set(cargos[cargos.codigo.isna()].gabinete))
        if sem:
            log(f"  Rio de Janeiro: gabinetes sem vereador identificado hoje: {', '.join(map(str, sem))}")
        cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})
        d = date.fromisoformat(str(eqc.data.iloc[0]))
        equipe_em = f"{d.month:02d}/{d.year}"

    notas = []
    ult_comb = int((comb.ano * 100 + comb.mes).max()) if comb is not None and len(comb) else None
    if ult_comb and ult_comb < ate:
        notas.append(f"A tabela de combustível publicada pela Câmara vai até {ult_comb % 100:02d}/{ult_comb // 100}: "
                     "os meses seguintes ainda não têm o combustível.")
    ult_alim = int((alim.ano * 100 + alim.mes).max()) if alim is not None and len(alim) else None
    if ult_alim and ult_alim < ate:
        notas.append(f"O vale-alimentação publicado vai até {ult_alim % 100:02d}/{ult_alim // 100}.")
    verba_mes = {}
    if precos is not None and len(precos):
        for a, g in precos.groupby("ano"):
            verba_mes[str(int(a))] = round(float(g.preco_anp.mean()) * 1000, 2)
        # mês em que a tabela traz a cota cheia (1.000 litros pelo preço da ANP) para todos: é o que foi publicado
        preco = {(int(a), int(m)): float(v) for a, m, v in zip(precos.ano, precos.mes, precos.preco_anp)}
        todo = _ler("combustivel.csv")
        for (a, m), g in (todo[todo.valor > 0].groupby(["ano", "mes"]) if todo is not None else []):
            cheia = round(preco.get((int(a), int(m)), 0) * 1000, 2)
            if len(g) >= 10 and cheia and g.valor.round(2).eq(cheia).all():
                notas.append(f"Em {int(m):02d}/{int(a)}, a tabela de combustível da Câmara traz a cota cheia ({_br(cheia)}) para todos os "
                             f"{len(g)} vereadores listados, inclusive quem ficou só um dia no cargo naquele mês: é o valor publicado.")
    ultimo = ate
    cfg = dict(CFG, ultimo_mes=ultimo, equipe_em=equipe_em, notas=CFG.get("notas", []) + notas, verba_mes=verba_mes)
    meta, pessoas = comum.montar(cfg, tipos, ver, mandatos_df, ganha=ganha, despesas=despesas, cargos=cargos)
    # o salário é o subsídio, igual para todos (só os meses de troca vêm do contracheque do mês): o site mostra
    # "salário igual para todos" e o subsídio de cada período, e não "salário pela folha de pagamento"
    meta["subsidio_folha"] = False
    return meta, pessoas


# rubrica do contracheque -> categoria do site. O vale-alimentação vem da planilha da Câmara (não aparece no
# contracheque): a linha de indenizações fica de fora para não contar duas vezes.
_CATEGORIA_RUBRICA = {"subsidio": "salario", "decimo_terceiro": "decimo_terceiro", "indenizacoes": None, "nao_encontrado": None}


def _br(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _folha():
    """{(código, AAAAMM): {rubrica: valor}} dos contracheques baixados. "Fora da folha" só vale para quem teve o nome
    achado em outro mês (senão, pode ser o nome escrito de outro jeito na folha)."""
    cc = _ler("contracheques.csv")
    if cc is None or not len(cc):
        return {}
    achados = set(cc[cc.rubrica != "nao_encontrado"].codigo.astype(int))
    nunca = sorted(set(cc[~cc.codigo.astype(int).isin(achados)].nome_civil))
    if nunca:
        log(f"  Rio de Janeiro: nome nunca achado na folha (vale o subsídio pelos dias no cargo): {', '.join(nunca)}")
    folha, negativos = {}, []
    for r in cc.itertuples():
        if int(r.codigo) not in achados:
            continue
        chave = (int(r.codigo), int(r.ano) * 100 + int(r.mes))
        folha.setdefault(chave, {})
        if float(r.valor) < 0:  # estorno de um pagamento que não aparece aqui (ex.: 13º devolvido na saída): fica de fora
            negativos.append(f"{r.nome_civil} {int(r.mes):02d}/{int(r.ano)} {r.rubrica} {float(r.valor):.2f}")
            continue
        folha[chave][r.rubrica] = float(r.valor)
    if negativos:
        log(f"  Rio de Janeiro: valores negativos no contracheque, fora da conta: {'; '.join(negativos)}")
    return folha


def _gabinetes(gabs, vdf, pelo_nome):
    """(gabinete de cada vereador, dono de cada gabinete hoje). O gabinete é do titular; o suplente em exercício usa o
    gabinete de quem ele substitui. A tabela da Câmara pode estar atrasada: quem está no cargo hoje e não aparece nela
    fica com o único gabinete cujo titular e suplente não estão no cargo."""
    no_cargo = {int(c) for c, x in zip(vdf.codigo, vdf.no_cargo_hoje) if str(x) == "True"}
    gab_de, titular, suplente = {}, {}, {}
    for r in gabs.itertuples():
        g = int(r.gabinete)
        t = pelo_nome(re.sub(r"\*", "", str(r.titular)).strip())
        s = pelo_nome(str(r.suplente).strip()) if isinstance(r.suplente, str) and r.suplente.strip() else None
        if t:
            titular[g] = t
            gab_de[t] = g
        else:
            log(f"  Rio de Janeiro: titular do gabinete {g} não identificado ({r.titular})")
        if s:
            suplente[g] = s
            gab_de.setdefault(s, g)
    dono = {}
    for g in set(titular) | set(suplente):
        if titular.get(g) in no_cargo:
            dono[g] = titular[g]
        elif suplente.get(g) in no_cargo:
            dono[g] = suplente[g]
    livres = sorted(g for g in set(titular) if g not in dono)
    sobram = sorted(no_cargo - set(dono.values()))
    if len(livres) == 1 and len(sobram) == 1:
        dono[livres[0]] = sobram[0]
        gab_de.setdefault(sobram[0], livres[0])
    elif livres or sobram:
        log(f"  Rio de Janeiro: gabinetes sem dono hoje {livres}; no cargo sem gabinete {sobram}")
    return gab_de, dono
