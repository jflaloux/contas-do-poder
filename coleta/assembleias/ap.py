"""Assembleia Legislativa do Amapá (Alap): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alap; só abre de dentro do Brasil, então este robô roda no Mac):
- CEAP (Cota para o Exercício da Atividade Parlamentar): o que a página https://www.al.ap.gov.br/transparencia/pagina.php?pg=ceap
  usa: os gabinetes de cada mês (gabinete_ceap_json.php), o resumo do gabinete no mês por elemento de despesa
  (pagina.php?pg=ceap&acao=buscar) e o detalhe de cada elemento (ceap_exibir_detalhado.php: CNPJ, empresa, nota, valor).
- Folha: a "Consulta remuneratória de deputados" (pagina.php?pg=deputado_consulta) e a página de cada deputado no mês
  (pg=exibir_servidor): só os rendimentos (subsídio, GFE, auxílio-alimentação e outros); descontos e líquido não são guardados.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os gabinetes da CEAP do mês (o nome do gabinete é o do deputado). Quem está no cargo hoje: a lista de
parlamentares da página inicial da Alap (https://www.al.ap.gov.br/): a CEAP do último mês pode ainda não ter o gabinete de
quem prestou contas depois.
"""
import html as H
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "AP"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://www.al.ap.gov.br/transparencia/"
PASTA = DADOS / "assembleias" / "ap"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Amapá", "uf": UF, "casa": "Assembleia Legislativa do Amapá", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da Alap (rendimentos: subsídio, GFE, auxílio-alimentação e outros), sem descontos. A folha "
                     "não diz o que é a GFE. Nos meses no cargo sem a folha do deputado (a de fev/2026 não foi publicada), vale o subsídio "
                     "da lei; quem não aparece na consulta da folha fica com o subsídio da lei."),
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (CEAP)",
    "verba_regra": "Cota mensal para despesas do mandato, reembolsadas com nota fiscal.",
    "verba_notas": ["A Alap publica a CEAP por gabinete, mês e elemento de despesa, com o CNPJ, a empresa, a nota e o valor."],
    "pagina": "https://www.al.ap.leg.br/",
    "notas": ["Quem está no cargo: os gabinetes da CEAP de cada mês; quem está na folha como deputado sem gabinete na CEAP entra pelos meses na folha. "
              "Quem está no cargo hoje: a lista de parlamentares da página inicial da Alap.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": f"{SITE}pagina.php?pg=ceap", "folha": f"{SITE}pagina.php?pg=deputado_consulta"},
}


def _conserta(t):
    """Alguns nomes vêm com o UTF-8 lido duas vezes ("SERRÃ\\x83O" em vez de "SERRÃO")."""
    if "Ã" in t or "Â" in t:
        try:
            return t.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return t
    return t


def _pedir(metodo, caminho, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, SITE + caminho, timeout=90, **kw)
            r.raise_for_status()
            dormir(1)
            return r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _texto(t):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _gabinete(nome):
    """"ALDILENE SOUZA - PDT" -> ("ALDILENE SOUZA", "PDT")."""
    n = " ".join(_conserta(H.unescape(nome)).split())
    m = re.match(r"^(.*?)\s*-\s*([^-]+)$", n)
    return (m.group(1).strip(), m.group(2).strip()) if m else (n, "")


def _resumo(t):
    """Página do gabinete no mês -> [(elemento, valor, link do detalhe)]."""
    saida = []
    for linha in re.findall(r"<tr>(.*?)</tr>", t, flags=re.S):
        link = re.search(r'href="(ceap_exibir_detalhado\.php\?[^"]+)"', linha)
        cel = [_texto(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, flags=re.S)]
        if link and len(cel) >= 2 and re.search(r"\d,\d{2}$", cel[1]):
            saida.append((re.sub(r"^[\d.]+\s*-\s*", "", cel[0]).strip(), num(cel[1]), H.unescape(link.group(1))))
    return saida


def _detalhe(t):
    """Detalhe do elemento -> [(cnpj, empresa, objeto, nota, valor)]."""
    saida = []
    for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
        cel = [_texto(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, flags=re.S)]
        if len(cel) >= 4 and re.search(r"\d,\d{2}$", cel[-1]) and not cel[0].upper().startswith("TOTAL"):
            m = re.match(r"^([\d./*-]{11,})\s*-\s*(.*)$", cel[0])
            doc, empresa = (m.group(1), m.group(2)) if m else ("", cel[0])
            saida.append((vc.mascarar(doc), _conserta(empresa).strip(), cel[1], cel[2], num(cel[-1])))
    return saida


LISTA = "https://www.al.ap.gov.br/"


def _em_exercicio():
    """Nomes da lista de parlamentares da página inicial da Alap (quem está em exercício hoje)."""
    verificar_prazo()
    t = _sessao().get(LISTA, timeout=60).text
    return sorted({H.unescape(n) for n in re.findall(r'exibir_parlamentar&(?:amp;)?iddeputado=\d+" title="([^"]+)"', t)})


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # de fora do Brasil o portal não responde: desiste logo (o site usa o que já está gravado)
        _sessao().get(SITE + "pagina.php?pg=ceap", timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Alap: o portal não abriu ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
        return
    try:
        comum.gravar_em_exercicio(PASTA, _em_exercicio(), CFG["vagas"], LISTA)
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — sem a lista, fica a que já estava gravada
        log(f"  Alap: a lista de parlamentares não abriu ({type(e).__name__}); fica a já gravada")
    meses = _meses()
    arq_g, arq_v, arq_f = PASTA / "gabinetes.csv", PASTA / "ceap_notas.csv", PASTA / "folha_deputados.csv"
    velho = lambda arq: not arq.exists() or time.time() - arq.stat().st_mtime > 86400
    rev = velho(arq_v)
    gab = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "gabinete", "nome", "partido"])
    ceap = pd.read_csv(arq_v, dtype={"cnpj_cpf": str}) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "gabinete"])
    fol = pd.read_csv(arq_f) if arq_f.exists() else pd.DataFrame(columns=["ano", "mes", "nome"])
    # 1. gabinetes de cada mês
    feitos = set(zip(gab.ano, gab.mes))
    for am in meses:
        if (am // 100, am % 100) in feitos and (am < meses[-2] or not velho(arq_g)):
            continue
        t = _pedir("POST", "gabinete_ceap_json.php", data={"ano_verbaB": str(am // 100), "mes_verbaB": f"{am % 100:02d}"})
        novos = [{"ano": am // 100, "mes": am % 100, "gabinete": int(v), "nome": _gabinete(n)[0], "partido": _gabinete(n)[1]}
                 for v, n in re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', t)]
        if novos:
            gab = pd.concat([gab[~((gab.ano == am // 100) & (gab.mes == am % 100))], pd.DataFrame(novos)])
    gab.sort_values(["ano", "mes", "nome"]).to_csv(arq_g, index=False)
    # 2. CEAP de cada gabinete e mês (resumo e detalhe)
    feitos = set(zip(ceap.ano, ceap.mes, ceap.gabinete))
    pedir = [(int(a), int(m), int(g)) for a, m, g in zip(gab.ano, gab.mes, gab.gabinete)
             if (a, m, g) not in feitos or (a * 100 + m >= meses[-2] and rev)]

    def um(item):
        a, m, g = item
        t = _pedir("POST", "pagina.php?pg=ceap&acao=buscar", data={"ano_verbaB": str(a), "mes_verbaB": f"{m:02d}", "idgabineteB": str(g)})
        linhas = []
        for elemento, valor, link in _resumo(t):
            notas = _detalhe(_pedir("GET", link))
            soma = sum(x[4] for x in notas)
            for doc, empresa, objeto, nota, v in notas:
                linhas.append({"ano": a, "mes": m, "gabinete": g, "elemento": elemento, "cnpj_cpf": doc, "fornecedor": empresa, "nota": nota, "valor": v})
            if abs(valor - soma) >= 0.01:  # o que o detalhe não explica fica como linha do elemento, sem fornecedor
                linhas.append({"ano": a, "mes": m, "gabinete": g, "elemento": elemento, "cnpj_cpf": "", "fornecedor": "", "nota": "", "valor": round(valor - soma, 2)})
        return linhas or [{"ano": a, "mes": m, "gabinete": g, "elemento": "", "cnpj_cpf": "", "fornecedor": "", "nota": "", "valor": 0.0}]
    res = []
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for r in ex.map(um, pedir):
                res.append(r)
    finally:
        novos = pd.DataFrame([x for r in res for x in r])
        if len(novos):
            chave = set(zip(novos.ano, novos.mes, novos.gabinete))
            ceap = pd.concat([ceap[[k not in chave for k in zip(ceap.ano, ceap.mes, ceap.gabinete)]], novos])
            ceap.sort_values(["ano", "mes", "gabinete", "elemento"]).to_csv(arq_v, index=False)
        log(f"  Alap: CEAP de {len(res)} de {len(pedir)} gabinetes e meses pedida agora")
    # 3. folha dos deputados de cada mês
    feitos = set(zip(fol.ano, fol.mes))
    rev_f = velho(arq_f)
    res = []
    try:
        for am in meses:
            if (am // 100, am % 100) in feitos and (am < meses[-2] or not rev_f):
                continue
            t = _pedir("GET", "pagina.php", params={"pg": "deputado_consulta", "acao": "buscar", "mostrar_filtro": "1", "anoB": str(am // 100), "mesB": f"{am % 100:02d}"})
            links = [H.unescape(l) for l in re.findall(r'href="(pagina\.php\?pg=exibir_servidor[^"]*retorno=deputado)"', t)]

            def deputado(link, am=am):
                x = _texto(_pedir("GET", link))
                nome = re.search(r"nomeB=([^&]+)", link).group(1).strip()
                rem = re.search(r"Remuneração \(\+\)(.*?)Descontos \(-\)", x)
                eventual = re.search(r"Outras remunerações eventuais \(\+\)\s*R\$\s*([\d.]+,\d{2})", x)
                itens = re.findall(r"([A-ZÀ-Ú][A-ZÀ-Ú0-9 ./º-]+?)\s+R\$\s*([\d.]+,\d{2})", rem.group(1)) if rem else []
                linhas = [{"ano": am // 100, "mes": am % 100, "nome": nome, "rubrica": r.strip(), "valor": num(v)} for r, v in itens]
                if eventual and num(eventual.group(1)):
                    linhas.append({"ano": am // 100, "mes": am % 100, "nome": nome, "rubrica": "OUTRAS REMUNERAÇÕES EVENTUAIS", "valor": num(eventual.group(1))})
                return linhas
            with ThreadPoolExecutor(SIMULTANEOS) as ex:
                linhas = [x for r in ex.map(deputado, links) for x in r]
            if linhas:
                res.extend(linhas)
                fol = pd.concat([fol[~((fol.ano == am // 100) & (fol.mes == am % 100))], pd.DataFrame(linhas)])
    finally:
        if res:
            fol.sort_values(["ano", "mes", "nome", "rubrica"]).to_csv(arq_f, index=False)
        log(f"  Alap: folha, {len(res)} linhas novas")


_TIPOS = [(r"COMBUST", "Combustível"), (r"ALIMENTA", "Alimentação"), (r"IM[OÓ]VE", "Escritório (aluguel e contas)"),
          (r"GR[AÁ]FIC|EDITORIA", "Material gráfico (arte e impressão)"), (r"PUBLICIDADE|DIVULGA", "Divulgação do mandato"),
          (r"VIGIL|SEGURAN", "Segurança"), (r"VE[IÍ]CULO", "Aluguel de carros"), (r"LOCA[CÇ][AÃ]O DE BENS M[OÓ]VEIS", "Locação de bens móveis"),
          (r"EXPEDIENTE", "Material de escritório"), (r"CONSULTORIA|ASSESSORIA|T[EÉ]CNIC", "Consultorias e assessorias"),
          (r"TELEF|INTERNET|COMUNICA", "Telefone e internet"), (r"PASSAGE|LOCOMO", "Passagens")]


def _tipo(elemento):
    u = normalizar_nome(elemento)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(elemento)


def _categoria(rubrica):
    u = normalizar_nome(rubrica)
    if "SUBSIDIO" in u:
        return "salario"
    if "13" in u or "NATALIN" in u:
        return "decimo_terceiro"
    if "AUXILIO" in u or "ALIMENTA" in u:
        return "auxilios"
    return "outros_rendimentos"


# nome do gabinete na CEAP -> nome civil na folha, quando o TSE não resolve (conferidos pelos meses em que aparecem)
APELIDOS = {"R. NELSON VIEIRA": "ERRINELSON VIEIRA PIMENTEL", "KAKA BARBOSA": "JOSE CARLOS CARVALHO BARBOSA"}


def montar(tipos):
    arq_g = PASTA / "gabinetes.csv"
    if not arq_g.exists():
        return None
    gab = pd.read_csv(arq_g).fillna("")
    ceap = pd.read_csv(PASTA / "ceap_notas.csv", dtype={"cnpj_cpf": str}).fillna({"elemento": "", "cnpj_cpf": "", "fornecedor": ""}) \
        if (PASTA / "ceap_notas.csv").exists() else pd.DataFrame(columns=["ano", "mes", "gabinete", "elemento", "cnpj_cpf", "fornecedor", "valor"])
    fol = pd.read_csv(PASTA / "folha_deputados.csv") if (PASTA / "folha_deputados.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome", "rubrica", "valor"])
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    gab["am"] = gab.ano * 100 + gab.mes
    fol["am"] = fol.ano * 100 + fol.mes
    com_ceap = set(ceap[ceap.elemento != ""].ano * 100 + ceap[ceap.elemento != ""].mes)
    ultimo_dado = int(max([m for m in gab.am.unique() if m in com_ceap] or [int(gab.am.max())]))
    gab = gab[gab.am <= ultimo_dado]
    fol = fol[fol.am <= ultimo_dado]
    meses_folha = set(fol.am)
    pessoas = []  # (codigo, nome, civil, t, meses)
    civis_usados = set()
    for nome, g in gab.groupby("nome"):
        civil = APELIDOS.get(normalizar_nome(nome))
        t = (por_civil.get(civil) if civil else None) or comum.achar(nome, tse) or {}
        civil = civil or normalizar_nome(t.get("nome") or "")
        codigo = comum.codigo_de(nome, t)
        pessoas.append((codigo, vc.titulo(nome), civil, t, sorted(set(g.am)), list(g.gabinete.unique())))
        civis_usados.add(civil)
    # o nome da folha às vezes tem outra grafia que o do TSE ("QUEIROS" e "QUEIROZ"): vale o mais parecido
    import difflib
    canon = {}
    for n in set(fol.nome.map(normalizar_nome)):
        perto = difflib.get_close_matches(n, [c for c in civis_usados if c], n=1, cutoff=0.9)
        canon[n] = perto[0] if perto else n
    fol["civil"] = fol.nome.map(normalizar_nome).map(canon)
    # quem está na folha como deputado e não tem gabinete na CEAP (o presidente da Alap, por exemplo)
    for civil, g in fol.groupby("civil"):
        if civil in civis_usados:
            continue
        t = por_civil.get(civil) or {}
        pessoas.append((comum.codigo_de(civil, t), vc.titulo(t.get("urna") or civil), civil, t, sorted(set(g.am)), []))
    ver, mandatos, cod_gab, ganha = [], [], {}, []
    folha_de = {n: g for n, g in fol.groupby("civil")}
    subsidio = lambda am: [v for d, v in CFG["subsidio"] if d <= am][-1]
    for codigo, nome, civil, t, meses_p, gabs in pessoas:
        for c in gabs:
            cod_gab[int(c)] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome") or civil or nome),
                    "partido": partidos.get(normalizar_nome(t.get("nome") or civil), ""),
                    "genero": t.get("genero") or ("F" if feminino(civil or nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        per = comum.periodos(meses_p, ultimo_dado, ultimo, folga=1)
        fim = max(meses_p)
        if fim < ultimo_dado:
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
        fg = folha_de.get(civil)
        if fg is None:
            continue  # sem folha: o site usa o subsídio da lei
        for r in fg.itertuples():
            ganha.append({"ano": r.ano, "mes": r.mes, "codigo": codigo, "categoria": _categoria(r.rubrica), "valor": r.valor})
        # mês no cargo sem a folha do deputado (fev/2026 não saiu para ninguém): o subsídio da lei
        for am in meses_p:
            if am not in set(fg.am):
                ganha.append({"ano": am // 100, "mes": am % 100, "codigo": codigo, "categoria": "salario", "valor": subsidio(am)})
    d = ceap[(ceap.elemento != "") & (ceap.valor.abs() >= 0.005)]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.gabinete.map(cod_gab), "tipo": d.elemento.map(_tipo),
                         "fornecedor": d.fornecedor, "cnpj_cpf": d.cnpj_cpf, "valor": d.valor}).dropna(subset=["codigo"])
    lista, atual = comum.ler_em_exercicio(PASTA), None  # quem está no cargo hoje; a CEAP e a folha dizem desde quando
    if lista:
        atual = comum.casar_em_exercicio(lista, ver, UF)
        mandatos = comum.aplicar_hoje(mandatos, atual, ultimo_dado, folga=1)
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), fora_hoje=comum.fora_hoje(atual))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]), despesas=desp)
