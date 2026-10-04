"""Assembleia Legislativa de Alagoas (ALE-AL): deputado estadual por deputado estadual.

Fontes:
- Folha: o Portal da Transparência da ALE-AL (https://transparencia.al.al.leg.br/, o link "Relação Nominal dos Servidores"
  de https://www.al.al.leg.br/transparencia/recursos-humanos; só abre de dentro do Brasil, então este robô roda no Mac).
  A lista de cada competência sai por letra (cada página leva uns 20 s para responder); o detalhe de cada pessoa
  (detalhar.php, pelo link que a lista dá) traz o cargo e os rendimentos: remuneração paradigma, vantagens pessoais,
  subsídio, indenizações, vantagens eventuais e a retenção pelo teto. Descontos pessoais e líquido não são guardados.
  Só os deputados (cargo "DEPUTADO ESTADUAL") são lidos no detalhe.
- Subsídio: Lei 9.056/2023 (R$ 34.774,64 desde fev/2025), para os meses sem folha.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
A VIAP (verba indenizatória) sai em PDF escaneado, um por deputado e mês, sem fornecedor, cada gabinete num modelo e muitas
vezes com o total corrigido à mão (para o limite do mês): a leitura por OCR, testada em jun/2025, conferiu com o total do
formulário em só 14 de 27 deputados. Os valores ficam de fora.
Quem está no cargo: quem está na folha do mês com o cargo de deputado estadual.
"""
import base64
import html as H
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "AL"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://transparencia.al.al.leg.br/"
PAG_VIAP = "https://www.al.al.leg.br/transparencia/orcamento-e-financas/viap-verba-indenizatoria-de-atividade-parlamentar"
PASTA = DADOS / "assembleias" / "al"
C = CACHE / "assembleias" / "al"
SIMULTANEOS = 3
EMPFIL_DEPUTADOS = "100105"  # o código que a lista dá aos deputados (conferido pelo cargo no detalhe)
CFG = {
    "cod": COD, "n": "Alagoas", "uf": UF, "casa": "Assembleia Legislativa de Alagoas", "vagas": 27, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da ALE-AL (rendimentos: subsídio, vantagens, indenizações e vantagens eventuais, menos a "
                     "retenção pelo teto), sem descontos pessoais."),
    "verba_nome": "Verba Indenizatória de Apoio à Atividade Parlamentar (VIAP)",
    "verba_regra": "Ressarcimento de despesas do mandato por categoria (Resoluções 531/2013 e 627/2019).",
    "verba_notas": ["A ALE-AL publica a VIAP de cada deputado e mês em formulário escaneado (imagem), cada gabinete num modelo, "
                    "sem fornecedor nem CNPJ e, em muitos meses, com o total corrigido à mão. A leitura automática dessas imagens "
                    "não é segura: os valores ficam de fora."],
    "pagina": "https://www.al.al.leg.br/processo-legislativo/parlamentares",
    "notas": ["Quem está no cargo: quem está na folha do mês com o cargo de deputado estadual.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": SITE, "verba": PAG_VIAP,
               "subsidio": "https://sapl.al.al.leg.br/media/sapl/public/normajuridica/2023/2750/lei_no_9.056_de_8_de_novembro_de_2023.pdf"},
}
COLS = ["ano", "mes", "folha", "matricula", "nome", "cargo", "rubrica", "valor"]
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _get(url, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, params=params, timeout=180)
            r.raise_for_status()
            dormir(1)
            return r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


def _competencias(t):
    """Opções do seletor: [("202609|EM", "09/2026 - FOLHA FECHAMENTO MENSAL")]."""
    s = re.search(r'<select[^>]*name="folha"[^>]*>(.*?)</select>', t, flags=re.S)
    return [(H.unescape(v), " ".join(H.unescape(n).split())) for v, n in re.findall(r'<option value="([^"]+)"[^>]*>([^<]*)</option>', s.group(1) if s else "")]


def _linhas(t):
    """Página da lista -> [(nome, link do detalhe, dados do link)]."""
    saida = []
    for href, nome in re.findall(r'href="(detalhar\.php\?d=[^"]+)"[^>]*>([^<]+)</a>', t):
        href = H.unescape(href)
        d = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("d", [""])[0]
        try:
            info = json.loads(base64.b64decode(d + "=" * (-len(d) % 4)))
        except Exception:  # noqa: BLE001
            info = {}
        saida.append((" ".join(H.unescape(nome).split()), href, info))
    return saida


_RENDIMENTOS = ["Remuneração Paradigma", "Vantagens Pessoais", "Subsídio / diferença de subsídio / função de confiança ou cargo comissionado",
                "Indenizações", "Vantagens Eventuais"]


def _detalhe(t):
    """Página do detalhe -> (cargo, [(rubrica, valor)]): só os rendimentos e a retenção pelo teto (negativa)."""
    x = " ".join(H.unescape(re.sub(r"<[^>]+>", " | ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())
    x = re.sub(r"(\|\s*)+", "| ", x)
    cargo = re.search(r"\|\s*([^|]+?)\s*·\s*Admissão", x)
    saida = []
    for rub in _RENDIMENTOS:
        m = re.search(re.escape(rub) + r"\s*\|\s*R\$\s*(-?[\d.]+,\d{2})", x)
        if m and num(m.group(1)):
            saida.append((rub, num(m.group(1))))
    teto = re.search(r"Retenção por Teto Constitucional\s*\|\s*R\$\s*(-?[\d.]+,\d{2})", x)
    if teto and num(teto.group(1)):
        saida.append(("Retenção por Teto Constitucional", -abs(num(teto.group(1)))))
    total = re.search(r"Total de Créditos\s*\|\s*R\$\s*(-?[\d.]+,\d{2})", x)
    if total and abs(sum(v for r, v in saida if v > 0) - num(total.group(1))) >= 0.01:
        log(f"  ALE-AL: rendimentos não somam o total de créditos ({cargo and cargo.group(1)})")
    return (cargo.group(1).strip() if cargo else ""), saida


def _letras_conhecidas(fol):
    """Iniciais dos nomes dos deputados já vistos e dos eleitos e suplentes de 2022 que têm VIAP publicada."""
    ini = {n[:1] for n in fol.nome.map(normalizar_nome) if n}
    tse = comum.tse_2022(UF)
    ini |= {normalizar_nome(v["nome"])[:1] for v in tse.values() if v["eleito"] == "eleito"}
    for nome in _nomes_viap():
        t = comum.achar(nome, tse)
        if t:
            ini.add(normalizar_nome(t["nome"])[:1])
    return ini


def _nomes_viap():
    """Nomes dos deputados com a VIAP publicada em cada ano (as pastas da página da VIAP)."""
    arq = C / "viap_nomes.json"
    if arq.exists() and time.time() - arq.stat().st_mtime < 20 * 86400:
        return json.loads(arq.read_text(encoding="utf-8"))
    nomes = set()
    for ano in range(INICIO // 100, int(time.strftime("%Y")) + 1):
        try:
            t = _get(f"{PAG_VIAP}/{ano}")
        except TempoEsgotado:
            raise
        except Exception:  # noqa: BLE001
            continue
        nomes |= {" ".join(H.unescape(n).split()) for n in re.findall(rf'href="{re.escape(PAG_VIAP)}/{ano}/[^"/]+"[^>]*>([^<]+)</a>', t)
                  if "Leia mais" not in n}
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(sorted(nomes), ensure_ascii=False), encoding="utf-8")
    return sorted(nomes)


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    (C / "listas").mkdir(parents=True, exist_ok=True)
    arq_c = C / "competencias.json"  # a página inicial leva uns 20 s: a lista de competências vale por 12 horas
    if arq_c.exists() and time.time() - arq_c.stat().st_mtime < 12 * 3600:
        comps = [tuple(x) for x in json.loads(arq_c.read_text(encoding="utf-8"))]
    else:
        try:  # de fora do Brasil o portal não responde: desiste logo (o site usa o que já está gravado)
            inicio = _get(SITE)
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"  ALE-AL: o portal da folha não abriu ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
            return
        comps = [(v, n) for v, n in _competencias(inicio) if v[:6].isdigit() and int(v[:6]) >= INICIO]
        if comps:
            arq_c.write_text(json.dumps(comps, ensure_ascii=False), encoding="utf-8")
    arq = PASTA / "folha_deputados.csv"
    fol = pd.read_csv(arq, dtype={"matricula": str}) if arq.exists() else pd.DataFrame(columns=COLS)
    if not comps:
        log("  ALE-AL: a página não trouxe as competências")
        return
    feitas = {f"{a * 100 + m}|{f}" for a, m, f in zip(fol.ano, fol.mes, fol.folha)}
    recentes = {v for v, _ in sorted(comps, reverse=True)[:2]}  # as duas mais recentes são lidas de novo (uma vez por semana)
    letras = _letras_conhecidas(fol)
    ultima = max(comps)[0]
    for valor, nome_comp in sorted(comps, reverse=True):
        lista_ok = C / "listas" / f"{valor.replace('|', '_')}.json"
        velho = not lista_ok.exists() or time.time() - lista_ok.stat().st_mtime > 6 * 86400
        if valor in feitas and not (valor in recentes and velho):
            continue
        # 1. a lista da competência, letra por letra (só as letras dos nomes de deputados; na mais recente, todas)
        vistas = json.loads(lista_ok.read_text(encoding="utf-8")) if lista_ok.exists() and not velho else {}
        faltam = [l for l in (LETRAS if valor == ultima else sorted(letras)) if l not in vistas]

        def letra(l, valor=valor):
            return l, [(n, h, i) for n, h, i in _linhas(_get(SITE + "index.php", {"folha": valor, "letra": l}))
                       if str(i.get("empfil")) == EMPFIL_DEPUTADOS and normalizar_nome(n)[:1] == l]  # letra sem nomes (X) devolve a lista do A
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for l, achados in ex.map(letra, faltam):
                vistas[l] = achados  # grava a cada letra: a próxima rodada continua de onde parou
                lista_ok.write_text(json.dumps(vistas, ensure_ascii=False), encoding="utf-8")
        novas = {n[:1] for l in vistas.values() for n, _, _ in l} - letras
        if novas:
            log(f"  ALE-AL: deputados com iniciais novas na lista de {valor}: {sorted(novas)}")
            letras |= novas
        # 2. o detalhe de cada deputado
        pessoas = [x for l in sorted(vistas) for x in vistas[l]]
        a, m = int(valor[:4]), int(valor[4:6])

        def det(item):
            nome, href, info = item
            cargo, itens = _detalhe(_get(SITE + href))
            return [{"ano": a, "mes": m, "folha": valor.split("|")[1], "matricula": str(info.get("mat", "")), "nome": nome, "cargo": cargo,
                     "rubrica": r, "valor": v} for r, v in itens]
        linhas = []
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for r in ex.map(det, pessoas):
                linhas.extend(r)
        if linhas:
            tp = valor.split("|")[1]
            fol = pd.concat([fol[~((fol.ano == a) & (fol.mes == m) & (fol.folha == tp))], pd.DataFrame(linhas)])
            gravar_csv(fol.sort_values(["ano", "mes", "folha", "nome", "rubrica"]), arq)
        log(f"  ALE-AL: {nome_comp}: {len(pessoas)} deputados na folha")


def _categoria(rubrica):
    u = normalizar_nome(rubrica)
    if u.startswith("SUBSIDIO"):
        return "salario"
    if "TETO" in u:
        return "salario"  # a retenção pelo teto sai do subsídio (como na Alece)
    if "INDENIZA" in u:
        return "auxilios"
    return "outros_rendimentos"


def _partido(civil, partidos):
    """Partido da candidatura de 2026 pelo nome civil; se o nome mudou (sobrenome a mais ou a menos), o único compatível."""
    if civil in partidos:
        return partidos[civil]
    achados = {p for n, p in partidos.items() if vc.compativel(n, civil) or vc.compativel(civil, n)}
    return achados.pop() if len(achados) == 1 else ""


def montar(tipos):
    arq = PASTA / "folha_deputados.csv"
    if not arq.exists():
        return None
    fol = pd.read_csv(arq, dtype={"matricula": str}).fillna("")
    fol = fol[fol.cargo.map(lambda c: "DEPUTAD" in normalizar_nome(c))].drop_duplicates(["ano", "mes", "folha", "matricula", "rubrica"])
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    fol["am"] = fol.ano.astype(int) * 100 + fol.mes.astype(int)
    ultimo_dado = int(fol[fol.folha == "EM"].am.max())
    fol = fol[fol.am <= ultimo_dado]
    meses_folha = sorted(set(fol[fol.folha == "EM"].am))
    ver, mandatos, ganha = [], [], []
    for civil, g in fol.groupby(fol.nome.map(normalizar_nome)):
        t = por_civil.get(civil) or comum.achar(civil, tse) or {}
        codigo = comum.codigo_de(civil, t)
        ver.append({"codigo": codigo, "nome": vc.titulo(t.get("urna") or civil), "nome_civil": vc.titulo(t.get("nome") or civil),
                    "partido": _partido(normalizar_nome(t.get("nome") or civil), partidos) or _partido(civil, partidos),
                    "genero": t.get("genero") or ("F" if feminino(civil) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses = sorted(set(g[(g.folha == "EM") & g.rubrica.map(lambda r: normalizar_nome(r).startswith("SUBSIDIO"))].am))
        if not meses:
            meses = sorted(set(g.am))
        per = vc.periodos_de_meses(meses, ultimo_dado, aberto=True)
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
        for r in g.itertuples():
            ganha.append({"ano": int(r.ano), "mes": int(r.mes), "codigo": codigo, "categoria": _categoria(r.rubrica), "valor": float(r.valor)})
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), inicio=max(INICIO, meses_folha[0] if meses_folha else INICIO))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]))
