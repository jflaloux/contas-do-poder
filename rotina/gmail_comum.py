"""Parte comum dos scripts do Gmail da conta do projeto (rotina/rascunhos_gmail.py, caixa_gmail.py e enviar_gmail.py).

- sessao(): a autorização OAuth (credencial e token fora do repositório, em ~/.config/contas-do-poder/). Os scripts
  pedem o mesmo conjunto de escopos, para uma autorização servir a todos. Um token sem algum deles (de uma versão antiga)
  não é usado: o script para e diz para refazer a autorização (--nova-autorizacao).
- pedir(): toda chamada à API passa por aqui, e aqui se recusa qualquer endereço terminado em /send. Nenhum script marca
  como lido, arquiva ou apaga. A única exceção ao envio é enviar_aprovado(), usada só por enviar_gmail.py, que só envia
  com a variável APROVACAO=1 no ambiente (o painel dos agentes a põe depois da confirmação de quem aprova, numa janela
  do macOS).
- conta_ok(): confere, antes de ler ou gravar qualquer coisa, que o token é da conta do projeto (users.getProfile e
  "Enviar e-mail como"). A conta pessoal de quem roda é recusada.

Escopos: gmail.compose (rascunhos e o envio aprovado no painel; o Google não tem escopo de rascunho que não permita
também enviar), gmail.settings.basic (a lista de remetentes) e gmail.readonly (ler a caixa e as conversas). Nada de
gmail.modify.
"""
import json
import os
import re
import sys
from pathlib import Path

CONFIG = Path.home() / ".config" / "contas-do-poder"
REMETENTE = "contato@contasdopoder.com"  # o contato público do projeto
ESCOPOS = ["https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.settings.basic",
           "https://www.googleapis.com/auth/gmail.readonly"]
API = "https://gmail.googleapis.com/gmail/v1/users/me"
CONTA_ARQ = "conta-do-projeto"  # na pasta da credencial: a conta do projeto, gravada no primeiro uso com --conta


def comando_nova(script):
    return (f".venv/bin/python rotina/{script} --nova-autorizacao (o token atual vira gmail-token.json.antigo; no navegador, "
            "escolha a conta do projeto)")


def _escopos_do_token(arq):
    try:
        info = json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    esc = info.get("scopes") or []
    return set(esc.split() if isinstance(esc, str) else esc)


def sessao(config, nova=False, conta="", script="rascunhos_gmail.py", interativo=True):
    """Sessão autorizada no Gmail. Só na primeira vez ou com `nova` (aí o token que existe vira gmail-token.json.antigo),
    imprime o endereço da autorização numa linha própria, para colar no Chrome da conta do projeto (o script não abre
    navegador). Um token sem todos os ESCOPOS não é usado: para e diz o que rodar."""
    config = Path(config)
    cred_arq, token_arq = config / "gmail-credencial.json", config / "gmail-token.json"
    if nova and token_arq.exists():
        token_arq.replace(token_arq.with_suffix(".json.antigo"))
    if token_arq.exists():
        faltam = [e.rsplit("/", 1)[-1] for e in ESCOPOS if e not in _escopos_do_token(token_arq)]
        if faltam:
            sys.exit(f"O token atual ({token_arq}) não tem a permissão {', '.join(faltam)}, que os scripts do Gmail pedem agora. "
                     f"Nada foi lido nem gravado.\nRefaça a autorização uma vez: {comando_nova(script)}.")
    try:
        from google.auth.transport.requests import AuthorizedSession, Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("Faltam as bibliotecas do Google: .venv/bin/pip install -r rotina/requirements-gmail.txt")
    cred = Credentials.from_authorized_user_file(str(token_arq), ESCOPOS) if token_arq.exists() else None
    if cred and cred.expired and cred.refresh_token:
        cred.refresh(Request())
    if not cred or not cred.valid:
        if not interativo:  # chamado pelo painel: sem terminal para colar o endereço da autorização
            sys.exit("Sem autorização válida no Gmail. No terminal: .venv/bin/python rotina/caixa_gmail.py --nova-autorizacao")
        if not cred_arq.exists():
            sys.exit(f"Falta a credencial OAuth em {cred_arq} (o arquivo JSON do cliente \"App para computador\" do Google Cloud).")
        # o navegador aberto pelo script deu erro 400 do Google; o endereço colado no Chrome da conta do projeto funciona
        extra = {"login_hint": conta} if conta else {}
        cred = InstalledAppFlow.from_client_secrets_file(str(cred_arq), ESCOPOS).run_local_server(
            port=0, open_browser=False, prompt="select_account",
            authorization_prompt_message=("\nCopie este endereço e cole no Chrome em que a conta do projeto está aberta; escolha a "
                                          "conta do projeto (a que envia como " + REMETENTE + "); ao final, a página de localhost "
                                          "avisa que terminou.\n\n{url}\n"),
            success_message="A autorização terminou. Pode fechar esta aba e voltar ao terminal.", **extra)
    config.mkdir(parents=True, exist_ok=True)
    token_arq.write_text(cred.to_json(), encoding="utf-8")
    os.chmod(token_arq, 0o600)
    return AuthorizedSession(cred)


def pedir(s, metodo, caminho, **kw):
    """Uma chamada à API do Gmail. Recusa envio: nenhum caminho terminado em /send passa daqui."""
    if re.search(r"/send(\b|$)", caminho) or caminho.split("?")[0].rstrip("/").endswith("send"):
        raise RuntimeError("estes scripts não enviam e-mails")
    r = s.request(metodo, API + caminho, timeout=60, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"Gmail {metodo} {caminho}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


APROVACAO = "CDP_PAINEL_APROVADO"  # posta pelo painel dos agentes depois da confirmação de quem aprova o envio


def enviar_aprovado(s, mensagem):
    """A única chamada de envio dos scripts do Gmail (só enviar_gmail.py a usa): users.messages.send, com a mensagem
    {"raw": ..., "threadId": ...}. Recusa sem APROVACAO=1 no ambiente."""
    if os.environ.get(APROVACAO) != "1":
        raise RuntimeError("envio recusado: falta a aprovação do painel (" + APROVACAO + "=1)")
    r = s.request("POST", API + "/messages/send", timeout=60, json=mensagem)
    if r.status_code >= 400:
        raise RuntimeError(f"Gmail POST /messages/send: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


def conta_ok(s, endereco, conta_arg="", config=None, script="rascunhos_gmail.py", nada="Nada foi lido nem gravado."):
    """(nome de exibição do remetente, conta do token). Confere que o token é da conta do projeto:
    - `endereco` está em "Enviar e-mail como" como endereço principal ou como alias verificado;
    - a conta do token (users.getProfile) é a do projeto: a de --conta, ou a gravada em `config`/conta-do-projeto, ou,
      sem nenhuma das duas, a conta em que `endereco` é o endereço principal.
    Com --conta e tudo certo, a conta fica gravada (permissão 600) e as próximas vezes não precisam de --conta; uma
    conta diferente da gravada (a pessoal, por exemplo) é recusada. Para com uma mensagem clara."""
    refazer = "Para refazer a autorização com a conta do projeto: " + comando_nova(script) + "."
    arq = Path(config) / CONTA_ARQ if config else None
    gravada = arq.read_text(encoding="utf-8").strip() if arq and arq.exists() else ""
    esperada = conta_arg or gravada
    conta = pedir(s, "GET", "/profile").get("emailAddress", "")
    lista = pedir(s, "GET", "/settings/sendAs").get("sendAs", [])
    x = next((x for x in lista if x.get("sendAsEmail", "").lower() == endereco.lower()), None)
    if x is None:
        sys.exit(f"O token é da conta {conta}, que não tem {endereco} em \"Enviar e-mail como\". {nada}\n{refazer}")
    if not (x.get("isPrimary") or x.get("verificationStatus") == "accepted"):
        sys.exit(f"{endereco} está na conta {conta}, mas não verificado (situação: {x.get('verificationStatus')}). {nada}")
    if esperada and conta.lower() != esperada.lower():
        origem = "--conta" if conta_arg else f"a conta do projeto gravada em {arq}"
        sys.exit(f"O token é da conta {conta}, e não de {esperada} ({origem}). {nada}\n{refazer}")
    if not esperada and not (x.get("isPrimary") or conta.lower() == endereco.lower()):
        sys.exit(f"O token é da conta {conta}, em que {endereco} é um alias verificado, não o endereço principal. {nada}\n"
                 f"Se esta é a conta do projeto, rode uma vez com --conta={conta}: a conta fica gravada e as próximas vezes "
                 f"não precisam disso.\nSe não é (uma conta pessoal, por exemplo), refaça a autorização: {comando_nova(script)}.")
    if conta_arg and arq and conta_arg.lower() != gravada.lower():
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(conta + "\n", encoding="utf-8")
        os.chmod(arq, 0o600)
        print(f"Conta do projeto gravada em {arq}: {conta} (as próximas vezes não precisam de --conta).")
    return x.get("displayName") or "", conta
