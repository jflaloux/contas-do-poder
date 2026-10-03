#!/usr/bin/env python3
"""Cópia local da caixa do Gmail da conta do projeto, para ler as respostas. Só leitura: não envia, não marca como lido,
não arquiva, não apaga.

Baixa as mensagens novas (recebidas e enviadas, sem os rascunhos, o spam e a lixeira) e grava cada conversa (thread)
num arquivo Markdown em CAIXA-CONTATO/ (na raiz, fora do Git), com nome que ordena por data:
AAAA-MM-DD_assunto_<id da conversa>.md. Cada mensagem traz De, Para, Cc, Data, Assunto, os nomes dos anexos (nenhum
anexo é baixado) e o texto puro, sem o texto citado das respostas. Sequências com cara de CPF (11 dígitos, com ou sem
pontuação) e de cartão (13 a 19 dígitos que passam no dígito verificador) são mascaradas na cópia.
O id da conversa, no começo de cada arquivo, é o que vai em "responde-a:" no arquivo de rascunhos (rascunhos_gmail.py).

Incremental: o ponto da última leitura fica em ~/.config/contas-do-poder/caixa-estado.json, e a próxima execução baixa
só o que chegou ou saiu depois (a conversa inteira é reescrita quando tem mensagem nova). --desde=AAAA-MM-DD refaz a
partir de uma data; na primeira vez, o padrão é 30/09/2026.

Mesma credencial, mesmo token e mesma conta do projeto de rascunhos_gmail.py (gmail_comum.py). No fim, um resumo:
quantas conversas novas e quais respondem a e-mails nossos (conversas com mensagem enviada pelo projeto e uma resposta
de outra pessoa depois dela).

Uso (sempre com o Python do .venv):
    .venv/bin/python rotina/caixa_gmail.py                       # baixa o que é novo
    .venv/bin/python rotina/caixa_gmail.py --desde=2026-09-30    # refaz a partir dessa data
    .venv/bin/python rotina/caixa_gmail.py --nova-autorizacao    # refaz a autorização (escolha a conta do projeto)
"""
import argparse
import base64
import html
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gmail_comum as gc  # noqa: E402
from gmail_comum import CONFIG, REMETENTE  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "CAIXA-CONTATO"
ESTADO = "caixa-estado.json"
DESDE_PADRAO = "2026-09-30"
FUSO = ZoneInfo("America/Sao_Paulo")
CABECALHOS = ("From", "To", "Cc", "Date", "Subject", "Reply-To", "Message-ID")


# --------------------------------------------------------------------------------------------------- privacidade
def _luhn(digitos):
    soma, dobro = 0, False
    for d in reversed(digitos):
        n = int(d) * (2 if dobro else 1)
        soma += n - 9 if n > 9 else n
        dobro = not dobro
    return soma % 10 == 0


RE_CARTAO = re.compile(r"(?<![\d.\-/])\d(?:[ -]?\d){12,18}(?![\d])")
RE_CPF = re.compile(r"(?<![\d])\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}(?![\d])")


def mascarar(t):
    """Tira da cópia o que tem cara de CPF (11 dígitos, com ou sem pontuação) e de número de cartão."""
    if not t:
        return t
    t = RE_CARTAO.sub(lambda m: "[número de cartão mascarado]" if _luhn(re.sub(r"\D", "", m.group(0))) else m.group(0), t)
    return RE_CPF.sub("[CPF mascarado]", t)


# ----------------------------------------------------------------------------------------------- texto das mensagens
def _b64(dados):
    return base64.urlsafe_b64decode(dados + "=" * (-len(dados) % 4)) if dados else b""


def _charset(parte):
    for h in parte.get("headers", []):
        if h["name"].lower() == "content-type":
            m = re.search(r'charset="?([\w.-]+)', h["value"], flags=re.I)
            if m:
                return m.group(1)
    return "utf-8"


def _partes(p):
    yield p
    for x in p.get("parts", []) or []:
        yield from _partes(x)


def _de_html(t):
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", t)
    t = re.sub(r"(?is)<blockquote\b.*?</blockquote>", "\n[texto citado cortado]\n", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>", "\n", t)
    t = re.sub(r"(?i)<li\b[^>]*>", "- ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(l.rstrip() for l in t.splitlines())


def texto_e_anexos(payload):
    """(texto puro, [nomes dos anexos]). Usa a parte text/plain; sem ela, a text/html convertida em texto."""
    plano = html_ = None
    anexos = []
    for p in _partes(payload):
        nome = p.get("filename") or ""
        if nome:
            anexos.append(nome)
            continue
        dados = (p.get("body") or {}).get("data")
        if not dados:
            continue
        conteudo = _b64(dados).decode(_charset(p), errors="replace")
        if p.get("mimeType") == "text/plain" and plano is None:
            plano = conteudo
        elif p.get("mimeType") == "text/html" and html_ is None:
            html_ = conteudo
    texto = plano if plano is not None else (_de_html(html_) if html_ else "")
    return texto.replace("\r\n", "\n"), anexos


RE_CITACAO = re.compile(
    r"(?im)^(?:"
    r"(?:Em|On|Le|El)\b[^\n]{0,200}(?:\n[^\n]{0,200})?(?:escreveu|wrote|a écrit|escribió)\s*:"
    r"|-{2,}\s*(?:Original Message|Mensagem original|Mensaje original)\s*-{2,}"
    r"|_{5,}\s*$"
    r"|(?:De|From):\s[^\n]+\n(?:[^\n]*\n){0,3}?(?:Enviad[ao]|Sent|Data|Date):\s"
    r")")


def sem_citacao(t):
    """Corta o texto citado: a partir de "Em ..., Fulano escreveu:" (e equivalentes) e os blocos de linhas com ">"."""
    m = RE_CITACAO.search(t)
    cortou = False
    if m and m.start() > 0:
        t, cortou = t[:m.start()], True
    linhas, saida = t.splitlines(), []
    for l in linhas:
        if l.lstrip().startswith(">"):
            if not saida or saida[-1] != "[texto citado cortado]":
                saida.append("[texto citado cortado]")
            continue
        saida.append(l)
    t = "\n".join(saida).strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t + ("\n\n[texto citado cortado]" if cortou else "")


# --------------------------------------------------------------------------------------------------- conversas
def _cab(m):
    return {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}


def _quando(m):
    return datetime.fromtimestamp(int(m.get("internalDate", 0)) / 1000, tz=timezone.utc).astimezone(FUSO)


def _slug(t, n=60):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"^\s*((re|res|enc|fwd?)\s*:\s*)+", "", t)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:n].strip("-") or "sem-assunto"


def _nossa(m, nossos):
    return "SENT" in (m.get("labelIds") or []) or any(a.lower() in nossos for _, a in getaddresses([_cab(m).get("from", "")]))


def markdown_da_conversa(c, nossos, agora):
    msgs = [m for m in c.get("messages", []) if "DRAFT" not in (m.get("labelIds") or [])]
    assunto = mascarar(_cab(msgs[0]).get("subject", "") or "(sem assunto)")
    linhas = [f"# {assunto}", "",
              f"- Conversa (thread): {c['id']}  (para responder dentro dela: \"responde-a: {c['id']}\" no arquivo de rascunhos)",
              f"- Mensagens: {len(msgs)}, de {_quando(msgs[0]):%d/%m/%Y %H:%M} a {_quando(msgs[-1]):%d/%m/%Y %H:%M}",
              f"- Cópia feita em {agora:%d/%m/%Y %H:%M} (só leitura; CPF e cartão mascarados; anexos só pelo nome)", ""]
    for i, m in enumerate(msgs, 1):
        h = _cab(m)
        texto, anexos = texto_e_anexos(m.get("payload", {}))
        quem = "enviada pelo projeto" if _nossa(m, nossos) else "recebida"
        linhas += [f"## {i}. {_quando(m):%d/%m/%Y %H:%M} ({quem})", "",
                   f"- De: {mascarar(h.get('from', ''))}",
                   f"- Para: {mascarar(h.get('to', ''))}"]
        if h.get("cc"):
            linhas.append(f"- Cc: {mascarar(h['cc'])}")
        linhas += [f"- Data: {h.get('date', '')}", f"- Assunto: {mascarar(h.get('subject', ''))}"]
        if anexos:
            linhas.append(f"- Anexos (não baixados): {mascarar(', '.join(anexos))}")
        linhas += ["", mascarar(sem_citacao(texto)) or "(sem texto)", ""]
    return "\n".join(linhas).rstrip() + "\n", msgs


def responde_a_nos(msgs, nossos):
    """A conversa tem mensagem nossa e, depois dela, uma de outra pessoa?"""
    primeira_nossa = next((i for i, m in enumerate(msgs) if _nossa(m, nossos)), None)
    return primeira_nossa is not None and any(not _nossa(m, nossos) for m in msgs[primeira_nossa + 1:])


def _listar(s, consulta):
    ids, token = [], None
    while True:
        d = gc.pedir(s, "GET", "/messages", params={"q": consulta, "maxResults": 500, **({"pageToken": token} if token else {})})
        ids += [(x["id"], x["threadId"]) for x in d.get("messages", [])]
        token = d.get("nextPageToken")
        if not token:
            return ids


def _desde(texto):
    return datetime.strptime(texto, "%Y-%m-%d").replace(tzinfo=FUSO)


def main(argv=None, sessao_fn=None):
    ap = argparse.ArgumentParser(description="Cópia local (só leitura) da caixa do Gmail da conta do projeto.")
    ap.add_argument("--desde", default="", help="AAAA-MM-DD: refaz a partir dessa data (padrão: desde a última leitura; na primeira, "
                                                f"{DESDE_PADRAO})")
    ap.add_argument("--pasta", default=str(PASTA), help="onde gravar a cópia (fora do Git)")
    ap.add_argument("--config", default=str(CONFIG), help="pasta da credencial, do token e do estado")
    ap.add_argument("--conta", default=os.environ.get("CONTAS_GMAIL_CONTA", ""), help="a conta do projeto (como em rascunhos_gmail.py)")
    ap.add_argument("--nova-autorizacao", action="store_true", help="refaz a autorização no navegador (o token atual vira .antigo)")
    a = ap.parse_args(argv)

    config, pasta = Path(a.config), Path(a.pasta)
    s = (sessao_fn or (lambda c, nova, conta: gc.sessao(c, nova, conta, script="caixa_gmail.py")))(config, a.nova_autorizacao, a.conta)
    _, conta = gc.conta_ok(s, REMETENTE, a.conta, config, script="caixa_gmail.py", nada="Nada foi lido.")
    nossos = {REMETENTE.lower(), conta.lower()}
    arq_estado = config / ESTADO
    estado = json.loads(arq_estado.read_text(encoding="utf-8")) if arq_estado.exists() else {}
    if a.desde:
        inicio = _desde(a.desde)
    elif estado.get("ultima_mensagem"):
        inicio = datetime.fromtimestamp(estado["ultima_mensagem"] - 1, tz=timezone.utc)
    else:
        inicio = _desde(DESDE_PADRAO)
    consulta = f"after:{int(inicio.timestamp())} -in:drafts"
    novas = _listar(s, consulta)
    conversas = list(dict.fromkeys(t for _, t in novas))
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(FUSO)
    novas_conversas, respostas, ultima = [], [], estado.get("ultima_mensagem", 0)
    for tid in conversas:
        c = gc.pedir(s, "GET", f"/threads/{tid}", params={"format": "full"})
        if not [m for m in c.get("messages", []) if "DRAFT" not in (m.get("labelIds") or [])]:
            continue
        md, msgs = markdown_da_conversa(c, nossos, agora)
        nome = f"{_quando(msgs[0]):%Y-%m-%d}_{_slug(_cab(msgs[0]).get('subject', ''))}_{tid}.md"
        antigos = list(pasta.glob(f"*_{tid}.md"))
        if not antigos:
            novas_conversas.append(nome)
        for x in antigos:
            if x.name != nome:
                x.replace(pasta / nome)
        (pasta / nome).write_text(md, encoding="utf-8")
        ultima = max([ultima] + [int(m.get("internalDate", 0)) // 1000 for m in msgs])
        if responde_a_nos(msgs, nossos):
            deles = [m for m in msgs if not _nossa(m, nossos)]
            respostas.append((nome, mascarar(_cab(deles[-1]).get("from", "")), _quando(deles[-1])))
    config.mkdir(parents=True, exist_ok=True)
    arq_estado.write_text(json.dumps({"conta": conta, "ultima_mensagem": ultima, "lida_em": agora.isoformat(timespec="seconds")},
                                     ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(arq_estado, 0o600)
    print(f"Conta {conta}: {len(novas)} mensagens desde {inicio.astimezone(FUSO):%d/%m/%Y %H:%M}, em {len(conversas)} conversas "
          f"({len(novas_conversas)} novas), gravadas em {pasta}.")
    if respostas:
        print(f"Conversas que respondem a e-mails nossos ({len(respostas)}):")
        for nome, de, quando in sorted(respostas, key=lambda x: x[2]):
            print(f"  {quando:%d/%m %H:%M}  {de}  ->  {nome}")
    else:
        print("Nenhuma conversa nova ou atualizada responde a e-mails nossos.")
    print("Nada foi enviado, marcado como lido, arquivado ou apagado no Gmail.")


if __name__ == "__main__":
    main()
