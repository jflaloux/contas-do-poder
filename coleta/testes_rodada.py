"""Testes de rotina/etapa-github.sh (tempo de cada etapa, prazo geral, códigos de saída, rodada retomada), do passo de
conferência do workflow, da rede de segurança (coleta/retomada.py, avisar-rodada.sh, o passo de salvar) e da conta do
orçamento, com um `python`, um `timeout` e um `gh` de mentira num PATH temporário. Não coleta nada nem abre a internet.

    python3 -m coleta.testes_rodada
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "rotina" / "etapa-github.sh"
WORKFLOW = RAIZ / ".github" / "workflows" / "atualizar-dados.yml"


def executar():
    falhas, total = [], 0

    def caso(nome, ok):
        nonlocal total
        total += 1
        if not ok:
            falhas.append(nome)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        # python de mentira: grava os argumentos e sai com STUB_RC; timeout de mentira: tira as opções e roda o resto
        (tmp / "bin" / "python").write_text('#!/bin/bash\necho "$@" >> "$RUNNER_TEMP/chamadas.txt"\nexit "${STUB_RC:-0}"\n')
        (tmp / "bin" / "timeout").write_text('#!/bin/bash\n[ "$1" = "-k" ] && shift 2\nshift\nexec "$@"\n')
        for f in (tmp / "bin").iterdir():
            f.chmod(0o755)

        def rodar(etapa, minutos, rc=0, essencial="", prazo_em=None):
            for f in ("etapas.txt", "chamadas.txt"):
                (tmp / f).unlink(missing_ok=True)
            env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp), "STUB_RC": str(rc)}
            env.pop("PRAZO_FIM", None)
            if prazo_em is not None:
                env["PRAZO_FIM"] = str(int(time.time()) + prazo_em)
            r = subprocess.run(["bash", str(SCRIPT), etapa, str(minutos), essencial], cwd=RAIZ, env=env, capture_output=True, text=True)
            ler = lambda f: (tmp / f).read_text().strip() if (tmp / f).exists() else ""
            return r.returncode, ler("etapas.txt"), ler("chamadas.txt"), r.stdout

        # o script nunca termina com erro, e anota código e duração
        for rc in (0, 1, 3, 5, 124, 137):
            sai, etapas, _, _ = rodar("tce", 10, rc=rc)
            caso(f"código {rc}: o script sai com 0", sai == 0)
            caso(f"código {rc}: anotado", re.fullmatch(rf"tce {rc} \d+", etapas) is not None)
        # o tempo máximo da etapa vai para --tempo-max (em segundos)
        _, _, chamadas, _ = rodar("senado", 10)
        caso("--tempo-max em segundos", chamadas == "coletar.py senado --tempo-max 600")
        # prazo geral: com PRAZO_FIM daqui a 80 min e reserva de 70, sobram 10 min: a etapa de 40 min recebe 10
        _, _, chamadas, _ = rodar("tce", 40, prazo_em=80 * 60)
        caso("o prazo geral encurta a etapa", re.fullmatch(r"coletar.py tce --tempo-max (5[89]\d|600)", chamadas) is not None)
        # sem sobra (menos de 2 min depois da reserva): pulada, e anotada
        sai, etapas, chamadas, _ = rodar("tce", 40, prazo_em=71 * 60)
        caso("sem sobra, a etapa é pulada", sai == 0 and chamadas == "" and etapas == "tce pulada-por-tempo 0")
        # etapa essencial ignora o prazo geral
        _, etapas, chamadas, _ = rodar("padronizar", 30, essencial="essencial", prazo_em=60)
        caso("essencial roda mesmo sem prazo", chamadas == "coletar.py padronizar --tempo-max 1800" and etapas.startswith("padronizar 0"))

    # o orçamento do workflow cabe no job (conta do pior caso do cabeçalho de etapa-github.sh)
    texto = WORKFLOW.read_text(encoding="utf-8")
    job = int(re.search(r"timeout-minutes: (\d+)", texto).group(1))
    prazo = int(re.search(r"PRAZO_FIM=\$\(\( \$\(date \+%s\) \+ (\d+) \* 60", texto).group(1))
    reserva = int(re.search(r'RESERVA_MIN="\$\{RESERVA_MIN:-(\d+)\}"', SCRIPT.read_text(encoding="utf-8")).group(1))
    essenciais = sum(int(m.group(1)) for m in re.finditer(r"etapa-github.sh \w+ (\d+) essencial", texto))
    caso("as etapas essenciais cabem na reserva (com 20 min para conferir e salvar)", essenciais + 20 <= reserva)
    pior = (prazo - reserva) + 3 + essenciais + 9 + 20
    caso(f"o pior caso ({pior} min) cabe no job ({job} min)", pior < job)

    # o passo de conferência recusa salvar com padronizar/site com erro ou etapa com código 5
    gate = re.search(r"grep -Eq '([^']+)' \"\$RUNNER_TEMP/etapas.txt\"", texto).group(1)
    for linha, deve in (("padronizar 1 12", True), ("site 2 3", True), ("camara 5 0", True), ("senado 5 2", True),
                        ("tce 3 9000", False), ("padronizar 0 100", False), ("camara 0 50", False), ("tce 124 9000", False),
                        ("fotos 15 90", False), ("site 0 10", False), ("bens pulada-por-tempo 0", False)):
        r = subprocess.run(["grep", "-Eq", gate], input=linha + "\n", text=True)
        caso(f"gate com {linha!r}", (r.returncode == 0) == deve)

    _retomada(caso)
    _avisar(caso, texto)
    _salvar(texto, caso)
    _estrutura(texto, caso)

    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


def _passo(texto, nome):
    """O script `run` do passo do workflow cujo nome começa com `nome` (sem a indentação do YAML)."""
    m = re.search(r"- name: " + re.escape(nome) + r"[^\n]*\n(?:        [^\n]*\n)*?        run: \|\n((?:          [^\n]*\n|\n)+)", texto)
    return re.sub(r"^          ", "", m.group(1), flags=re.M)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def _novo_repo(caminho, arquivos):
    caminho.mkdir(parents=True)
    _git(caminho, "init", "-q", "-b", "main")
    _git(caminho, "config", "user.email", "t@t")
    _git(caminho, "config", "user.name", "t")
    for arq, conteudo in arquivos.items():
        (caminho / arq).parent.mkdir(parents=True, exist_ok=True)
        (caminho / arq).write_text(conteudo)
    _git(caminho, "add", "-A")
    _git(caminho, "commit", "-q", "-m", "base")


def _recusa(funcao, *args, **kw):
    """A mensagem da Recusa que a função levanta (None se não levantar)."""
    from . import retomada
    try:
        funcao(*args, **kw)
    except retomada.Recusa as e:
        return str(e)
    return None


def _retomada(caso):
    import json
    import tarfile
    from . import retomada
    cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = tmp / "repo"
            _novo_repo(repo, {"dados/a.csv": "1\n", "dados/b.csv": "1\n", "dados/apagar.csv": "x\n", "site/dados/x.json": "{}",
                              "coleta/codigo.py": "ok\n", ".gitignore": "dados/brutos/\n"})
            inicio = _git(repo, "rev-parse", "HEAD")
            # a rodada: altera, apaga, cria, gera um bruto (ignorado), faz um commit (o Git do passo de salvar) e depois altera mais
            (repo / "dados/a.csv").write_text("2\n")
            (repo / "dados/apagar.csv").unlink()
            (repo / "dados/c.csv").write_text("novo\n")
            (repo / "dados/brutos").mkdir()
            (repo / "dados/brutos/camara.csv").write_text("bruto\n")
            (repo / "site/dados/x.json").write_text('{"a":1}')
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "commit da rodada (como o passo de salvar faz antes do push)")
            (repo / "dados/b.csv").write_text("2\n")
            (repo / "coleta/codigo.py").write_text("mudou\n")  # fora de dados/ e site/: não entra
            pasta = tmp / "pacote"
            m = retomada.guardar(pasta, inicio=inicio, raiz=repo)
            caso("guardar: pega o que já foi comitado e o que não foi", set(m["arquivos"]) == {"dados/a.csv", "dados/b.csv", "dados/c.csv", "site/dados/x.json"})
            caso("guardar: registra o apagado e o bruto", "dados/apagar.csv" in m["apagados"] and m["brutos"] == 1)
            caso("guardar: o código fora de dados e site não entra", "coleta/codigo.py" not in m["arquivos"])
            caso("guardar: manifesto com o commit de partida", m["base"] == inicio)
            os.chdir(cwd)

            def clone(nome):
                d = tmp / nome
                subprocess.run(["git", "clone", "-q", str(repo), str(d)], check=True, capture_output=True)
                _git(d, "checkout", "-q", inicio)
                _git(d, "config", "user.email", "t@t")
                _git(d, "config", "user.name", "t")
                return d

            nova = clone("nova")
            os.chdir(cwd)
            retomada.restaurar(pasta, raiz=nova)
            os.chdir(cwd)
            caso("restaurar: traz os arquivos, o bruto e apaga o que a rodada apagou",
                 (nova / "dados/a.csv").read_text() == "2\n" and (nova / "dados/c.csv").exists()
                 and (nova / "dados/brutos/camara.csv").exists() and not (nova / "dados/apagar.csv").exists()
                 and (nova / "site/dados/x.json").read_text() == '{"a":1}')

            # conflito em dados/ e também em site/dados/ (agora conta): recusa e não extrai nada
            for arq in ("dados/a.csv", "site/dados/x.json"):
                outra = clone("conflito-" + arq.replace("/", "-"))
                (outra / arq).write_text("mudou na main\n")
                _git(outra, "commit", "-q", "-am", "outra rodada")
                msg = _recusa(retomada.restaurar, pasta, raiz=outra)
                os.chdir(cwd)
                caso(f"restaurar: recusa se a main mudou {arq}", msg is not None and arq in msg and not (outra / "dados/c.csv").exists())

            # pacote adulterado ou quebrado: recusa antes de extrair qualquer coisa
            def pacote_com(nome, membros, manifesto=None):
                d = tmp / nome
                d.mkdir()
                with tarfile.open(d / "trabalho.tgz", "w:gz") as t:
                    for arcname, tipo, conteudo in membros:
                        info = tarfile.TarInfo(arcname)
                        if tipo == "link":
                            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                            t.addfile(info)
                        else:
                            import io
                            dados = conteudo.encode()
                            info.size = len(dados)
                            t.addfile(info, io.BytesIO(dados))
                man = manifesto or {"base": inicio, "arquivos": {n: None for n, _, _ in membros if not n.startswith("dados/brutos/")},
                                    "brutos": sum(1 for n, _, _ in membros if n.startswith("dados/brutos/")), "apagados": {}}
                (d / "manifesto.json").write_text(json.dumps(man))
                return d

            casos = (
                ("caminho com ..", [("dados/../coleta/x.py", "f", "x")], "inseguro"),
                ("caminho absoluto", [("/tmp/x", "f", "x")], "inseguro"),
                ("fora de dados e site", [("coleta/x.py", "f", "x")], "fora de dados/ e site/"),
                ("link simbólico", [("dados/l.csv", "link", "")], "não é arquivo comum"),
            )
            for nome, membros, trecho in casos:
                alvo = clone("adulterado-" + nome.replace(" ", "-"))
                msg = _recusa(retomada.restaurar, pacote_com("p-" + nome.replace(" ", "-"), membros), raiz=alvo)
                os.chdir(cwd)
                caso(f"restaurar: recusa {nome}", msg is not None and trecho in msg)
            # manifesto diferente do pacote
            alvo = clone("manifesto-diferente")
            p = pacote_com("p-man", [("dados/z.csv", "f", "z")], manifesto={"base": inicio, "arquivos": {"dados/outro.csv": None}, "brutos": 0, "apagados": {}})
            msg = _recusa(retomada.restaurar, p, raiz=alvo)
            os.chdir(cwd)
            caso("restaurar: recusa pacote diferente do manifesto", msg is not None and "manifesto" in msg and not (alvo / "dados/z.csv").exists())
            # tar quebrado (cortado no meio)
            alvo = clone("tar-quebrado")
            quebrado = tmp / "quebrado"
            quebrado.mkdir()
            dados = (pasta / "trabalho.tgz").read_bytes()
            (quebrado / "trabalho.tgz").write_bytes(dados[: len(dados) // 2])
            (quebrado / "manifesto.json").write_text((pasta / "manifesto.json").read_text())
            msg = _recusa(retomada.restaurar, quebrado, raiz=alvo)
            os.chdir(cwd)
            caso("restaurar: recusa pacote cortado e não deixa extração parcial", msg is not None and not (alvo / "dados/c.csv").exists())
            caso("restaurar: recusa pasta sem pacote", _recusa(retomada.restaurar, tmp / "vazia", raiz=nova) is not None)
            os.chdir(cwd)
            # sem nada para guardar
            vazio = tmp / "repo-vazio"
            _novo_repo(vazio, {"dados/a.csv": "1\n"})
            caso("guardar: nada alterado, nada guardado", retomada.guardar(tmp / "p-vazio", inicio=_git(vazio, "rev-parse", "HEAD"), raiz=vazio) is None)
    finally:
        os.chdir(cwd)


def _avisar(caso, texto):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        # gh de mentira: grava os comandos; GH_API / GH_LIST / GH_CREATE dizem o que responde (ou falha, com "ERRO")
        (tmp / "bin/gh").write_text(
            '#!/bin/bash\necho "$@" >> "$RUNNER_TEMP/gh.txt"\n'
            'case "$1 $2" in\n'
            '"api repos"*) [ "${GH_API:-0}" = ERRO ] && { echo falhou; exit 1; }; echo "${GH_API:-0}";;\n'
            '"issue list") [ "${GH_LIST:-}" = ERRO ] && { echo falhou; exit 1; }; echo "${GH_LIST:-}";;\n'
            '"issue create") [ "${GH_CREATE:-}" = ERRO ] && exit 1;;\n'
            '"issue comment") [ "${GH_COMENTA:-}" = ERRO ] && exit 1;;\n'
            'esac\n')
        (tmp / "bin/gh").chmod(0o755)
        env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp), "GITHUB_RUN_ID": "123",
               "GITHUB_STEP_SUMMARY": str(tmp / "resumo.md"), "GITHUB_REPOSITORY": "o/r", "GH_TOKEN": "x"}

        def avisar(salvou=False, motivo="", guardado="sim", **extra):
            for f in tmp.iterdir():
                if f.is_file():
                    f.unlink()
            if salvou:
                (tmp / "salvo").write_text("")
            if motivo:
                (tmp / "motivo.txt").write_text(motivo)
            r = subprocess.run(["bash", str(RAIZ / "rotina/avisar-rodada.sh")], cwd=RAIZ, capture_output=True, text=True,
                               env={**env, "TRABALHO_GUARDADO": guardado, **extra})
            ler = lambda f: (tmp / f).read_text() if (tmp / f).exists() else ""
            return r.returncode, ler("resumo.md"), ler("gh.txt"), r.stdout

        rc, resumo, gh, _ = avisar(salvou=True)
        caso("aviso: rodada salva diz isso e não consulta o gh", rc == 0 and "Rodada salva" in resumo and gh == "")
        rc, resumo, gh, _ = avisar(motivo="a conferência passou do limite", GH_API="3")
        caso("aviso: não salvou diz o motivo, onde está o pacote e como retomar", rc == 0 and "NADA FOI SALVO" in resumo and "a conferência passou do limite" in resumo
             and "trabalho-123" in resumo and "run_id = 123" in resumo)
        caso("aviso: o robô salvou na semana, não abre issue", "issue create" not in gh and "issue comment" not in gh)
        rc, resumo, gh, _ = avisar(motivo="x", GH_API="0")
        caso("aviso: mais de uma semana sem salvar abre a issue", "issue create" in gh)
        rc, resumo, gh, _ = avisar(motivo="x", GH_API="0", GH_LIST="7")
        caso("aviso: issue aberta recebe comentário em vez de outra", "issue comment 7" in gh and "issue create" not in gh)
        rc, resumo, gh, out = avisar(motivo="x", GH_API="ERRO")
        caso("aviso: gh api falhou: avisa e não abre issue", rc == 0 and "issue create" not in gh and "::warning::" in out and "NADA FOI SALVO" in resumo)
        rc, resumo, gh, out = avisar(motivo="x", GH_API="0", GH_LIST="ERRO")
        caso("aviso: gh issue list falhou: não duplica", "issue create" not in gh and "::warning::" in out)
        rc, resumo, gh, out = avisar(motivo="x", GH_API="0", GH_CREATE="ERRO")
        caso("aviso: criar a issue falhou: avisa", rc == 0 and "::warning::" in out)
        rc, resumo, gh, out = avisar(motivo="x", guardado="nao")
        caso("aviso: sem pacote guardado não manda retomar", "run_id" not in resumo and "não foi guardado" in resumo)
        rc, resumo, gh, _ = avisar(motivo="x", GH_TOKEN="")
        caso("aviso: sem token, só o resumo", rc == 0 and gh == "" and "NADA FOI SALVO" in resumo)


def _salvar(texto, caso):
    """O passo "Salvar os números novos" do workflow contra um repositório remoto de verdade (um bare local): commit, rebase,
    conferência de novo e push, com um `python` de mentira que faz o papel de `coletar.py conferir` e `montar`."""
    passo = _passo(texto, "Salvar os números novos")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        # python de mentira: "conferir" reescreve o relatório rastreado (como o de verdade) e sai com STUB_RC; "montar" sai com STUB_MONTAR
        (tmp / "bin/python").write_text(
            '#!/bin/bash\ncase "$2" in\nconferir) date +%N > dados/processados/conferencia.md; exit "${STUB_RC:-0}";;\n'
            'montar) echo montado >> dados/processados/montar.txt; exit "${STUB_MONTAR:-0}";;\nesac\n')
        (tmp / "bin/python").chmod(0o755)
        base = {"dados/processados/conferencia.md": "antigo\n", "dados/processados/situacao.md": "s\n", "dados/camara/a.csv": "1\n",
                "dados/portal_transparencia/.gitkeep": "", "dados/municipios/.gitkeep": "", "dados/municipios_tce/.gitkeep": "",
                "dados/judiciario/.gitkeep": "", "dados/governadores/.gitkeep": "", "dados/atividade/.gitkeep": "", "dados/bens/.gitkeep": "",
                "dados/assembleias/.gitkeep": "", "dados/referencia/renda_trabalho.json": "{}", "site/dados/s.json": "{}", "site/fotos/f.txt": "f"}

        def cenario(nome, rejeitar_primeiro_push=False, outra_rodada=None, stub_rc=0, stub_montar=0):
            origem = tmp / f"{nome}.git"
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origem)], check=True)
            semente = tmp / f"{nome}-semente"
            _novo_repo(semente, base)
            _git(semente, "remote", "add", "origin", str(origem))
            _git(semente, "push", "-q", "origin", "main")
            if rejeitar_primeiro_push:  # a primeira tentativa de push é recusada (outra rodada enviou no meio)
                hook = origem / "hooks/pre-receive"
                hook.write_text(f'#!/bin/bash\nif [ ! -f "{tmp}/{nome}.recusou" ]; then touch "{tmp}/{nome}.recusou"; echo recusado >&2; exit 1; fi\n')
                hook.chmod(0o755)
            rodada = tmp / f"{nome}-rodada"
            subprocess.run(["git", "clone", "-q", str(origem), str(rodada)], check=True, capture_output=True)
            (rodada / "dados/camara/a.csv").write_text("2\n")  # o que a coleta mudou
            (rodada / "site/dados/s.json").write_text('{"github":1}')
            if outra_rodada:  # a rodada do Brasil enviou antes
                outro = tmp / f"{nome}-brasil"
                subprocess.run(["git", "clone", "-q", str(origem), str(outro)], check=True, capture_output=True)
                _git(outro, "config", "user.email", "b@b")
                _git(outro, "config", "user.name", "b")
                for arq, conteudo in outra_rodada.items():
                    (outro / arq).write_text(conteudo)
                _git(outro, "commit", "-q", "-am", "rodada do Brasil")
                _git(outro, "push", "-q", "origin", "main")
            temp = tmp / f"{nome}-temp"
            temp.mkdir()
            env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(temp), "STUB_RC": str(stub_rc),
                   "STUB_MONTAR": str(stub_montar), "GIT_CONFIG_GLOBAL": "/dev/null"}
            r = subprocess.run(["bash", "-e", "-c", passo], cwd=rodada, env=env, capture_output=True, text=True)
            remoto = subprocess.run(["git", "--git-dir", str(origem), "show", "main:dados/camara/a.csv"], capture_output=True, text=True).stdout
            motivo = (temp / "motivo.txt").read_text() if (temp / "motivo.txt").exists() else ""
            return r, remoto, (temp / "salvo").exists(), motivo, rodada

        r, remoto, salvo, motivo, _ = cenario("normal")
        caso("salvar: caso normal envia e marca como salvo", r.returncode == 0 and remoto == "2\n" and salvo)
        r, remoto, salvo, motivo, rodada = cenario("brasil", outra_rodada={"dados/camara/a.csv": "1\n", "site/dados/s.json": '{"brasil":1}'})
        montou = (rodada / "dados/processados/montar.txt").exists() and "montado" in (rodada / "dados/processados/montar.txt").read_text()
        caso("salvar: conflito nos arquivos gerados com a rodada do Brasil: fica a versão de lá, refaz com montar e envia",
             r.returncode == 0 and salvo and montou and remoto == "2\n")
        r, remoto, salvo, motivo, _ = cenario("recusado", rejeitar_primeiro_push=True)
        caso("salvar: push recusado uma vez (conferência reescreveu o relatório): o pull --rebase seguinte funciona e a 2ª tentativa envia",
             r.returncode == 0 and remoto == "2\n" and salvo)
        r, remoto, salvo, motivo, _ = cenario("conferencia-final-falha", stub_rc=4)
        caso("salvar: a conferência da árvore final falha: nada é enviado, com o motivo", r.returncode != 0 and remoto == "1\n" and not salvo and "conferência da árvore final" in motivo)
        r, remoto, salvo, motivo, _ = cenario("montar-falha", outra_rodada={"dados/camara/a.csv": "1\n", "site/dados/s.json": '{"brasil":1}'}, stub_montar=1)
        caso("salvar: montar falha depois do rebase: nada é enviado, com o motivo", r.returncode != 0 and remoto == "1\n" and not salvo and "não foram refeitos" in motivo)
        r, remoto, salvo, motivo, _ = cenario("nada")  # nada mudou: reescreve a.csv igual
        # (o cenário já muda a.csv; aqui só garante que o marcador existe no caso normal)
        caso("salvar: o relatório da conferência final fica fora da árvore", (tmp / "normal-temp/conferencia-final.md").exists())


def _estrutura(texto, caso):
    caso("o pacote da coleta vai para o cache privado, não para artefato público", "actions/cache/save@v4" in texto
         and "key: trabalho-${{ github.run_id }}" in texto and "upload-artifact" in texto and texto.count("upload-artifact") == 1)
    caso("o único artefato é o relatório da conferência", "name: conferencia" in texto and "trabalho-da-rodada" not in texto)
    caso("retomar busca o cache pela chave da rodada e falha se não achar", "key: trabalho-${{ inputs.run_id }}" in texto and "fail-on-cache-miss: true" in texto)
    caso("o ponto de retomada vem antes da conferência", texto.index("Ponto de retomada - guardar") < texto.index("Conferir com os sites oficiais"))
    caso("conferir e salvar têm prazo próprio", texto.count("timeout-minutes: 20") == 2)
    caso("concurrency fila sem cancelar", "group: atualizar-dados" in texto and "cancel-in-progress: false" in texto)
    caso("a suíte de testes roda no workflow", all(t in texto for t in ("coleta.testes_pandas", "coleta.testes_gravacao", "coleta.testes_disjuntor", "coleta.testes_rodada", "coleta.testes_fontes")))


if __name__ == "__main__":
    sys.exit(executar())
