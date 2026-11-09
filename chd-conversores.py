#!/usr/bin/env python3
"""Converte imagens de disco de PS1, PS2 e PSP para CHD usando o chdman."""

import argparse
import os
import re
import shutil
import subprocess
import sys

SCRIPT_NAME = os.path.basename(sys.argv[0])

FILE_QUOTED_RE = re.compile(r'^\s*FILE\s+"([^"]+)"', re.I)
FILE_PLAIN_RE = re.compile(r'^\s*FILE\s+(\S+)', re.I)


class Stats:
    def __init__(self):
        self.ok = 0
        self.fail = 0
        self.skipped = 0


def die(message):
    print(f"Erro: {message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_codec(codec):
    codec = (codec or "").strip()
    if codec.lower() in ("", "default", "padrao"):
        return ""
    return codec


def remove_quiet(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def check_chdman():
    if not shutil.which("chdman"):
        die("chdman nao encontrado. Instale com: sudo pacman -S mame-tools")


def scan_paths(paths, recursive, extensions, label):
    found = []
    seen = set()

    def matches(name):
        low = name.lower()
        return any(low.endswith(ext) for ext in extensions)

    def add(path):
        key = os.path.realpath(path)
        if key in seen:
            return
        seen.add(key)
        found.append(path)

    for path in paths:
        if os.path.isdir(path):
            if recursive:
                for root, _dirs, files in os.walk(path):
                    for name in files:
                        if matches(name):
                            add(os.path.join(root, name))
            else:
                try:
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if entry.is_file() and matches(entry.name):
                                add(entry.path)
                except OSError:
                    pass
        elif os.path.isfile(path):
            if matches(path):
                add(path)
            else:
                print(f"Ignorando (nao e {label}): {path}", file=sys.stderr)
        else:
            print(f"Aviso: caminho nao encontrado: {path}", file=sys.stderr)

    found.sort()
    return found


def delete_cue_sources(cue):
    cue_dir = os.path.dirname(cue) or "."
    try:
        with open(cue, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = FILE_QUOTED_RE.match(line) or FILE_PLAIN_RE.match(line)
                if not match:
                    continue
                track = match.group(1)
                if not os.path.isabs(track):
                    track = os.path.join(cue_dir, track)
                if os.path.exists(track):
                    try:
                        os.remove(track)
                        print(f"Apagado: {track}")
                    except OSError:
                        print(f"Aviso: nao consegui apagar {track}", file=sys.stderr)
    except OSError as exc:
        print(f"Aviso: nao consegui ler {cue}: {exc}", file=sys.stderr)

    try:
        os.remove(cue)
        print(f"Apagado: {cue}")
    except OSError:
        print(f"Aviso: nao consegui apagar {cue}", file=sys.stderr)


def build_command(platform, args, codec, src, tmp):
    command = ["chdman"]
    if platform == "ps1":
        command.append("createcd")
    elif platform == "ps2":
        command.append("createcd" if getattr(args, "cd", False) else "createdvd")
    else:
        command.extend(["createdvd", "-hs", "2048"])

    if codec:
        command.extend(["-c", codec])
    if args.threads:
        command.extend(["-np", str(args.threads)])
    command.extend(["-i", src, "-o", tmp])
    return command


def convert(src, kind, platform, args, codec, stats):
    directory = os.path.dirname(src) or "."
    stem = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(directory, stem + ".chd")

    if os.path.exists(out) and not args.forcar:
        print(f"Pulando (ja existe): {out}")
        stats.skipped += 1
        return

    tmp = out + ".part"
    remove_quiet(tmp)

    print(f"\nConvertendo: {src}", flush=True)
    result = subprocess.run(build_command(platform, args, codec, src, tmp))
    if result.returncode != 0:
        remove_quiet(tmp)
        print(f"Falhou: {src}", file=sys.stderr)
        stats.fail += 1
        return

    verify = subprocess.run(
        ["chdman", "verify", "-i", tmp],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if verify.returncode != 0:
        remove_quiet(tmp)
        print(f"Verificacao falhou: {src}", file=sys.stderr)
        stats.fail += 1
        return

    try:
        os.replace(tmp, out)
    except OSError:
        remove_quiet(tmp)
        print(f"Nao consegui gravar: {out}", file=sys.stderr)
        stats.fail += 1
        return

    print(f"OK: {out}")
    stats.ok += 1

    if args.apagar:
        if kind == "cue":
            delete_cue_sources(src)
        else:
            try:
                os.remove(src)
                print(f"Apagado: {src}")
            except OSError:
                print(f"Aviso: nao consegui apagar {src}", file=sys.stderr)


def finish(stats):
    print(f"\nResumo: {stats.ok} convertido(s), {stats.skipped} pulado(s), "
          f"{stats.fail} falha(s).")
    return 1 if stats.fail > 0 else 0


def run_ps1(args):
    check_chdman()
    codec = normalize_codec(args.codec)
    paths = args.paths or ["."]

    cues = []
    isos = []
    for path in scan_paths(paths, args.recursivo, [".cue", ".iso"], ".cue/.iso"):
        if path.lower().endswith(".cue"):
            cues.append(path)
        else:
            isos.append(path)

    if not cues and not isos:
        print("Nenhum .cue/.iso encontrado.")
        print("Se você tem apenas .bin, é necessário um .cue correspondente.")
        return 0

    cue_stems = set()
    for cue in cues:
        directory = os.path.realpath(os.path.dirname(cue) or ".")
        stem = os.path.splitext(os.path.basename(cue))[0].lower()
        cue_stems.add((directory, stem))

    stats = Stats()
    for cue in cues:
        convert(cue, "cue", "ps1", args, codec, stats)

    for iso in isos:
        directory = os.path.realpath(os.path.dirname(iso) or ".")
        stem = os.path.splitext(os.path.basename(iso))[0].lower()
        if (directory, stem) in cue_stems:
            print(f"Pulando ISO (existe .cue com o mesmo nome): {iso}")
            stats.skipped += 1
            continue
        convert(iso, "iso", "ps1", args, codec, stats)

    return finish(stats)


def run_iso_platform(args, platform):
    check_chdman()
    codec = normalize_codec(args.codec)
    paths = args.paths or ["."]

    sources = scan_paths(paths, args.recursivo, [".iso"], ".iso")
    if not sources:
        print("Nenhum .iso encontrado.")
        return 0

    stats = Stats()
    for src in sources:
        convert(src, "iso", platform, args, codec, stats)
    return finish(stats)


def add_common_options(parser, default_codec, allow_cd=False):
    parser.add_argument(
        "-r", "--recursivo", action="store_true",
        help="procura os arquivos tambem nas subpastas",
    )
    parser.add_argument(
        "-d", "--apagar", action="store_true",
        help="apaga as origens depois de verificar o CHD",
    )
    parser.add_argument(
        "-f", "--forcar", action="store_true",
        help="sobrescreve um .chd que ja exista",
    )
    if allow_cd:
        parser.add_argument(
            "--cd", action="store_true",
            help="usa o modo CD (createcd) para jogos de PS2 em CD",
        )
    parser.add_argument(
        "-c", "--codec", default=os.environ.get("CHD_CODEC", default_codec),
        help=f"compressao (padrao: {default_codec or 'do chdman'}); "
             "variavel de ambiente: CHD_CODEC",
    )
    parser.add_argument(
        "-j", "--threads", default=os.environ.get("CHD_THREADS", ""),
        help="limita o numero de threads do chdman; variavel: CHD_THREADS",
    )
    parser.add_argument(
        "paths", nargs="*", metavar="caminho",
        help="arquivos ou pastas (padrao: pasta atual)",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Converte imagens de disco de PS1, PS2 e PSP para CHD "
                    "usando o chdman (MAME), com verify antes de apagar a origem.",
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            f"  {SCRIPT_NAME} ps1 ~/jogos/ps1\n"
            f"  {SCRIPT_NAME} ps2 -r -d ~/jogos/ps2\n"
            f"  {SCRIPT_NAME} psp -c default ~/jogos/psp\n"
            f"  {SCRIPT_NAME} ps2 --cd jogo-de-ps2-em-cd.iso\n"
        ),
    )
    parser.add_argument(
        "-h", "--ajuda", "--help", action="help",
        help="mostra esta ajuda",
    )

    subparsers = parser.add_subparsers(dest="platform", metavar="{ps1,ps2,psp}")

    ps1 = subparsers.add_parser(
        "ps1", add_help=False,
        description="PS1 (CD): converte .cue/.bin ou .iso com createcd.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Com .cue, todos os .bin referenciados sao usados automaticamente.\n"
            "Com --apagar e .cue, o script apaga o .cue e os .bin que ele lista.\n"
            "Formatos .ccd/.mds/.pbp nao sao suportados pelo chdman.\n"
            "Um .bin sem .cue nao tem informacao de trilhas; nao e convertido.\n"
        ),
    )
    ps1.add_argument("-h", "--ajuda", "--help", action="help", help="mostra esta ajuda")
    add_common_options(ps1, "")

    ps2 = subparsers.add_parser(
        "ps2", add_help=False,
        description="PS2 (DVD): converte .iso com createdvd; --cd para jogos em CD.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Jogos de PS2 em CD (raros) costumam vir em .bin/.cue; use o\n"
            "subcomando ps1 ou a opcao --cd se tiver um .iso de CD.\n"
            "zstd pode nao funcionar em emuladores antigos (AetherSX2/NetherSX2);\n"
            "nesse caso use: -c zlib\n"
        ),
    )
    ps2.add_argument("-h", "--ajuda", "--help", action="help", help="mostra esta ajuda")
    add_common_options(ps2, "zstd", allow_cd=True)

    psp = subparsers.add_parser(
        "psp", add_help=False,
        description="PSP (UMD): converte .iso com createdvd -hs 2048.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "O CHD de PSP exige PPSSPP 1.17 ou mais novo.\n"
            "zstd exige PPSSPP 1.17.1 ou mais novo; em versoes antigas use:\n"
            "  -c default\n"
            "O hunk de 2048 bytes evita problemas de desempenho no PPSSPP.\n"
            "O PPSSPP nao le CHD na PSP real; no hardware use CSO.\n"
        ),
    )
    psp.add_argument("-h", "--ajuda", "--help", action="help", help="mostra esta ajuda")
    add_common_options(psp, "zstd")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.platform:
        parser.print_help()
        return 2
    if args.platform == "ps1":
        return run_ps1(args)
    return run_iso_platform(args, args.platform)


if __name__ == "__main__":
    sys.exit(main())
