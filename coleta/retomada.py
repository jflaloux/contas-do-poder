"""Rede de segurança da rodada do GitHub: guardar o trabalho da coleta e retomar uma rodada que não salvou.

    python3 -m coleta.retomada guardar <pasta>     empacota o que a rodada produziu (workflow: passo "ponto de retomada")
    python3 -m coleta.retomada restaurar <pasta>   restaura o pacote numa rodada nova (workflow: entrada "retomar")

O pacote (trabalho.tgz + manifesto.json) vai para o CACHE do GitHub Actions (chave trabalho-<número da rodada>), nunca para um
artefato: o artefato de um repositório público pode ser baixado por qualquer conta do GitHub, e o pacote leva `dados/brutos/`
(intermediários que não vão para o Git, com o que a fonte publica, como o CPF mascarado do Portal da Transparência). O cache só
é lido pelas rodadas do próprio repositório. Nada disto publica: quem publica é só o `git push` do passo de salvar, depois da
conferência.

O que entra: os arquivos de `dados/` e `site/` diferentes do commit em que a rodada começou (INICIO_SHA; alterados, novos e
apagados, comitados ou não) e `dados/brutos/`. Na restauração, o pacote é validado antes de qualquer extração (só arquivos
comuns, só em dados/ e site/, sem `..` nem caminho absoluto, e os mesmos do manifesto) e é recusado se a `main` mudou, desde
o commit de partida, algum dos arquivos de dados que ele traz (por exemplo, um CSV que outra rodada enviou): ele sobrescreveria
um trabalho mais novo. Nos arquivos gerados (GERADOS: os do site, feitos a partir dos CSVs, e a base em dados/processados/),
fica a versão da `main` (como no passo de salvar, quando o rebase conflita com a rodada do Brasil): a lista vai para
<pasta>/mantidos.txt, e o workflow refaz os arquivos do site com `coletar.py montar` antes das etapas essenciais.
"""
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

PERMITIDOS = ("dados/", "site/")
BRUTOS = "dados/brutos/"
LIMITE_MB = 700  # o cache do repositório tem 10 GB; um pacote maior que isto indica algo errado
# arquivos refeitos a partir dos CSVs (coletar.py montar, padronizar, site e situacao): no conflito, fica a versão da main
# (a mesma regra do passo de salvar do workflow, no rebase com a rodada do Brasil)
GERADOS = re.compile(r"^(site/dados/|site/fotos/creditos\.json$|dados/processados/)")


class Recusa(Exception):
    """O pacote não pode ser guardado ou aplicado (a mensagem diz por quê)."""


def _git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise Recusa(f"git {' '.join(args[:3])}: {r.stderr.strip()[:200]}")
    return r.stdout


def _lista_nul(*args):
    return [x for x in _git(*args).split("\0") if x]


def _blob(commit, caminho):
    r = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{commit}:{caminho}"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def guardar(pasta, inicio=None, raiz="."):
    """Empacota o trabalho em <pasta>/trabalho.tgz e <pasta>/manifesto.json. Devolve o manifesto (None se não há nada)."""
    os.chdir(raiz)
    inicio = inicio or os.environ.get("INICIO_SHA") or _git("rev-parse", "HEAD").strip()
    alterados = set(_lista_nul("diff", "--name-only", "-z", "--diff-filter=d", inicio, "--", "dados", "site"))
    apagados = set(_lista_nul("diff", "--name-only", "-z", "--diff-filter=D", inicio, "--", "dados", "site"))
    novos = set(_lista_nul("ls-files", "-o", "--exclude-standard", "-z", "--", "dados", "site"))
    brutos = {str(p) for p in Path(BRUTOS).rglob("*") if p.is_file() and not p.is_symlink()} if Path(BRUTOS).is_dir() else set()
    arquivos = sorted(f for f in alterados | novos | brutos if os.path.isfile(f) and not os.path.islink(f))
    if not arquivos and not apagados:
        return None
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    manifesto = {"base": _git("rev-parse", inicio).strip(),
                 "arquivos": {f: _blob(inicio, f) for f in arquivos if not f.startswith(BRUTOS)},
                 "brutos": sum(1 for f in arquivos if f.startswith(BRUTOS)),
                 "apagados": {f: _blob(inicio, f) for f in sorted(apagados)}}
    pacote = pasta / "trabalho.tgz"
    with tarfile.open(pacote, "w:gz") as t:
        for f in arquivos:
            t.add(f, arcname=f, recursive=False)
    # confere o pacote que acabou de ser feito: mesmo conteúdo do manifesto
    with tarfile.open(pacote) as t:
        nomes = {m.name for m in t.getmembers()}
    esperado = set(manifesto["arquivos"]) | {f for f in arquivos if f.startswith(BRUTOS)}
    if nomes != esperado:
        raise Recusa("o pacote feito não tem os mesmos arquivos do manifesto")
    mb = pacote.stat().st_size / 1e6
    if mb > LIMITE_MB:
        raise Recusa(f"o pacote ficou com {mb:.0f} MB (limite {LIMITE_MB})")
    (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Trabalho guardado: {len(manifesto['arquivos'])} arquivos de dados e site, {manifesto['brutos']} brutos, "
          f"{len(apagados)} apagados, {mb:.1f} MB (partida {manifesto['base'][:8]}).")
    return manifesto


def _caminho_seguro(nome):
    p = Path(nome)
    return (not p.is_absolute() and ".." not in p.parts and nome.startswith(PERMITIDOS) and "\0" not in nome)


def restaurar(pasta, raiz="."):
    os.chdir(raiz)
    pasta = Path(pasta)
    if not (pasta / "trabalho.tgz").exists() or not (pasta / "manifesto.json").exists():
        raise Recusa(f"faltam trabalho.tgz e manifesto.json em {pasta}")
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    try:
        t = tarfile.open(pasta / "trabalho.tgz")
        membros = t.getmembers()
    except (tarfile.TarError, OSError, EOFError) as e:
        raise Recusa(f"o pacote não abre ({e})")
    with t:
        # 1) validar tudo antes de extrair qualquer coisa
        for m in membros:
            if not m.isreg():
                raise Recusa(f"o pacote tem algo que não é arquivo comum: {m.name}")
            if not _caminho_seguro(m.name):
                raise Recusa(f"o pacote tem um caminho fora de dados/ e site/ ou inseguro: {m.name}")
        nomes = {m.name for m in membros}
        esperado_sem_brutos = set(manifesto["arquivos"])
        if {n for n in nomes if not n.startswith(BRUTOS)} != esperado_sem_brutos:
            raise Recusa("os arquivos do pacote não são os do manifesto")
        if sum(1 for n in nomes if n.startswith(BRUTOS)) != manifesto.get("brutos"):
            raise Recusa("a quantidade de arquivos brutos do pacote não é a do manifesto")
        for caminho in [*manifesto["arquivos"], *manifesto["apagados"]]:
            if not _caminho_seguro(caminho):
                raise Recusa(f"o manifesto tem um caminho inseguro: {caminho}")
        # 2) a main não pode ter mudado nenhum dos arquivos de dados que o pacote traz; nos gerados, fica a versão da main
        conflitos = [c for c, base in {**manifesto["arquivos"], **manifesto["apagados"]}.items() if _blob("HEAD", c) != base]
        dados = [c for c in conflitos if not GERADOS.match(c)]
        if dados:
            raise Recusa("estes arquivos mudaram na main desde a rodada que falhou (rode a rodada completa de novo): "
                         + ", ".join(sorted(dados)[:20]) + (" ..." if len(dados) > 20 else ""))
        mantidos = set(conflitos)
        # 3) extrair
        for m in membros:
            if m.name not in mantidos:
                t.extract(m, path=".", **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    for c in manifesto["apagados"]:
        if c not in mantidos and os.path.exists(c):
            os.remove(c)
    (pasta / "mantidos.txt").write_text("".join(f"{c}\n" for c in sorted(mantidos)), encoding="utf-8")
    print(f"Trabalho restaurado (partida {manifesto['base'][:8]}): {len(manifesto['arquivos']) - len(mantidos)} arquivos de dados e site, "
          f"{manifesto['brutos']} brutos, {len(manifesto['apagados'])} apagados."
          + (f" Ficou a versão da main (mudou depois da rodada; refeitos com coletar.py montar): {', '.join(sorted(mantidos))}."
             if mantidos else ""))
    return sorted(mantidos)


def main(argv):
    if len(argv) != 3 or argv[1] not in ("guardar", "restaurar"):
        print(__doc__)
        return 2
    try:
        if argv[1] == "guardar":
            if guardar(argv[2]) is None:
                print("Nada para guardar.")
                return 3  # sem pacote: o workflow não envia nada ao cache
        else:
            restaurar(argv[2])
    except Recusa as e:
        print(f"ERRO: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
