"""Câmara Municipal de João Pessoa: vereador por vereador.

Fontes (Portal da Transparência da Câmara, sem cadastro; abre de fora do Brasil, conferido em 08/10/2026; robots.txt só
proíbe /wp-admin/):
- Folha mensal, nome por nome (Recursos Humanos > Pessoal): POST https://joaopessoa.pb.leg.br/transparencia/recursos-humanos/
  com data=MMAAAA. Traz nome, cargo, regime, data de admissão e o valor do mês ("vantagens"), sem CPF e sem a lotação.
  Guardamos só as linhas de regime eletivo (os vereadores e o presidente da Câmara). Quem estava no cargo em cada mês:
  quem aparece na folha do mês.
- Verba indenizatória: https://joaopessoa.pb.leg.br/transparencia/verbas-indenizatorias/ (uma tabela com mês, vereador,
  serviço e valor; os contratos e as notas ficam em PDF, que não lemos: sem fornecedor nem CNPJ).
- Quem está em exercício hoje: a lista de vereadores da Câmara, https://joaopessoa.pb.leg.br/vereadores/ (nome
  parlamentar, partido e foto).
- Subsídio: Lei 14.702/2022, R$ 26.000 (o presidente, R$ 32.000), limitado a 75% do subsídio de deputado estadual
  (R$ 24.754,79 em jan/2025).
- Nome civil, nome de urna, partido (quando a lista da Câmara não tem) e gênero: TSE (eleição de 2024).

Plano de queda (fonte que só tem um caminho; escrito em 08/10/2026, também em dados/referencia/plano-de-queda.json):
- Folha ou verba fora do ar ou com outro formato: o robô mantém o que já gravou (gravação segura) e o site fica até o
  último mês lido. A reserva é automática: o TCE-PB tem a folha da Câmara de João Pessoa, vereador por vereador
  (site/dados/interior/pb.json, RESERVAS_TCE em coleta/situacao.py); se a fonte própria falhar ou ficar 2 meses atrás,
  a página da cidade passa a mostrar o valor do TCE-PB, com aviso.
- Lista de vereadores fora do ar: fica a última lista gravada (em_exercicio.csv); sem lista, o "no cargo" sai da folha.
- Conserto só se couber em cerca de 1 hora; passou disso, a fonte vai para onde.CONGELADAS.
"""
import html as html_lib
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..assembleias import comum as acomum
from . import comum

COD = 2507507
INICIO = 202501
SITE = "https://joaopessoa.pb.leg.br"
FOLHA = f"{SITE}/transparencia/recursos-humanos/"
VERBA = f"{SITE}/transparencia/verbas-indenizatorias/"
LISTA = f"{SITE}/vereadores/"
LEI = f"{SITE}/transparencia/arquivos/lei_14_702_2022_subsidio_dos_vereadores_2025_a_2028.pdf"
PASTA = DADOS / "municipios" / "joao_pessoa"
C = CACHE / "cmjp"
REBAIXAR = 3  # os últimos meses da folha são baixados de novo (a Câmara ainda pode acertar)
VAGAS = 29
CFG = {
    "cod": COD, "n": "João Pessoa", "uf": "PB", "casa": "Câmara Municipal de João Pessoa", "vagas": VAGAS, "inicio": INICIO,
    # Lei 14.702/2022: R$ 26.000, limitado a 75% do subsídio de deputado estadual (R$ 33.006,39 em jan/2025)
    "subsidio": [[202501, 24754.79], [202502, 26000.0]],
    "salario_nota": ("Valor do mês na folha da Câmara (subsídio de R$ 26.000 pela Lei 14.702/2022; o presidente da Câmara "
                     "recebe R$ 32.000). A folha publicada não separa 13º, férias nem descontos."),
    "verba_nome": "Verba indenizatória", "verba_mes": {},
    "verba_regra": "Ressarcimento de serviços contratados para o mandato (assessoria, divulgação, aluguel de sala), com contrato e nota.",
    "verba_notas": ["A Câmara publica um valor por vereador e mês, com o serviço como ela descreve; os contratos e as notas ficam em PDF, por isso não há fornecedor nem CNPJ aqui."],
    "equipe_nota": None,
    "credito_foto": "Câmara Municipal de João Pessoa", "pagina": LISTA,
    "notas": ["Quem estava no cargo em cada mês: quem aparece na folha da Câmara no mês. Quem está em exercício hoje: a lista de vereadores da Câmara.",
              "A folha lista os cargos de gabinete de vereador, mas não diz de qual gabinete cada pessoa é: a equipe de cada vereador não aparece aqui."],
    "fontes": {"folha": FOLHA, "verba": VERBA, "lista": LISTA, "subsidio": LEI},
}


def _pedir(metodo, url, arquivo=None, dias=None, **kw):
    """Texto da resposta, com novas tentativas; guarda no cache (arquivo) e usa o cache se ainda vale."""
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_text(encoding="utf-8")
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=120, **kw)
            r.raise_for_status()
            texto = r.text
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(10 + 10 * tentativa)
    dormir(1.5)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(texto, encoding="utf-8")
    return texto


def _txt(c):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", c or ""))).strip()


def _valor(t):
    t = re.sub(r"[^\d,]", "", str(t or ""))
    return float(t.replace(",", ".")) if t else 0.0


# ---------------------------------------------------------------- coleta
def _folha_mes(a, m, dias):
    """Linhas de regime eletivo da folha de um mês (lista vazia se o mês ainda não saiu)."""
    t = _pedir("POST", FOLHA, C / f"folha_{a}{m:02d}.html", dias, data={"data": f"{m:02d}{a}"})
    corpo = t[t.find("<tbody>"):t.find("</tbody>")] if "<tbody>" in t else ""
    saida = []
    for linha in re.findall(r"<tr>(.*?)</tr>", corpo, re.S):
        cel = [_txt(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]
        if len(cel) < 7 or "ELETIVO" not in cel[3].upper():
            continue
        saida.append({"ano": a, "mes": m, "nome": cel[0], "cargo": cel[1], "regime": cel[3], "admissao": cel[5], "valor": _valor(cel[6])})
    return saida


def folha():
    """Folha dos vereadores, mês a mês. Os meses que já estão em dados/municipios/joao_pessoa/ não são baixados de novo
    (só os REBAIXAR últimos)."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq = PASTA / "folha.csv"
    velha = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["ano", "mes"])
    feitos = set(velha.ano * 100 + velha.mes) if len(velha) else set()
    linhas = []
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        novas = _folha_mes(a, m, 5 if am > recentes else None)
        if not novas and am in feitos:  # o mês sumiu da consulta: fica o que estava gravado
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        linhas += novas
    df = pd.DataFrame(linhas, columns=["ano", "mes", "nome", "cargo", "regime", "admissao", "valor"])
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df.sort_values(["ano", "mes", "nome"]), arq)
    ult = int((df.ano * 100 + df.mes).max()) if len(df) else None
    log(f"  João Pessoa: folha com {len(df)} linhas de vereadores, até {ult}")


def verba():
    """A tabela da verba indenizatória (uma página só, com todos os meses)."""
    t = _pedir("GET", VERBA)
    linhas = []
    for linha in re.findall(r'<tr><td class="column-1">(.*?)</tr>', t, re.S):
        cel = dict(re.findall(r'<td class="column-(\d)">(.*?)(?=<td class="column-|$)', '<td class="column-1">' + linha, re.S))
        mes = re.match(r"(\d{2})/(\d{4})", _txt(cel.get("1")))
        if not mes:
            continue
        a, m = int(mes.group(2)), int(mes.group(1))
        if a * 100 + m < INICIO:
            continue
        linhas.append({"ano": a, "mes": m, "nome": _txt(cel.get("2")), "servico": _txt(cel.get("3")), "valor": _valor(_txt(cel.get("4")))})
    df = pd.DataFrame(linhas, columns=["ano", "mes", "nome", "servico", "valor"])
    if not len(df):
        log("  João Pessoa: a tabela da verba veio vazia; fica o que estava gravado")
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df.sort_values(["ano", "mes", "nome"], kind="stable"), PASTA / "verba.csv")
    log(f"  João Pessoa: verba com {len(df)} linhas, até {int((df.ano * 100 + df.mes).max())}")


def lista():
    """Nome parlamentar, partido, foto e página de quem está em exercício (a lista de vereadores da Câmara)."""
    t = _pedir("GET", LISTA)
    linhas = []
    for bloco in re.split(r'<div class="vereador-info">', t)[1:]:
        foto = re.search(r'<img src="([^"]+)"', bloco)
        pagina = re.search(r'<a href="([^"]+/tag/[^"]+)"', bloco)
        dados = re.search(r'<div class="vereador-dados">\s*<span>(.*?)</span>\s*<span>(.*?)</span>', bloco, re.S)
        if not dados:
            continue
        linhas.append({"nome": _txt(dados.group(1)), "partido": _txt(dados.group(2)),
                       "foto": foto.group(1) if foto else "", "pagina": pagina.group(1) if pagina else ""})
    df = pd.DataFrame(linhas, columns=["nome", "partido", "foto", "pagina"]).drop_duplicates("nome")
    if not 0.8 * VAGAS <= len(df) <= 1.2 * VAGAS:  # página quebrada: não tira ninguém do cargo nem põe ninguém
        log(f"  João Pessoa: a lista de vereadores veio com {len(df)} nomes para {VAGAS} vagas; fica a que estava gravada")
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df, PASTA / "site_vereadores.csv")
    acomum.gravar_em_exercicio(PASTA, list(df.nome), VAGAS, LISTA)
    log(f"  João Pessoa: {len(df)} vereadores na lista da Câmara")


def coletar():
    try:  # se o portal não responder, desiste logo: o site usa o que já está gravado
        _sessao().get(SITE, timeout=30).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  João Pessoa: o portal da Câmara não abriu ({type(e).__name__}); fica o que já estava gravado")
        raise
    lista()
    folha()
    verba()


# ---------------------------------------------------------------- montagem
def _tipo(servico):
    """O serviço como a Câmara escreve, em letras normais ("Assessoria jurídica e marketing"). Um serviço só ganha o nome
    curto comum a todas as cidades; vários juntos ficam como a Câmara escreveu, para não esconder nenhum."""
    s = re.sub(r"\s+", " ", servico or "").strip(" .;-")
    if not s:
        return "Não informado"
    if not re.search(r",| E |/|;", s.upper()):
        return comum.tipo_curto(s)
    return s[:1].upper() + s[1:].lower()


def _subsidio(am):
    v = 0.0
    for de, valor in CFG["subsidio"]:
        if am >= de:
            v = valor
    return v


def _acertar_periodos(mandatos, fol, ultimo, atual):
    """Os períodos saem dos meses na folha; aqui ganham o dia certo e o "hoje":
    - começo no meio do mês: a data de admissão da folha;
    - saída no meio do mês: o valor do mês dividido pelo subsídio dá os dias pagos (R$ 4.193,55 em ago/2026 = 5 dias);
    - quem está na lista de hoje da Câmara e não tem período aberto (voltou de licença depois do último mês da folha):
      um período novo começa no mês seguinte ao último da folha;
    - quem tem período aberto e não está na lista de hoje: o período fecha no último mês da folha (ou no dia pago)."""
    from calendar import monthrange
    fol = fol.assign(am=fol.ano * 100 + fol.mes)
    adm = {c: pd.to_datetime(g.admissao, format="%d/%m/%Y", errors="coerce").max() for c, g in fol.groupby("codigo")}

    def dia_da_saida(cod, aaaamm):
        g = fol[(fol.codigo == cod) & (fol.am == aaaamm)]
        a, m = divmod(aaaamm, 100)
        sub, n = _subsidio(aaaamm), monthrange(a, m)[1]
        if len(g) and "VEREADOR" in g.cargo.iloc[0].replace(" ", "").upper() and sub and float(g.valor.sum()) < 0.97 * sub:
            return f"{a}-{m:02d}-{max(1, min(n, round(float(g.valor.sum()) / sub * n))):02d}"
        return f"{a}-{m:02d}-{n:02d}"

    for p in mandatos:
        d = adm.get(p["codigo"])
        if d is not None and not pd.isna(d) and d.strftime("%Y-%m") == p["inicio"][:7] and d.day > 1:
            p["inicio"] = d.strftime("%Y-%m-%d")
        if p["fim"]:
            p["fim"] = dia_da_saida(p["codigo"], int(p["fim"][:7].replace("-", "")))
    if not atual:
        return mandatos
    seguinte = comum.mes_seguinte(ultimo)
    for cod, hoje in atual.items():
        ps = [p for p in mandatos if p["codigo"] == cod]
        aberto = [p for p in ps if not p["fim"]]
        if hoje and ps and not aberto:
            mandatos.append({"codigo": cod, "inicio": f"{seguinte // 100}-{seguinte % 100:02d}-01", "fim": ""})
        elif not hoje and aberto:
            for p in aberto:
                p["fim"] = dia_da_saida(cod, ultimo)
    return mandatos


def montar(tipos):
    arq = PASTA / "folha.csv"
    if not arq.exists():
        return None
    fol = pd.read_csv(arq).fillna({"cargo": "", "regime": "", "admissao": ""})
    if not len(fol):
        return None
    vb = pd.read_csv(PASTA / "verba.csv").fillna({"servico": ""}) if (PASTA / "verba.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome", "servico", "valor"])
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else pd.DataFrame(columns=["nome", "partido", "foto", "pagina"])
    tse = comum.candidatos_tse("PB", "João Pessoa")
    por_civil = [(n, i) for i, n in enumerate(tse.nome)] if len(tse) else []

    def no_tse(nome_civil):
        i = comum.achar_parecido(nome_civil, por_civil, 0.9) if por_civil else None
        return tse.iloc[i].to_dict() if i is not None else None

    # quem é quem: o nome civil da folha (e da verba) casa com o TSE; o código é o SQ da candidatura (como em Boa Vista)
    codigos, info = {}, {}
    for nome in sorted(set(fol.nome)):
        t = no_tse(nome)
        cod = int(t["sq"]) if t else acomum.codigo_de(nome, None)
        codigos[normalizar_nome(nome)] = cod
        info.setdefault(cod, {"t": t, "nome": nome})
    da_folha = [(n, codigos[normalizar_nome(n)]) for n in sorted(set(fol.nome))]
    for nome in sorted(set(vb.nome)):
        k = normalizar_nome(nome)
        if k in codigos:
            continue
        t = no_tse(nome)
        # a verba escreve o nome com acentos e às vezes de outro jeito: primeiro pelo TSE, depois pelos nomes da folha
        cod = int(t["sq"]) if t is not None and int(t["sq"]) in info else comum.achar_parecido(nome, da_folha, 0.9)
        if cod is None:
            cod = int(t["sq"]) if t is not None else acomum.codigo_de(nome, None)
            info.setdefault(cod, {"t": t, "nome": nome})
        codigos[k] = cod
    fol["codigo"] = fol.nome.map(lambda n: codigos[normalizar_nome(n)])
    vb["codigo"] = vb.nome.map(lambda n: codigos[normalizar_nome(n)])
    sem_tse = sorted({v["nome"] for v in info.values() if v["t"] is None})
    if sem_tse:
        log(f"  João Pessoa: sem candidatura no TSE de 2024: {', '.join(sem_tse)}")
    so_verba = sorted(set(vb.codigo) - set(fol.codigo))
    if so_verba:
        log(f"  João Pessoa: na verba e não na folha: {', '.join(info[c]['nome'] for c in so_verba)}")

    # a lista da Câmara (nome parlamentar) casa com o nome de urna do TSE; dela vêm a foto, o partido e o "em exercício"
    cod_por_urna = {}
    for c, v in info.items():
        if v["t"] is not None:
            cod_por_urna[c] = v["t"]["nome_urna"]
    opcoes = [(u, c) for c, u in cod_por_urna.items()] + [(info[c]["nome"], c) for c in info]
    site_cod, faltam = {}, []
    for r in site.itertuples():
        c = comum.achar_parecido(r.nome, opcoes, 0.9)
        if c is None:
            faltam.append(r)
        else:
            site_cod[c] = r
    ultimo = int((fol.ano * 100 + fol.mes).max())
    # segunda volta, mais tolerante, só entre quem estava na folha do último mês e ainda não casou ("Guguinha Moov Jampa"
    # na lista x "Guga Moov Jampa" no TSE)
    livres = set(fol[(fol.ano * 100 + fol.mes) == ultimo].codigo) - set(site_cod)
    for r in faltam:
        c = comum.achar_parecido(r.nome, [(n, c) for n, c in opcoes if c in livres], 0.8)
        if c is None:
            log(f"  João Pessoa: na lista da Câmara e não na folha: {r.nome}")
            continue
        site_cod[c] = r
        livres.discard(c)
    ate = comum.ultimo_mes_fechado()
    nomes_lista = acomum.ler_em_exercicio(PASTA)
    atual = {c: (c in site_cod) for c in info} if nomes_lista else None

    ver, mandatos, fotos = [], [], []
    for c in sorted(set(fol.codigo)):
        v, s = info[c], site_cod.get(c)
        t = v["t"]
        nome = s.nome if s is not None else (comum.titulo(t["nome_urna"]) if t else comum.titulo(v["nome"]))
        if s is not None and s.foto:
            fotos.append((c, s.foto))
        ver.append({"codigo": c, "nome": nome, "nome_civil": comum.titulo(t["nome"]) if t else comum.titulo(v["nome"]),
                    "partido": (s.partido if s is not None and s.partido else "") or (t["partido"] if t else ""),
                    "genero": t["genero"] if t else "", "eleito": t["situacao"] if t else "",
                    "pagina": (s.pagina if s is not None and s.pagina else "") or LISTA})
        g = fol[fol.codigo == c]
        for i, f in comum.periodos_de_meses(g.ano * 100 + g.mes, ultimo):
            mandatos.append({"codigo": c, "inicio": i, "fim": f})
    mandatos = _acertar_periodos(mandatos, fol, ultimo, atual)
    comum.fotos(COD, fotos)
    ganha = pd.DataFrame({"ano": fol.ano, "mes": fol.mes, "codigo": fol.codigo, "categoria": "salario", "valor": fol.valor})
    desp = pd.DataFrame({"ano": vb.ano, "mes": vb.mes, "codigo": vb.codigo, "tipo": vb.servico.map(_tipo),
                         "fornecedor": "", "cnpj_cpf": "", "valor": vb.valor})
    # a verba sai uns meses depois da folha: os meses depois da última verba publicada não contam na média da verba
    ultimo_vb = int((vb.ano * 100 + vb.mes).max()) if len(vb) else None
    notas = list(CFG["notas"])
    if ultimo_vb and ultimo_vb < min(ate, ultimo):
        notas.append(f"A verba indenizatória está publicada até {ultimo_vb % 100:02d}/{ultimo_vb // 100}; os meses seguintes ainda não têm verba.")
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo), subsidio_folha=True, verba_ate=ultimo_vb, notas=notas)
    return comum.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=ganha, despesas=desp)
