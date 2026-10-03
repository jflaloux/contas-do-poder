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
Escopos: gmail.compose (criar, ler e atualizar rascunhos; o Google não tem um escopo de rascunho que não permita também
enviar) e gmail.settings.basic (ler a lista de remetentes; não dá acesso ao conteúdo dos e-mails).
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

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "RASCUNHOS-DIVULGACAO.md"
CONFIG = Path.home() / ".config" / "contas-do-poder"
REMETENTE = "contato@contasdopoder.com"  # o contato público do projeto (o From de todos os rascunhos)
# endereços do projeto que viram link mesmo escritos sem https:// (com ou sem caminho). Os de fora só viram link
# escritos por inteiro, com https:// (o script não adivinha se o site precisa de "www.")
NOSSOS = ("contasdopoder.com", "github.com/jflaloux/contas-do-poder")
ESCOPOS = ["https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.settings.basic"]
API = "https://gmail.googleapis.com/gmail/v1/users/me"

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
    if not r.fora and not r.para:
        r.fora = "sem destinatário"
    if not r.fora and not r.assunto:
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


def montar(r, remetente, nome_remetente="", para=None, prefixo=""):
    """O e-mail (multipart/alternative, UTF-8): texto puro e HTML."""
    msg = EmailMessage(policy=SMTP)
    msg["From"] = formataddr((nome_remetente, remetente)) if nome_remetente else remetente
    msg["To"] = ", ".join(para if para is not None else r.para)
    if r.cc and para is None:
        msg["Cc"] = ", ".join(r.cc)
    msg["Subject"] = prefixo + r.assunto
    msg.set_content(texto_puro(r.corpo), subtype="plain", charset="utf-8", cte="quoted-printable")
    msg.add_alternative(html_do_corpo(r.corpo), subtype="html", charset="utf-8", cte="quoted-printable")
    return msg


# ------------------------------------------------------------------------------------------------------- Gmail
def sessao(config, nova=False, conta=""):
    """Sessão autorizada no Gmail (abre o navegador na primeira vez, com a escolha de conta). A credencial e o token ficam
    em `config`. Com `nova`, o token que existe vira gmail-token.json.antigo e a autorização é feita de novo."""
    try:
        from google.auth.transport.requests import AuthorizedSession, Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("Faltam as bibliotecas do Google: .venv/bin/pip install -r rotina/requirements-gmail.txt")
    cred_arq, token_arq = config / "gmail-credencial.json", config / "gmail-token.json"
    cred = None
    if nova and token_arq.exists():
        token_arq.replace(token_arq.with_suffix(".json.antigo"))
    if token_arq.exists():
        cred = Credentials.from_authorized_user_file(str(token_arq), ESCOPOS)
    if cred and cred.expired and cred.refresh_token:
        cred.refresh(Request())
    if not cred or not cred.valid or not set(ESCOPOS) <= set(cred.scopes or []):
        if not cred_arq.exists():
            sys.exit(f"Falta a credencial OAuth em {cred_arq} (o arquivo JSON do cliente \"App para computador\" do Google Cloud).")
        print("Abrindo o navegador para a autorização: escolha a conta do projeto (a que envia como " + REMETENTE + ").")
        extra = {"login_hint": conta} if conta else {}
        cred = InstalledAppFlow.from_client_secrets_file(str(cred_arq), ESCOPOS).run_local_server(port=0, prompt="select_account", **extra)
    config.mkdir(parents=True, exist_ok=True)
    token_arq.write_text(cred.to_json(), encoding="utf-8")
    os.chmod(token_arq, 0o600)
    return AuthorizedSession(cred)


def _pedir(s, metodo, caminho, **kw):
    if re.search(r"/send(\b|$)", caminho) or caminho.rstrip("/").endswith("send"):
        raise RuntimeError("este script não envia e-mails")
    r = s.request(metodo, API + caminho, timeout=60, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"Gmail {metodo} {caminho}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


COMANDO_NOVA = (".venv/bin/python rotina/rascunhos_gmail.py --nova-autorizacao (o token atual vira gmail-token.json.antigo; "
                "no navegador, escolha a conta do projeto)")
REFAZER = "Para refazer a autorização com a conta do projeto: " + COMANDO_NOVA + "."
CONTA_ARQ = "conta-do-projeto"  # na pasta da credencial: a conta do projeto, gravada no primeiro uso com --conta


def remetente_ok(s, endereco, conta_arg="", config=None):
    """(nome de exibição, conta do token). Confere, antes de qualquer gravação, que o token é da conta do projeto:
    - `endereco` está em "Enviar e-mail como" como endereço principal ou como alias verificado;
    - a conta do token (users.getProfile) é a do projeto: a de --conta, ou a gravada em `config`/conta-do-projeto, ou,
      sem nenhuma das duas, a conta em que `endereco` é o endereço principal.
    Com --conta e tudo certo, a conta fica gravada (permissão 600) e as próximas vezes não precisam de --conta; uma
    conta diferente da gravada (a pessoal, por exemplo) é recusada. Para com uma mensagem clara; nada é gravado no Gmail."""
    arq = Path(config) / CONTA_ARQ if config else None
    gravada = arq.read_text(encoding="utf-8").strip() if arq and arq.exists() else ""
    esperada = conta_arg or gravada
    conta = _pedir(s, "GET", "/profile").get("emailAddress", "")
    lista = _pedir(s, "GET", "/settings/sendAs").get("sendAs", [])
    x = next((x for x in lista if x.get("sendAsEmail", "").lower() == endereco.lower()), None)
    if x is None:
        sys.exit(f"O token é da conta {conta}, que não tem {endereco} em \"Enviar e-mail como\". Nenhum rascunho foi criado.\n{REFAZER}")
    if not (x.get("isPrimary") or x.get("verificationStatus") == "accepted"):
        sys.exit(f"{endereco} está na conta {conta}, mas não verificado (situação: {x.get('verificationStatus')}). "
                 f"Nenhum rascunho foi criado.")
    if esperada and conta.lower() != esperada.lower():
        origem = "--conta" if conta_arg else f"a conta do projeto gravada em {arq}"
        sys.exit(f"O token é da conta {conta}, e não de {esperada} ({origem}). Nenhum rascunho foi criado.\n{REFAZER}")
    if not esperada and not (x.get("isPrimary") or conta.lower() == endereco.lower()):
        sys.exit(f"O token é da conta {conta}, em que {endereco} é um alias verificado, não o endereço principal. Nenhum "
                 f"rascunho foi criado.\nSe esta é a conta do projeto, rode uma vez com --conta={conta}: a conta fica "
                 f"gravada e as próximas vezes não precisam disso.\nSe não é (uma conta pessoal, por exemplo), refaça a "
                 f"autorização: {COMANDO_NOVA}.")
    if conta_arg and arq and conta_arg.lower() != gravada.lower():
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(conta + "\n", encoding="utf-8")
        os.chmod(arq, 0o600)
        print(f"Conta do projeto gravada em {arq}: {conta} (as próximas vezes não precisam de --conta).")
    return x.get("displayName") or "", conta


def _chave(para, assunto):
    return frozenset(a.lower() for a in para), " ".join(assunto.split()).lower()


def rascunhos_existentes(s):
    """{(destinatários, assunto): [ids]} e {destinatário: [(id, assunto)]} dos rascunhos da conta."""
    por_chave, por_para, token = {}, {}, None
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
        token = d.get("nextPageToken")
        if not token:
            return por_chave, por_para


def gravar(s, msg, id_existente=None):
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    if id_existente:
        return _pedir(s, "PUT", f"/drafts/{id_existente}", json={"id": id_existente, "message": {"raw": raw}})
    return _pedir(s, "POST", "/drafts", json={"message": {"raw": raw}})


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
    por_chave, por_para = {}, {}
    if s is not None:
        nome, principal = remetente_ok(s, a.de, a.conta, a.config)
        por_chave, por_para = rascunhos_existentes(s)
    print(f"Arquivo: {a.arquivo}: {len(todos)} blocos, {len(escolhidos)} escolhidos, {len(validos)} com e-mail."
          + ("" if s is None else f" Conta: {principal}. Remetente: {formataddr((nome, a.de)) if nome else a.de}."))
    for r in (validos if a.teste else escolhidos):  # no teste, só o rascunho de teste (o primeiro escolhido)
        rotulo = f"{r.numero}." if r.numero is not None else "-"
        print(f"\n{rotulo} {r.titulo}  [formato {r.formato}]")
        if r.fora:
            print(f"   fica de fora: {r.fora}")
            continue
        para = [a.para_teste or principal] if a.teste else r.para
        prefixo = "[TESTE] " if a.teste else ""
        print(f"   Para: {', '.join(para)}" + ("" if a.teste or not r.cc else f"   Cc: {', '.join(r.cc)}"))
        print(f"   Assunto: {prefixo}{r.assunto}")
        for av in r.avisos:
            print(f"   atenção: {av}")
        acao, id_ = "cria", None
        if s is not None:
            ids = por_chave.get(_chave(para, prefixo + r.assunto), [])
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
        msg = montar(r, a.de, nome, para=para if a.teste else None, prefixo=prefixo)
        if (a.criar or a.teste) and s is not None:
            g = gravar(s, msg, id_)
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
