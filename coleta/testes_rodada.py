"""Testes de rotina/etapa-github.sh (tempo de cada etapa, prazo geral, códigos de saída, rodada retomada), do passo de
conferência do workflow, da rede de segurança (guardar-trabalho.sh, retomar-trabalho.sh, avisar-rodada.sh) e da conta do
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

    rede_de_seguranca(texto, caso)

    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


def _passo(texto, nome):
    """O script `run` do passo do workflow cujo nome começa com `nome` (sem a indentação do YAML)."""
    m = re.search(r"- name: " + re.escape(nome) + r"[^\n]*\n(?:        [^\n]*\n)*?        run: \|\n((?:          [^\n]*\n|\n)+)", texto)
    return re.sub(r"^          ", "", m.group(1), flags=re.M)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def rede_de_seguranca(texto, caso):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_ = tmp / "bin"
        bin_.mkdir()
        # python de mentira (sai com STUB_RC), gh de mentira (grava os comandos; responde a conclusão da rodada anterior)
        (bin_ / "python").write_text('#!/bin/bash\nexit "${STUB_RC:-0}"\n')
        (bin_ / "gh").write_text('#!/bin/bash\necho "$@" >> "$RUNNER_TEMP/gh.txt"\n'
                                 'case "$1 $2" in\n"run list") echo "${GH_ANTERIOR:-success}";;\n'
                                 '"issue list") echo "${GH_ISSUE:-}";;\nesac\n')
        for f in bin_.iterdir():
            f.chmod(0o755)
        temp = tmp / "temp"
        temp.mkdir()
        env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "RUNNER_TEMP": str(temp), "GITHUB_RUN_ID": "123",
               "GITHUB_STEP_SUMMARY": str(temp / "resumo.md"), "GITHUB_REPOSITORY": "o/r", "GH_TOKEN": "x"}

        def sh(script, cwd=RAIZ, **extra):
            return subprocess.run(["bash", "-c", script], cwd=cwd, env={**env, **extra}, capture_output=True, text=True)

        def limpar():
            for f in temp.iterdir():
                if f.is_file():
                    f.unlink()
                else:
                    subprocess.run(["rm", "-rf", str(f)])

        # --- o passo "Conferir com os sites oficiais": motivo gravado, e nada é salvo nos casos ruins
        passo = _passo(texto, "Conferir com os sites oficiais")
        for etapas, rc, deve_falhar, parte in (
                ("camara 0 100\npadronizar 0 5\nsite 0 5", 0, False, ""),
                ("camara 3 100\ntce 124 100\nbens pulada-por-tempo 0\npadronizar 0 5", 0, False, ""),
                ("camara 0 1\npadronizar 1 2\nsite 0 5", 0, True, "padronizar"),
                ("camara 0 1\npadronizar 0 2\nsite 2 5", 0, True, "site"),
                ("camara 5 1\nsenado 5 1\npadronizar 0 2", 0, True, "legislatura"),
                ("a 1 1\nb 1 1\nc 2 1\nd 1 1\npadronizar 0 2\nsite 0 2", 0, True, "4 etapas terminaram com erro"),
                ("a 1 1\nb 1 1\nc 2 1\npadronizar 0 2\nsite 0 2", 0, False, ""),
                ("camara 0 1\npadronizar 0 2\nsite 0 5", 4, True, "limite de alertas")):
            limpar()
            (temp / "etapas.txt").write_text(etapas + "\n")
            r = sh(passo, STUB_RC=str(rc))
            motivo = (temp / "motivo.txt").read_text() if (temp / "motivo.txt").exists() else ""
            caso(f"conferir {etapas.splitlines()[:2]} rc={rc}: {'recusa' if deve_falhar else 'passa'}", (r.returncode != 0) == deve_falhar)
            caso(f"conferir {etapas.splitlines()[:2]}: motivo certo ({parte!r})", (parte in motivo) if deve_falhar else motivo == "")

        # --- guardar / retomar, num repositório de mentira
        repo = tmp / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        for arq, conteudo in (("dados/a.csv", "1\n"), ("dados/b.csv", "1\n"), ("site/dados/x.json", "{}"), (".gitignore", "dados/brutos/\n")):
            (repo / arq).parent.mkdir(parents=True, exist_ok=True)
            (repo / arq).write_text(conteudo)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        # a rodada que falhou: alterou a.csv, criou c.csv e um bruto (ignorado), e não salvou
        (repo / "dados/a.csv").write_text("2\n")
        (repo / "dados/c.csv").write_text("novo\n")
        (repo / "dados/brutos").mkdir()
        (repo / "dados/brutos/camara.csv").write_text("bruto\n")
        limpar()
        sh(f"cd {repo} && bash {RAIZ}/rotina/guardar-trabalho.sh", cwd=repo)
        pacote = temp / "trabalho"
        caso("guardar: faz o pacote e o base.txt", (pacote / "trabalho.tgz").exists() and (pacote / "base.txt").exists())
        base = (pacote / "base.txt").read_text()
        caso("guardar: base.txt traz o commit e os arquivos alterados e novos", base.startswith("base ") and "dados/a.csv" in base and "dados/c.csv" in base)
        caso("guardar: não traz o que não mudou", "dados/b.csv" not in base)
        caso("guardar: o bruto vai no pacote, mas fora do base.txt", "brutos" not in base)
        limpar()
        (temp / "salvo").write_text("")
        sh(f"cd {repo} && bash {RAIZ}/rotina/guardar-trabalho.sh", cwd=repo)
        caso("guardar: se a rodada salvou, não guarda nada", not (temp / "trabalho").exists())

        # retomar numa cópia limpa da main
        limpar()
        sh(f"cd {repo} && bash {RAIZ}/rotina/guardar-trabalho.sh", cwd=repo)
        nova = tmp / "nova"
        subprocess.run(["git", "clone", "-q", str(repo), str(nova)], check=True, capture_output=True)
        (nova / ".git/info").mkdir(exist_ok=True)
        r = sh(f"cd {nova} && bash {RAIZ}/rotina/retomar-trabalho.sh {temp / 'trabalho'}", cwd=nova)
        caso("retomar: restaura sem conflito", r.returncode == 0 and (nova / "dados/a.csv").read_text() == "2\n"
             and (nova / "dados/c.csv").exists() and (nova / "dados/brutos/camara.csv").exists())
        # a main mudou o mesmo arquivo de dados desde então: recusa e não mexe
        (nova / "dados/a.csv").write_text("3\n")
        (nova / "dados/c.csv").unlink()
        _git(nova, "config", "user.email", "t@t")
        _git(nova, "config", "user.name", "t")
        _git(nova, "commit", "-q", "-am", "outra rodada mexeu em a.csv")
        r = sh(f"cd {nova} && bash {RAIZ}/rotina/retomar-trabalho.sh {temp / 'trabalho'}", cwd=nova)
        caso("retomar: recusa se a main mudou o mesmo arquivo", r.returncode != 0 and "dados/a.csv" in r.stdout and (nova / "dados/a.csv").read_text() == "3\n")
        # mudança só em arquivo gerado (site/dados) não conta como conflito
        (repo / "site/dados/x.json").write_text('{"a":1}')
        limpar()
        sh(f"cd {repo} && bash {RAIZ}/rotina/guardar-trabalho.sh", cwd=repo)
        outra = tmp / "outra"
        subprocess.run(["git", "clone", "-q", str(repo), str(outra)], check=True, capture_output=True)
        # (o clone traz o HEAD da base, sem as alterações do repo de origem, que não foram commitadas)
        (outra / "site/dados/x.json").write_text('{"b":2}')
        _git(outra, "config", "user.email", "t@t")
        _git(outra, "config", "user.name", "t")
        _git(outra, "commit", "-q", "-am", "x.json refeito pela outra rodada")
        r = sh(f"cd {outra} && bash {RAIZ}/rotina/retomar-trabalho.sh {temp / 'trabalho'}", cwd=outra)
        caso("retomar: arquivo gerado (site/dados) alterado na main não é conflito", r.returncode == 0)

        # --- avisar-rodada: resumo e issue
        def avisar(salvou=False, motivo="", artefato=True, anterior="success", issue=""):
            limpar()
            if salvou:
                (temp / "salvo").write_text("")
            if motivo:
                (temp / "motivo.txt").write_text(motivo)
            if artefato:
                (temp / "trabalho").mkdir()
                (temp / "trabalho/trabalho.tgz").write_text("x")
            r = sh(f"bash {RAIZ}/rotina/avisar-rodada.sh", GH_ANTERIOR=anterior, GH_ISSUE=issue)
            resumo = (temp / "resumo.md").read_text() if (temp / "resumo.md").exists() else ""
            gh = (temp / "gh.txt").read_text() if (temp / "gh.txt").exists() else ""
            return r.returncode, resumo, gh

        rc, resumo, gh = avisar(salvou=True)
        caso("aviso: rodada salva diz isso e não abre issue", rc == 0 and "Rodada salva" in resumo and gh == "")
        rc, resumo, gh = avisar(motivo="a conferência passou do limite")
        caso("aviso: não salvou diz o motivo e como retomar", rc == 0 and "NADA FOI SALVO" in resumo and "a conferência passou do limite" in resumo
             and "retomar" in resumo and "run_id = 123" in resumo)
        caso("aviso: anterior boa, não abre issue", "issue create" not in gh and "issue comment" not in gh)
        rc, resumo, gh = avisar(motivo="x", anterior="failure")
        caso("aviso: duas seguidas sem salvar abre a issue", "issue create" in gh)
        rc, resumo, gh = avisar(motivo="x", anterior="failure", issue="7")
        caso("aviso: issue aberta recebe comentário em vez de outra", "issue comment 7" in gh and "issue create" not in gh)
        rc, resumo, gh = avisar(motivo="x", artefato=False)
        caso("aviso: sem artefato não manda retomar", "run_id" not in resumo and "Não havia trabalho" in resumo)
        limpar()
        r = sh(f"bash {RAIZ}/rotina/avisar-rodada.sh", GH_TOKEN="")
        caso("aviso: sem token, só o resumo", r.returncode == 0)

    # a rodada retomada: só as etapas essenciais rodam
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        (tmp / "bin/python").write_text('#!/bin/bash\necho "$@" >> "$RUNNER_TEMP/chamadas.txt"\n')
        (tmp / "bin/timeout").write_text('#!/bin/bash\n[ "$1" = "-k" ] && shift 2\nshift\nexec "$@"\n')
        for f in (tmp / "bin").iterdir():
            f.chmod(0o755)
        env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp), "RETOMAR": "true"}
        for etapa, ess in (("camara", ""), ("tce", ""), ("padronizar", "essencial"), ("site", "essencial")):
            subprocess.run(["bash", str(SCRIPT), etapa, "10", ess], cwd=RAIZ, env=env, capture_output=True, text=True)
        chamadas = (tmp / "chamadas.txt").read_text()
        caso("retomada: só padronizar e site rodam", "padronizar" in chamadas and "site" in chamadas and "camara" not in chamadas and "tce" not in chamadas)

    # concurrency: a rodada seguinte espera a em andamento, sem cancelá-la
    caso("concurrency fila sem cancelar", "group: atualizar-dados" in texto and "cancel-in-progress: false" in texto)
    caso("o upload do artefato nunca vai para a main (só artefato)", "name: trabalho-da-rodada" in texto and "retention-days: 14" in texto)


if __name__ == "__main__":
    sys.exit(executar())
