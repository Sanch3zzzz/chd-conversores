#!/usr/bin/env bash
set -uo pipefail

SCRIPT_NAME="$(basename -- "$0")"

usage() {
  cat <<EOF
Uso: $SCRIPT_NAME [opcoes] [arquivo.iso | pasta ...]

Converte ISOs de PS2 para .chd usando chdman no modo DVD (createdvd).

Opcoes:
  -r, --recursivo      procura ISOs nas subpastas
  -d, --apagar         apaga o ISO original depois de verificar o CHD
  -f, --forcar         sobrescreve um .chd que ja exista
      --cd             usa o modo CD (createcd) para jogos de PS2 em CD
  -c, --codec CODEC    compressao: zstd (padrao), zlib, lzma, default
  -j, --threads N      limita o numero de threads de compressao
  -h, --ajuda          mostra esta ajuda

Sem argumentos, converte os .iso da pasta atual (sem subpastas).
Variaveis de ambiente: CHD_CODEC e CHD_THREADS.

Observacoes:
  - O modo DVD e o correto para a grande maioria dos jogos de PS2.
  - Jogos de PS2 em CD (raros) costumam vir em .bin/.cue; use o script
    ps1-cd-para-chd.sh ou a opcao --cd se tiver um .iso de CD.
  - zstd pode nao funcionar em emuladores antigos (AetherSX2/NetherSX2
    antigos). Nesse caso use: -c zlib

Exemplos:
  $SCRIPT_NAME ~/jogos/ps2
  $SCRIPT_NAME -r -d ~/jogos/ps2
  $SCRIPT_NAME -c zlib jogo.iso
EOF
}

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

recursive=0
delete_src=0
force=0
cd_mode=0
codec="${CHD_CODEC:-zstd}"
threads="${CHD_THREADS:-}"
paths=()

while (($#)); do
  case "$1" in
    -r|--recursivo) recursive=1 ;;
    -d|--apagar) delete_src=1 ;;
    -f|--forcar) force=1 ;;
    --cd) cd_mode=1 ;;
    -c|--codec)
      (($# >= 2)) || die "faltou o valor de $1"
      codec="$2"
      shift
      ;;
    -j|--threads)
      (($# >= 2)) || die "faltou o valor de $1"
      threads="$2"
      shift
      ;;
    -h|--ajuda|--help) usage; exit 0 ;;
    --) shift; paths+=("$@"); break ;;
    -*) die "opcao desconhecida: $1" ;;
    *) paths+=("$1") ;;
  esac
  shift
done

case "${codec,,}" in
  default|padrao|"") codec="" ;;
esac

((${#paths[@]})) || paths=(".")

command -v chdman >/dev/null 2>&1 || die "chdman nao encontrado. Instale com: sudo pacman -S mame-tools"

declare -a srcs=()
declare -A seen=()

add_src() {
  local f="$1" key
  key="$(realpath -m -- "$f" 2>/dev/null || printf '%s' "$f")"
  [[ -n "${seen[$key]:-}" ]] && return 0
  seen["$key"]=1
  srcs+=("$f")
}

scan_dir() {
  local dir="$1"
  while IFS= read -r -d '' f; do
    add_src "$f"
  done < <(
    if ((recursive)); then
      find "$dir" -type f -iname '*.iso' -print0 2>/dev/null
    else
      find "$dir" -maxdepth 1 -type f -iname '*.iso' -print0 2>/dev/null
    fi
  )
}

for p in "${paths[@]}"; do
  if [[ -d "$p" ]]; then
    scan_dir "$p"
  elif [[ -f "$p" ]]; then
    if [[ "${p,,}" == *.iso ]]; then
      add_src "$p"
    else
      printf 'Ignorando (nao e .iso): %s\n' "$p" >&2
    fi
  else
    printf 'Aviso: caminho nao encontrado: %s\n' "$p" >&2
  fi
done

if ((${#srcs[@]} == 0)); then
  printf 'Nenhum .iso encontrado.\n'
  exit 0
fi

mapfile -d '' -t srcs < <(printf '%s\0' "${srcs[@]}" | sort -z)

ok=0
fail=0
skipped=0

convert_iso() {
  local src="$1" dir base stem out tmp
  dir="$(dirname -- "$src")"
  base="$(basename -- "$src")"
  stem="${base%.*}"
  out="$dir/$stem.chd"

  if [[ -e "$out" && "$force" -eq 0 ]]; then
    printf 'Pulando (ja existe): %s\n' "$out"
    skipped=$((skipped + 1))
    return 0
  fi

  tmp="${out}.part"
  rm -f -- "$tmp"

  local args=(createdvd)
  if ((cd_mode)); then
    args=(createcd)
  fi
  [[ -n "$codec" ]] && args+=(-c "$codec")
  [[ -n "$threads" ]] && args+=(-np "$threads")
  args+=(-i "$src" -o "$tmp")

  printf '\nConvertendo: %s\n' "$src"
  if ! chdman "${args[@]}"; then
    rm -f -- "$tmp"
    printf 'Falhou: %s\n' "$src" >&2
    fail=$((fail + 1))
    return 1
  fi

  if ! chdman verify -i "$tmp" >/dev/null 2>&1; then
    rm -f -- "$tmp"
    printf 'Verificacao falhou: %s\n' "$src" >&2
    fail=$((fail + 1))
    return 1
  fi

  if ! mv -f -- "$tmp" "$out"; then
    rm -f -- "$tmp"
    printf 'Nao consegui gravar: %s\n' "$out" >&2
    fail=$((fail + 1))
    return 1
  fi

  printf 'OK: %s\n' "$out"
  ok=$((ok + 1))

  if ((delete_src)); then
    if rm -f -- "$src"; then
      printf 'Apagado: %s\n' "$src"
    else
      printf 'Aviso: nao consegui apagar %s\n' "$src" >&2
    fi
  fi

  return 0
}

for src in "${srcs[@]}"; do
  convert_iso "$src" || true
done

printf '\nResumo: %d convertido(s), %d pulado(s), %d falha(s).\n' "$ok" "$skipped" "$fail"

if ((fail > 0)); then
  exit 1
fi
exit 0
