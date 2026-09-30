"""O que é comum às folhas de pagamento dos estados: o arquivo de cada estado, os meses que faltam, os nomes a procurar
e a classificação das rubricas (salário, 13º, férias, auxílios, outros, abate-teto).

Cada estado grava dados/governadores/folha/<uf>.csv (vai para o Git), uma linha por pessoa e mês, só do governador, do
vice e de quem governou interinamente (e, quando a pessoa recebe por outro cargo, como a governadora de Pernambuco,
pelo nome). Nunca guardamos CPF (nem mascarado) nem descontos pessoais (empréstimos, pensão alimentícia...): só o que
a pessoa recebe (o bruto e as partes dele) e o abate-teto, que é o corte feito para ninguém passar do teto.
"""
import json
import re

import pandas as pd

from ..config import DADOS
from ..util import log, normalizar_nome
from ..vereadores.comum import menos_meses, meses, ultimo_mes_fechado

PASTA = DADOS / "governadores" / "folha"
CURADO = DADOS / "governadores" / "governadores.json"
INICIO = 202501
# salario: subsídio (ou vencimento) do mês; decimo: 13º; ferias: 1/3 de férias e férias vendidas; beneficios: auxílios
# (alimentação, saúde...); outros: o resto do que é pago (atrasados, diferenças, verbas eventuais); redutor: abate-teto
# (positivo; já descontado do bruto); bruto: o total pago no mês, como a folha mostra. Parte desconhecida = vazio.
COLUNAS = ["aaaamm", "tp", "nome", "cargo", "salario", "decimo", "ferias", "beneficios", "outros", "redutor", "bruto"]
PARTES = ["salario", "decimo", "ferias", "beneficios", "outros"]


def arquivo(uf):
    return PASTA / f"{uf.lower()}.csv"


def ler(uf):
    a = arquivo(uf)
    return pd.read_csv(a) if a.exists() else pd.DataFrame(columns=COLUNAS)


def gravar(uf, linhas, meses_feitos):
    """Troca, no arquivo do estado, os meses processados agora pelas linhas novas."""
    velhas = ler(uf)
    # a mesma pessoa pode aparecer duas vezes na lista de ocupantes (a vice que vira governadora): linhas iguais contam uma vez
    novas = pd.DataFrame(linhas, columns=COLUNAS).drop_duplicates()
    if len(velhas):
        velhas = velhas[~velhas.aaaamm.isin(set(meses_feitos))]
    df = pd.concat([velhas, novas], ignore_index=True) if len(velhas) else novas
    PASTA.mkdir(parents=True, exist_ok=True)
    df.sort_values(["aaaamm", "tp", "nome"]).to_csv(arquivo(uf), index=False)
    return df


def a_fazer(uf, ultimo, refazer=2):
    """Meses de INICIO até ultimo que ainda não estão no arquivo, mais os `refazer` últimos (a folha pode ser corrigida)."""
    tem = set(ler(uf).aaaamm.astype(int)) if arquivo(uf).exists() else set()
    todos = [a * 100 + m for a, m in meses(INICIO, ultimo)]
    recentes = set(todos[-refazer:]) if refazer else set()
    return [am for am in todos if am not in tem or am in recentes]


def ocupantes(uf):
    """Governadores, vices e governadores em exercício do estado desde INICIO: [{nome, civil, folha_nome, cargo, de, ate}]."""
    for e in json.loads(CURADO.read_text(encoding="utf-8")):
        if e["uf"] == uf:
            return [o for o in e["ocupantes"] if not o.get("ate") or int(o["ate"][:4]) * 100 + int(o["ate"][5:7]) >= INICIO]
    return []


def no_cargo(o, aaaamm, folga=1):
    """A pessoa ocupava o cargo naquele mês (com `folga` meses a mais nas pontas, para pegar os acertos de saída)?"""
    de = int(o["de"][:4]) * 100 + int(o["de"][5:7])
    ate = int(o["ate"][:4]) * 100 + int(o["ate"][5:7]) if o.get("ate") else 999912
    return menos_meses(de, folga) <= aaaamm <= _mais(ate, folga)


def _mais(aaaamm, n):
    a, m = divmod(aaaamm, 100)
    for _ in range(n):
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return a * 100 + m


def nomes_folha(uf, aaaamm=None):
    """{nome como está na folha: "gov" ou "vice"} de quem procurar pelo nome (campo folha_nome no arquivo). O cargo é o
    que a pessoa ocupava naquele mês (o da folha nem sempre diz: em Roraima, o vice aparece como "SEXEC")."""
    saida = {}
    for folga in (0, 1):  # primeiro o cargo do próprio mês; depois, o dos meses vizinhos (acertos de saída)
        for o in ocupantes(uf):
            if o.get("folha_nome") and (aaaamm is None or no_cargo(o, aaaamm, folga)):
                saida.setdefault(o["folha_nome"], "vice" if o["cargo"] == "vice" else "gov")
    return saida


def tp_do_cargo(cargo):
    """"gov" ou "vice" quando o cargo é o de governador ou de vice ("GOVERNADOR DO ESTADO", "VICE-GOVERNADOR"...),
    e não um cargo que só tem a palavra (assessor do governador, diretor do Hospital Governador Celso Ramos...)."""
    c = re.sub(r"\s+", " ", normalizar_nome(cargo or "")).strip()
    m = re.fullmatch(r"(VICE[- ]?)?GOVERNADORA?( D[OE] ESTADO.*)?", c)
    if not m:
        return None
    return "vice" if m.group(1) else "gov"


def classificar(descricao):
    """Parte do pagamento pelo nome da rubrica."""
    d = normalizar_nome(descricao or "")
    if re.search(r"\b13|DECIMO|NATALINA|NATAL\b", d):
        return "decimo"
    if re.search(r"FERIAS|ABONO PECUNIARIO|1/3", d):
        return "ferias"
    if re.search(r"AUX|ALIMENTA|SAUDE|BENEFICIO|CRECHE|TRANSPORTE", d):
        return "beneficios"
    if re.search(r"SUBSIDIO|VENCIMENTO|REPRESENTACAO|REMUNERACAO BASICA|SALARIO", d):
        return "salario"
    return "outros"


def eh_redutor(descricao):
    return bool(re.search(r"TETO|REDUTOR|EXCEDENTE|ABATE", normalizar_nome(descricao or "")))


def linha(aaaamm, tp, nome, cargo, bruto, partes=None, redutor=0.0):
    """partes: {salario, decimo, ferias, beneficios, outros} (None = a folha não separa)."""
    p = partes or {}
    return {"aaaamm": int(aaaamm), "tp": tp, "nome": re.sub(r"\s+", " ", str(nome)).strip(), "cargo": re.sub(r"\s+", " ", str(cargo or "")).strip(),
            **{k: (round(float(p[k]), 2) if k in p and p[k] is not None else None) for k in PARTES},
            "redutor": round(float(redutor or 0), 2), "bruto": round(float(bruto), 2)}


def somar_rubricas(rubricas):
    """[(descricao, valor, credito?)] -> (partes, redutor, bruto)."""
    partes = {k: 0.0 for k in PARTES}
    redutor = 0.0
    for desc, valor, credito in rubricas:
        v = float(valor or 0)
        if credito:
            partes[classificar(desc)] += v
        elif eh_redutor(desc):
            redutor += v
    return partes, redutor, sum(partes.values())


def ultimo_possivel():
    return ultimo_mes_fechado()


def avisar(uf, texto):
    log(f"  Folha {uf}: {texto}")


def linhas_csv(url, chaves, encoding="utf-8-sig", sep=";", timeout=600, colunas=None):
    """Lê um CSV grande aos poucos, sem guardar, e devolve (cabeçalho, [linhas que têm alguma das chaves]) como dicionários.
    As chaves (sem acento) são procuradas nos bytes da linha, em maiúsculas, antes de ler as colunas: é o que deixa ler
    arquivos de 100-200 MB sem gastar memória. `colunas`: nomes das colunas, para arquivo sem linha de cabeçalho."""
    import csv
    import time
    from ..util import TempoEsgotado, _sessao, verificar_prazo
    chaves = [normalizar_nome(c).encode("ascii") for c in chaves]
    bom = "\N{ZERO WIDTH NO-BREAK SPACE}"
    for tentativa in range(3):
        verificar_prazo()
        try:
            achadas, cab = [], (list(colunas) if colunas else None)
            with _sessao().get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                for i, bruta in enumerate(r.iter_lines(chunk_size=1 << 20)):
                    if cab is None:
                        cab = [c.strip() for c in next(csv.reader([bruta.decode(encoding, "replace").lstrip(bom)], delimiter=sep))]
                        continue
                    if i % 200000 == 0:
                        verificar_prazo()
                    maiusc = bruta.upper()
                    if any(c in maiusc for c in chaves):
                        achadas.append(dict(zip(cab, next(csv.reader([bruta.decode(encoding, "replace")], delimiter=sep)))))
            return cab, achadas
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(30)


def num(t):
    """'1.234,56', '1234.56', '1234,56' -> float."""
    from ..prefeituras.comum import num as _num
    return _num(t)
