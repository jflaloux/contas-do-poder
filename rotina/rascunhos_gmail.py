#!/usr/bin/env python3
"""Rascunhos de e-mail no Gmail a partir de um arquivo Markdown de rascunhos. NUNCA envia nada.

O script lê os blocos do arquivo (por padrão, RASCUNHOS-DIVULGACAO.md na raiz, fora do Git), monta cada e-mail
(texto puro e HTML, com links diretos) e cria ou atualiza o rascunho no Gmail, pela API oficial. Quem envia é a pessoa,
no Gmail, clicando em Enviar. O código só chama: a lista de remetentes (settings/sendAs), a lista e a leitura de
rascunhos e a criação e a atualização de rascunhos. Nenhuma função de envio (drafts.send, messages.send) é chamada, e
_pedir() recusa qualquer endereço da API que termine em /send.

Uso (sempre com o Python do .venv):
    .venv/bin/python rotina/rascunhos_gmail.py                 # só mostra o que faria (para quem, assunto, cria ou atualiza)
    .venv/bin/python rotina/rascunhos_gmail.py --teste         # cria um rascunho de teste para a própria conta
    .venv/bin/python rotina/rascunhos_gmail.py --criar         # cria ou atualiza todos
    .venv/bin/python rotina/rascunhos_gmail.py --criar --so=3,7,ALRN
    .venv/bin/python rotina/rascunhos_gmail.py --sem-gmail --mostrar=7   # sem conectar: a leitura e o e-mail montado

Formato de cada bloco do arquivo (um "## " por rascunho):
    ## 7. Título livre

    ```email
    para: endereco@dominio
    cc: outro@dominio, mais@dominio
    assunto: O assunto, numa linha
    responde-a: id da conversa   (opcional: resposta dentro da conversa; o id está no arquivo da conversa em CAIXA-CONTATO/)
    a-partir-de: AAAA-MM-DD      (opcional: antes dessa data, horário de Brasília, o painel não libera o envio)
    ```

    (notas livres, que não vão no e-mail)

    **Texto**

    O corpo, com as linhas quebradas onde for; parágrafos separados por linha em branco, itens com "- ".
    ...

    **Notas** (opcional: daqui até o fim do bloco, nada vai no e-mail)

    ---
O bloco sem a caixa ```email fica de fora (formulário, endereço a conferir). Também se lê o formato antigo, com as
linhas "- **Para:**" e "- **Assunto:**": o primeiro endereço do "Para" é o destinatário, os endereços depois de
"Cópia:" vão em cópia, os depois de "Opcional, com cópia:" só com --com-copias-opcionais, e o que está entre parênteses
é comentário. Um "Para" que não começa com um endereço fica de fora (o script não adivinha).

Credencial (fora do repositório, em ~/.config/contas-do-poder/): gmail-credencial.json (o arquivo do cliente OAuth "App
para computador" baixado do Google Cloud) e gmail-token.json (criado na primeira autorização, no navegador, com a conta
do projeto). Antes de gravar, o script confere em que conta o token está (users.getProfile e "Enviar e-mail como"): os
rascunhos só vão para a conta do projeto: a de --conta (gravada em conta-do-projeto, na mesma pasta, no primeiro uso
que dá certo) ou, sem conta gravada, a que tem o remetente como endereço principal. Token de outra conta: para e diz o
que fazer (--conta, se a conta é a do projeto; --nova-autorizacao, se não é).
Com "responde-a", o rascunho é uma resposta dentro da conversa (threadId, In-Reply-To e References da última mensagem):
o assunto é o da conversa com "Re:", e o destinatário, se não houver "para:", é quem escreveu por último (Reply-To ou
From). Um rascunho que já está na conversa é atualizado.
Escopos (os mesmos de caixa_gmail.py, em gmail_comum.py): gmail.compose (rascunhos; o Google não tem um escopo de
rascunho que não permita também enviar), gmail.settings.basic (a lista de remetentes) e gmail.readonly (ler a conversa a
que o rascunho responde).
Dependências só no .venv do computador que cria os rascunhos: .venv/bin/pip install -r rotina/requirements-gmail.txt
"""
import argparse
import base64
import html
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, getaddresses
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gmail_comum as gc  # noqa: E402  (autorização, conta do projeto e a trava contra envio, iguais às de caixa_gmail.py)
from gmail_comum import API, CONFIG, ESCOPOS, REMETENTE  # noqa: E402,F401

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "RASCUNHOS-DIVULGACAO.md"
# endereços do projeto que viram link mesmo escritos sem https:// (com ou sem caminho). Os de fora só viram link
# escritos por inteiro, com https:// (o script não adivinha se o site precisa de "www.")
NOSSOS = ("contasdopoder.com", "github.com/jflaloux/contas-do-poder")

EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
RE_EMAIL = re.compile(EMAIL)


@dataclass
class Rascunho:
    numero: int | None
    titulo: str
    para: list = field(default_factory=list)
    cc: list = field(default_factory=list)
    cc_opcional: list = field(default_factory=list)
    assunto: str = ""
    corpo: list = field(default_factory=list)  # linhas do corpo, como estão no arquivo
    formato: str = ""
    fora: str = ""  # motivo de ficar de fora (sem destinatário, sem assunto...)
    responde_a: str = ""  # id da conversa (thread) do Gmail: o rascunho é uma resposta dentro dela
    a_partir_de: str = ""  # AAAA-MM-DD: antes dessa data, o painel não libera o envio (enviar_gmail.py)
    avisos: list = field(default_factory=list)


# ----------------------------------------------------------------------------------------------- leitura do arquivo
def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()


def _sem_parenteses(t):
    saida, nivel = [], 0
    for c in t:
        if c == "(":
            nivel += 1
        elif c == ")" and nivel:
            nivel -= 1
        elif not nivel:
            saida.append(c)
    return "".join(saida)


def _enderecos(t):
    return [e for e in RE_EMAIL.findall(t)]


def _para_antigo(valor):
    """O "Para" do formato antigo -> (para, cc, cc_opcional). O que está entre parênteses é comentário."""
    t = " ".join(_sem_parenteses(valor).split())
    m = re.match(rf"\s*((?:{EMAIL})(?:\s*(?:,|\be\b)\s*{EMAIL})*)", t)
    if not m:
        return [], [], []
    para = _enderecos(m.group(1))
    cc, opc = [], []
    for seg in re.finditer(r"(opcional[^:]*?c[oó]pia|c[oó]pia)\s*:\s*(.*?)(?=(?:\bopcional\b|\bc[oó]pia\s*:)|$)", t[m.end():], flags=re.I):
        (opc if "opcional" in seg.group(1).lower() else cc).extend(_enderecos(seg.group(2)))
    return para, cc, opc


def _itens_meta(linhas):
    """Linhas "- **Chave:** valor" (com as continuações recuadas) -> [(chave sem acento, valor)]."""
    itens = []
    for l in linhas:
        m = re.match(r"^- \*\*(.+?)\*\*\s*(.*)$", l)
        if m:
            itens.append([_sem_acento(m.group(1)).rstrip(": "), m.group(2).lstrip(": ").strip()])
        elif itens and l.startswith("  ") and l.strip():
            itens[-1][1] += " " + l.strip()
    return itens


def _corpo(linhas, inicio):
    """O corpo: a partir de `inicio` (pula as linhas em branco e um título em negrito, como **Texto**) até "---", até
    uma linha só em negrito (**Notas...**) ou até o fim do bloco."""
    i = inicio
    while i < len(linhas) and not linhas[i].strip():
        i += 1
    if i < len(linhas) and re.match(r"^\*\*[^*]+\*\*\s*$", linhas[i]):
        i += 1
    corpo = []
    for l in linhas[i:]:
        if l.strip() == "---" or re.match(r"^\*\*[^*]+\*\*\s*$", l):
            break
        corpo.append(l.rstrip())
    while corpo and not corpo[0].strip():
        corpo.pop(0)
    while corpo and not corpo[-1].strip():
        corpo.pop()
    return corpo


def _bloco(cabeca, linhas, com_opcionais):
    m = re.match(r"^(\d+)\.\s*(.*)$", cabeca)
    r = Rascunho(int(m.group(1)) if m else None, (m.group(2) if m else cabeca).strip())
    # formato novo: a caixa ```email
    ini = next((i for i, l in enumerate(linhas) if l.strip().lower() in ("```email", "~~~email")), None)
    if ini is not None:
        r.formato = "novo"
        fim = next((i for i in range(ini + 1, len(linhas)) if linhas[i].strip() in ("```", "~~~")), len(linhas))
        campos = {}
        for l in linhas[ini + 1:fim]:
            mm = re.match(r"^\s*([A-Za-zçÇóÓ-]+)\s*:\s*(.*)$", l)
            if mm:
                campos[_sem_acento(mm.group(1))] = mm.group(2).strip()
        r.para, r.cc = _enderecos(campos.get("para", "")), _enderecos(campos.get("cc", ""))
        r.cc_opcional = _enderecos(campos.get("cc-opcional", ""))
        r.assunto = campos.get("assunto", "")
        r.responde_a = re.sub(r"[^0-9A-Za-z]", "", campos.get("responde-a", ""))
        r.a_partir_de = campos.get("a-partir-de", "").strip()
        if r.a_partir_de and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.a_partir_de):
            r.avisos.append(f'"a-partir-de" fora do formato AAAA-MM-DD: {r.a_partir_de}')
        texto = next((i for i, l in enumerate(linhas) if re.match(r"^\*\*texto\*\*\s*$", l.strip(), flags=re.I)), None)
        r.corpo = _corpo(linhas, texto if texto is not None else fim + 1)
        if texto is None:
            r.avisos.append('sem a linha **Texto**: o corpo começa depois da caixa ```email')
    else:
        r.formato = "antigo"
        i0 = next((i for i, l in enumerate(linhas) if l.startswith("- **")), None)
        if i0 is None:
            r.fora = "sem a caixa ```email (formulário, endereço a conferir)"
            return r
        i1 = i0
        while i1 < len(linhas) and linhas[i1].strip():
            i1 += 1
        meta = _itens_meta(linhas[i0:i1])
        para = next((v for k, v in meta if k == "para"), "")
        r.para, r.cc, r.cc_opcional = _para_antigo(para)
        r.assunto = next((v for k, v in meta if k.startswith("assunto")), "")
        de = next((v for k, v in meta if k == "de"), "")
        if de and REMETENTE not in de:
            r.avisos.append(f'o "De" do arquivo não é {REMETENTE}: {de[:60]}')
        texto = next((i for i in range(i1, len(linhas)) if re.match(r"^\*\*texto\*\*\s*$", linhas[i].strip(), flags=re.I)), None)
        r.corpo = _corpo(linhas, texto if texto is not None else i1)
        if not r.para:
            r.fora = 'o "Para" não começa com um endereço de e-mail (formulário ou endereço a conferir)'
    if com_opcionais:
        r.cc += r.cc_opcional
    if not r.fora and not r.para and not r.responde_a:
        r.fora = "sem destinatário"
    if not r.fora and not r.assunto and not r.responde_a:
        r.fora = "sem assunto"
    if not r.fora and not r.corpo:
        r.fora = "sem corpo"
    if r.cc_opcional and not com_opcionais:
        r.avisos.append("cópia opcional fora (use --com-copias-opcionais para incluir): " + ", ".join(r.cc_opcional))
    return r


def ler(arquivo, com_opcionais=False):
    """Os blocos "## " do arquivo que têm destinatário (ou motivo para ficar de fora)."""
    linhas = Path(arquivo).read_text(encoding="utf-8").splitlines()
    blocos, atual = [], None
    for l in linhas:
        if l.startswith("## "):
            atual = [l[3:].strip(), []]
            blocos.append(atual)
        elif atual:
            atual[1].append(l)
    saida = []
    for cabeca, corpo in blocos:
        if not re.match(r"^\d+\.", cabeca) and not any(l.startswith("- **") or l.strip().lower() in ("```email", "~~~email") for l in corpo):
            continue  # índice, notas: não é rascunho (um bloco numerado sem a caixa ```email aparece como "fica de fora")
        saida.append(_bloco(cabeca, corpo, com_opcionais))
    return saida


# --------------------------------------------------------------------------------------------- montagem do e-mail
def _paragrafos(linhas):
    """Linhas do arquivo (quebradas em ~130 colunas) -> [("texto", [linhas]) | ("lista", [itens])].
    Parágrafo comum: as linhas se juntam. Itens "- ": cada item numa linha (as continuações recuadas se juntam a ele).
    Parágrafo de linhas curtas (assinatura, endereço): as quebras ficam."""
    grupos, atual = [], []
    for l in linhas + [""]:
        if l.strip():
            atual.append(l)
        elif atual:
            grupos.append(atual)
            atual = []
    saida = []
    for g in grupos:
        if len(g) > 1 and all(len(l) < 80 for l in g[:-1]) and not any(l.startswith("- ") for l in g):
            saida.append(("texto", [l.strip() for l in g], True))
            continue
        intro, itens = [], []
        for l in g:
            if l.startswith("- "):
                itens.append(l[2:].strip())
            elif itens and (l.startswith("  ") or l.startswith("\t")):
                itens[-1] += " " + l.strip()
            elif itens:
                itens[-1] += " " + l.strip()
            else:
                intro.append(l.strip())
        if intro and itens:
            saida.append(("misto", [" ".join(intro)] + itens, False))  # a frase que abre a lista e os itens, juntos
        elif intro:
            saida.append(("texto", [" ".join(intro)], False))
        elif itens:
            saida.append(("lista", itens, False))
    return saida


def texto_puro(linhas):
    partes = []
    for tipo, ls, _ in _paragrafos(linhas):
        if tipo == "misto":
            partes.append("\n".join([ls[0]] + ["- " + x for x in ls[1:]]))
        else:
            partes.append("\n".join(("- " + x) if tipo == "lista" else x for x in ls))
    return "\n\n".join(partes) + "\n"


RE_LINK = re.compile(
    rf"(?P<email>{EMAIL})"
    r"|(?P<url>https?://[^\s<>\"]+)"
    rf"|(?<![\w@./-])(?P<nosso>(?:{'|'.join(re.escape(d) for d in NOSSOS)})(?:/[^\s<>\"]*)?)(?![\w-])")


def _linkar(t):
    """Texto -> HTML escapado, com links diretos: e-mails (mailto:), endereços escritos com https:// e os endereços do
    projeto (NOSSOS), com ou sem caminho. Nenhum link passa por redirecionamento."""
    saida, pos = [], 0
    for m in RE_LINK.finditer(t):
        alvo = m.group(0)
        resto = ""
        if not m.group("email"):
            while alvo and alvo[-1] in ".,;:!?'\"»”":
                resto = alvo[-1] + resto
                alvo = alvo[:-1]
            if alvo.endswith(")") and alvo.count("(") < alvo.count(")"):
                resto = ")" + resto
                alvo = alvo[:-1]
        if m.group("email"):
            href = "mailto:" + alvo
        elif m.group("url"):
            href = alvo
        else:
            href = "https://" + alvo
        saida.append(html.escape(t[pos:m.start()]))
        saida.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(alvo)}</a>{html.escape(resto)}')
        pos = m.end()
    saida.append(html.escape(t[pos:]))
    return "".join(saida)


def html_do_corpo(linhas):
    partes = []
    for tipo, ls, curtas in _paragrafos(linhas):
        if tipo in ("lista", "misto"):
            itens = ls[1:] if tipo == "misto" else ls
            if tipo == "misto":
                partes.append(f'<p style="margin-bottom:0">{_linkar(ls[0])}</p>')
            partes.append('<ul style="margin-top:0">\n' + "\n".join(f"<li>{_linkar(x)}</li>" for x in itens) + "\n</ul>")
        else:
            partes.append("<p>" + "<br>\n".join(_linkar(x) for x in ls) + "</p>")
    return '<!DOCTYPE html>\n<html><head><meta charset="utf-8"></head><body>\n' + "\n".join(partes) + "\n</body></html>\n"


def montar(r, remetente, nome_remetente="", para=None, prefixo="", assunto=None, resposta=None):
    """O e-mail (multipart/alternative, UTF-8): texto puro e HTML. Com `resposta` (de conversa()), os cabeçalhos
    In-Reply-To e References, para o Gmail e o destinatário guardarem a mensagem na mesma conversa."""
    msg = EmailMessage(policy=SMTP)
    msg["From"] = formataddr((nome_remetente, remetente)) if nome_remetente else remetente
    msg["To"] = ", ".join(para if para is not None else r.para)
    if r.cc and (para is None or resposta):
        msg["Cc"] = ", ".join(r.cc)
    msg["Subject"] = prefixo + (assunto if assunto is not None else r.assunto)
    if resposta and resposta.get("in_reply_to"):
        msg["In-Reply-To"] = resposta["in_reply_to"]
        msg["References"] = resposta["references"]
    msg.set_content(texto_puro(r.corpo), subtype="plain", charset="utf-8", cte="quoted-printable")
    msg.add_alternative(html_do_corpo(r.corpo), subtype="html", charset="utf-8", cte="quoted-printable")
    return msg


# ------------------------------------------------------------------------------------------------------- Gmail
def sessao(config, nova=False, conta=""):
    return gc.sessao(config, nova, conta, script="rascunhos_gmail.py")


_pedir = gc.pedir  # recusa qualquer caminho terminado em /send


def remetente_ok(s, endereco, conta_arg="", config=None):
    return gc.conta_ok(s, endereco, conta_arg, config, script="rascunhos_gmail.py", nada="Nenhum rascunho foi criado.")


def conversa(s, thread_id, nossos):
    """Dados para responder dentro de uma conversa: o assunto com "Re:", o Message-ID e as References da última mensagem
    (sem os rascunhos) e o destinatário (Reply-To ou From da última mensagem que não é nossa; se todas são nossas, o
    To da última)."""
    d = _pedir(s, "GET", f"/threads/{thread_id}", params=[("format", "metadata")] + [
        ("metadataHeaders", h) for h in ("From", "To", "Reply-To", "Subject", "Message-ID", "References")])
    msgs = [m for m in d.get("messages", []) if "DRAFT" not in (m.get("labelIds") or [])]
    if not msgs:
        raise RuntimeError(f"a conversa {thread_id} não tem mensagens")
    cab = lambda m: {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
    ultima = cab(msgs[-1])
    deles = [cab(m) for m in msgs if not any(a.lower() in nossos for _, a in getaddresses([cab(m).get("from", "")]))]
    if deles:
        alvo = [a for _, a in getaddresses([deles[-1].get("reply-to") or deles[-1].get("from", "")]) if a]
    else:
        alvo = [a for _, a in getaddresses([ultima.get("to", "")]) if a]
    assunto = re.sub(r"^\s*((re|res|enc|fwd?)\s*:\s*)+", "", ultima.get("subject", ""), flags=re.I)
    mid = ultima.get("message-id", "")
    return {"assunto": "Re: " + assunto, "para": alvo, "in_reply_to": mid,
            "references": " ".join(x for x in (ultima.get("references", ""), mid) if x).strip()}


def _chave(para, assunto):
    return frozenset(a.lower() for a in para), " ".join(assunto.split()).lower()


def rascunhos_existentes(s):
    """{(destinatários, assunto): [ids]}, {destinatário: [(id, assunto)]} e {conversa: [ids]} dos rascunhos da conta."""
    por_chave, por_para, por_conversa, token = {}, {}, {}, None
    while True:
        d = _pedir(s, "GET", "/drafts", params={"maxResults": 500, **({"pageToken": token} if token else {})})
        for x in d.get("drafts", []):
            m = _pedir(s, "GET", f"/drafts/{x['id']}", params={"format": "metadata"})
            cab = {h["name"].lower(): h["value"] for h in m.get("message", {}).get("payload", {}).get("headers", [])}
            para = [a for _, a in getaddresses([cab.get("to", "")]) if a]
            assunto = cab.get("subject", "")
            por_chave.setdefault(_chave(para, assunto), []).append(x["id"])
            for a in para:
                por_para.setdefault(a.lower(), []).append((x["id"], assunto))
            if m.get("message", {}).get("threadId"):
                por_conversa.setdefault(m["message"]["threadId"], []).append(x["id"])
        token = d.get("nextPageToken")
        if not token:
            return por_chave, por_para, por_conversa


def gravar(s, msg, id_existente=None, conversa_id=None):
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    mensagem = {"raw": raw, **({"threadId": conversa_id} if conversa_id else {})}
    if id_existente:
        return _pedir(s, "PUT", f"/drafts/{id_existente}", json={"id": id_existente, "message": mensagem})
    return _pedir(s, "POST", "/drafts", json={"message": mensagem})


# --------------------------------------------------------------------------------------------------------- main
def escolher(rascunhos, so):
    if not so:
        return rascunhos
    pedidos = [x.strip() for x in so.split(",") if x.strip()]
    saida = []
    for r in rascunhos:
        for p in pedidos:
            if (p.isdigit() and r.numero == int(p)) or (not p.isdigit() and _sem_acento(p) in _sem_acento(r.titulo)):
                saida.append(r)
                break
    return saida


def main(argv=None, sessao_fn=None):
    ap = argparse.ArgumentParser(description="Cria ou atualiza rascunhos no Gmail a partir do arquivo de rascunhos. Nunca envia.")
    ap.add_argument("--arquivo", default=str(ARQUIVO))
    ap.add_argument("--criar", action="store_true", help="grava os rascunhos (sem isso, só mostra o que faria)")
    ap.add_argument("--teste", action="store_true",
                    help='cria um único rascunho, endereçado à própria conta, com "[TESTE]" no assunto (o primeiro escolhido; use --so)')
    ap.add_argument("--so", default="", help="números ou partes do título, separados por vírgula (ex.: 3,7,ALRN)")
    ap.add_argument("--de", default=REMETENTE, help=f"remetente (padrão: {REMETENTE})")
    ap.add_argument("--com-copias-opcionais", action="store_true", help='inclui as cópias marcadas como opcionais')
    ap.add_argument("--mesmo-destinatario", action="store_true",
                    help="sem rascunho com o mesmo assunto, atualiza o único rascunho para o mesmo destinatário (assunto mudou)")
    ap.add_argument("--sem-gmail", action="store_true", help="não conecta: só lê o arquivo e monta os e-mails")
    ap.add_argument("--mostrar", default="", help="mostra o e-mail montado (MIME) do rascunho com esse número ou nome")
    ap.add_argument("--config", default=str(CONFIG), help="pasta da credencial e do token")
    ap.add_argument("--conta", default=os.environ.get("CONTAS_GMAIL_CONTA", ""),
                    help="a conta do projeto, onde os rascunhos ficam; com tudo certo, fica gravada na pasta da credencial "
                         "(sem ela: a conta cujo endereço principal é o remetente)")
    ap.add_argument("--nova-autorizacao", action="store_true", help="refaz a autorização no navegador (o token atual vira .antigo)")
    ap.add_argument("--para-teste", default="", help="destinatário do rascunho de --teste (padrão: a própria conta)")
    a = ap.parse_args(argv)

    todos = ler(a.arquivo, a.com_copias_opcionais)
    escolhidos = escolher(todos, a.so)
    validos = [r for r in escolhidos if not r.fora]
    if a.teste:
        validos = validos[:1]
    s = None if a.sem_gmail else (sessao_fn or sessao)(Path(a.config), a.nova_autorizacao, a.conta)
    nome, principal = ("", None)
    por_chave, por_para, por_conversa = {}, {}, {}
    if s is not None:
        nome, principal = remetente_ok(s, a.de, a.conta, a.config)
        por_chave, por_para, por_conversa = rascunhos_existentes(s)
    print(f"Arquivo: {a.arquivo}: {len(todos)} blocos, {len(escolhidos)} escolhidos, {len(validos)} com e-mail."
          + ("" if s is None else f" Conta: {principal}. Remetente: {formataddr((nome, a.de)) if nome else a.de}."))
    for r in (validos if a.teste else escolhidos):  # no teste, só o rascunho de teste (o primeiro escolhido)
        rotulo = f"{r.numero}." if r.numero is not None else "-"
        print(f"\n{rotulo} {r.titulo}  [formato {r.formato}]")
        if r.fora:
            print(f"   fica de fora: {r.fora}")
            continue
        resposta, assunto = None, r.assunto
        if r.responde_a:
            if s is None:
                print(f"   resposta na conversa {r.responde_a}: o destinatário e o assunto saem da conversa (sem conectar, não lidos)")
            else:
                resposta = conversa(s, r.responde_a, {a.de.lower(), (principal or "").lower()})
                assunto = resposta["assunto"]
                print(f"   resposta na conversa {r.responde_a}")
        para = [a.para_teste or principal] if a.teste else (r.para or (resposta or {}).get("para") or [])
        prefixo = "[TESTE] " if a.teste else ""
        if resposta and a.teste:
            resposta = None  # o teste não entra na conversa
        print(f"   Para: {', '.join(para) or '(sai da conversa)'}" + ("" if a.teste or not r.cc else f"   Cc: {', '.join(r.cc)}"))
        print(f"   Assunto: {prefixo}{assunto or '(sai da conversa)'}")
        for av in r.avisos:
            print(f"   atenção: {av}")
        acao, id_ = "cria", None
        if s is not None and resposta:
            ids = por_conversa.get(r.responde_a, [])
            if ids:
                acao, id_ = "atualiza (rascunho que já está na conversa)", ids[0]
            print(f"   Gmail: {acao}" + (f" o rascunho {id_}" if id_ else " uma resposta nova na conversa"))
        elif s is not None:
            ids = por_chave.get(_chave(para, prefixo + assunto), [])
            if ids:
                acao, id_ = "atualiza", ids[0]
                if len(ids) > 1:
                    print(f"   atenção: {len(ids)} rascunhos com esse destinatário e assunto; atualiza o primeiro ({ids[0]})")
            else:
                outros = sorted({(i, x) for d in para for i, x in por_para.get(d.lower(), [])})
                if outros:
                    if a.mesmo_destinatario and len(outros) == 1:
                        acao, id_ = "atualiza (mesmo destinatário, assunto antigo)", outros[0][0]
                    else:
                        print("   atenção: já há rascunho para esse destinatário com outro assunto: "
                              + "; ".join(f'"{x}"' for _, x in outros[:3]) + " (com --mesmo-destinatario, atualiza se for um só)")
            print(f"   Gmail: {acao}" + (f" o rascunho {id_}" if id_ else " um rascunho novo"))
        msg = montar(r, a.de, nome, para=para if (a.teste or resposta) else None, prefixo=prefixo, assunto=assunto, resposta=resposta)
        if (a.criar or a.teste) and s is not None:
            g = gravar(s, msg, id_, r.responde_a if resposta else None)
            print(f"   gravado: rascunho {g.get('id')}")
    if a.mostrar:
        r = next(iter(escolher([x for x in todos if not x.fora], a.mostrar)), None)
        if r is None:
            print(f"\n--mostrar={a.mostrar}: nenhum rascunho com e-mail com esse número ou nome")
        else:
            print("\n" + "=" * 100 + "\n" + montar(r, a.de, nome).as_string(policy=SMTP.clone(linesep="\n")))
    if not (a.criar or a.teste) and s is not None:
        print("\nNada foi gravado (sem --criar). Nada é enviado em nenhum caso.")


if __name__ == "__main__":
    main()
