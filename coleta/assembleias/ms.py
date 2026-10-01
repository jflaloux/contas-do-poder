"""Assembleia Legislativa de Mato Grosso do Sul (Alems): deputado estadual por deputado estadual.

Fontes:
- Cota para o Exercício da Atividade Parlamentar (CEAP), nota por nota (categoria, CNPJ, fornecedor, documento, data,
  valor e link do comprovante), um CSV por ano: https://transparencia2.al.ms.gov.br/ceap/notas/exportar-csv?ano=AAAA
  (Portal da Transparência da Alems, https://transparencia2.al.ms.gov.br/ceap). CPF de pessoa física fica mascarado.
- Subsídio: Lei 6.016/2022 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, partido, gênero e eleito/suplente: TSE (eleição de 2022). A Alems não publica a lista de deputados em
  dados abertos: quem esteve no cargo em cada mês sai dos meses com notas da CEAP.
"""
import csv
import io
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "MS"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
CSV = "https://transparencia2.al.ms.gov.br/ceap/notas/exportar-csv"
PASTA = DADOS / "assembleias" / "ms"
C = CACHE / "assembleias" / "ms"
MESES = {normalizar_nome(m): i for i, m in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
                                                      "Outubro", "Novembro", "Dezembro"], 1)}
CFG = {
    "cod": COD, "n": "Mato Grosso do Sul", "uf": UF, "casa": "Assembleia Legislativa de Mato Grosso do Sul", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 6.016/2022), proporcional aos meses no cargo. A folha da Alems sai em PDF, um por "
                     "deputado, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (CEAP)",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal; cada nota tem o comprovante publicado.",
    "verba_notas": ["As notas entram no mês de referência da prestação de contas."],
    "pagina": "https://transparencia2.al.ms.gov.br/ceap",
    "notas": ["A Alems não publica a lista de deputados em dados abertos: quem estava no cargo em cada mês sai das notas da CEAP "
              "(um mês sem notas entre dois com notas conta como mês no cargo).",
              "Partido: o da candidatura de 2026 no TSE (depois da janela partidária). Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": "https://transparencia2.al.ms.gov.br/ceap", "subsidio": "https://www.transparencia.al.ms.gov.br/uploads/ac633cbeae1cad5ef3590fd62b32d828.pdf"},
}


def _baixar(ano, dias):
    arq = C / f"ceap_{ano}.csv"
    if arq.exists() and time.time() - arq.stat().st_mtime < dias * 86400:
        return arq.read_bytes()
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(CSV, params={"ano": ano}, timeout=300)
            r.raise_for_status()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(r.content)
    dormir(3)
    return r.content


def _nome(dep):
    return re.sub(r"^\s*DEP\.?\s*", "", str(dep or ""), flags=re.I).strip()


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    ano_hoje = int(time.strftime("%Y"))
    linhas = []
    for ano in range(INICIO // 100, ano_hoje + 1):
        texto = _baixar(ano, 3 if ano >= ano_hoje - 1 else 3650).decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(texto), delimiter=";"):
            mes = MESES.get(normalizar_nome(r.get("Mês") or ""))
            if not mes:
                continue
            linhas.append({"ano": int(r["Ano"]), "mes": mes, "deputado": _nome(r["Deputado"]), "tipo": (r.get("Categoria") or "").strip(),
                           "fornecedor": (r.get("Fornecedor") or "").strip(), "cnpj_cpf": vc.mascarar(r.get("CPF/CNPJ") or ""),
                           "documento": (r.get("Documento") or "").strip(), "data": (r.get("Emissão") or "").strip(),
                           "valor": comum_num(r.get("Valor (R$)")), "comprovante": (r.get("Comprovante") or "").strip()})
    notas = pd.DataFrame(linhas)
    notas = notas[notas.ano * 100 + notas.mes >= INICIO]
    notas.sort_values(["ano", "mes", "deputado", "data", "fornecedor"]).to_csv(PASTA / "ceap_notas.csv", index=False)
    log(f"  Alems: {len(notas)} notas da CEAP de {notas.deputado.nunique()} deputados desde {INICIO % 100:02d}/{INICIO // 100}")


def comum_num(t):
    from ..prefeituras.comum import num
    return num(t)


_TIPOS_CURTOS = [(r"COMBUST", "Combustíveis"), (r"DIVULGA", "Divulgação da atividade parlamentar"), (r"SOFTWARE|POSTAI|ASSINATURA|INTERNET", "Software, internet, correio e assinaturas"),
                 (r"LOCA[CÇ][AÃ]O DE VE[IÍ]CULO|VE[IÍ]CULO", "Veículos"), (r"CONSULTORIA|ASSESSORIA|T[EÉ]CNIC", "Consultorias e serviços técnicos"),
                 (r"ESCRIT[OÓ]RIO|IM[OÓ]VEL|ALUGUEL", "Escritório (aluguel e despesas)"), (r"ALIMENTA|HOSPEDA|LOCOMO|PASSAGE", "Alimentação, hospedagem e passagens"),
                 (r"TELEF", "Telefone"), (r"GR[AÁ]FIC|IMPRESS", "Gráfica e impressos")]


def _tipo(t):
    u = normalizar_nome(t)
    for rx, nome in _TIPOS_CURTOS:
        if re.search(rx, u):
            return nome
    return (t or "Outros").strip().capitalize()[:80]


def montar(tipos):
    arq = PASTA / "ceap_notas.csv"
    if not arq.exists():
        return None
    notas = pd.read_csv(arq, dtype={"cnpj_cpf": str}).fillna("")
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)  # o partido de 2022 já mudou para muitos: usamos o da candidatura de 2026, quando há
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((notas.ano * 100 + notas.mes).max())
    ver, mandatos, cods = [], [], {}
    for nome, g in notas.groupby("deputado"):
        t = comum.achar(nome, tse) or {}
        codigo = comum.codigo_de(nome, t)
        cods[nome] = codigo
        ver.append({"codigo": codigo, "nome": vc.titulo(nome) if nome.isupper() else nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "", "partido": partidos.get(normalizar_nome(t.get("nome", "")), ""),
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        for i, f in comum.periodos(list(g.ano * 100 + g.mes), ultimo_dado, ultimo):
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    desp = notas.assign(codigo=notas.deputado.map(cods), tipo=notas.tipo.map(_tipo))
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]])
