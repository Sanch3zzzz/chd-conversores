#!/usr/bin/env bash
set -uo pipefail

SCRIPT_NAME="$(basename -- "$0")"

usage() {
  cat <<EOF
Uso: $SCRIPT_NAME [opcoes] [arquivo.cue | arquivo.iso | pasta ...]

Converte jogos de PS1 para .chd usando chdman no modo CD (createcd).

O modo CD preserva faixas de audio e o layout original do disco. O
formato recomendado para PS1 e .cue + .bin; um .iso solto tambem
funciona, mas so contem uma faixa de dados.

Opcoes:
  -r, --recursivo      procura .cue/.iso nas subpastas
  -d, --apagar         apaga as origens depois de verificar o CHD
  -f, --forcar         sobrescreve um .chd que ja exista
  -c, --codec CODEC    compressao: default, cdzl, cdzs, cdlz, cdfl
  -j, --threads N      limita o numero de threads de compressao
  -h, --ajuda          mostra esta ajuda

Sem argumentos, converte os .cue/.iso da pasta atual (sem subpastas).
Variaveis de ambiente: CHD_CODEC e CHD_THREADS.

Observacoes:
  - Com .cue, todos os .bin referenciados sao usados automaticamente.
  - Com --apagar e .cue, o script apaga o .cue e os .bin que ele lista.
  - Formatos .ccd/.mds/.pbp nao sao suportados pelo chdman.
  - Um .bin sem .cue nao tem informacao de trilhas; nao e convertido.

Exemplos:
  $SCRIPT_NAME ~/jogos/ps1
  $SCRIPT_NAME -r -d ~/jogos/ps1
  $SCRIPT_NAME "Final Fantasy VII (Disc 1).cue"
EOF
}

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

recursive=0
delete_src=0
force=0
codec="${CHD_CODEC:-}"
threads="${CHD_THREADS:-}"
paths=()

while (($#)); do
  case "$1" in
    -r|--recursivo) recursive=1 ;;
    -d|--apagar) delete_src=1 ;;
    -f|--forcar) force=1 ;;
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

declare -a cues=()
declare -a isos=()
declare -A seen=()

add_file() {
  local f="$1" key
  key="$(realpath -m -- "$f" 2>/dev/null || printf '%s' "$f")"
  [[ -n "${seen[$key]:-}" ]] && return 0
  seen["$key"]=1
  case "${f,,}" in
    *.cue) cues+=("$f") ;;
    *.iso) isos+=("$f") ;;
  esac
}

scan_dir() {
  local dir="$1"
  while IFS= read -r -d '' f; do
    add_file "$f"
  done < <(
    if ((recursive)); then
      find "$dir" -type f \( -iname '*.cue' -o -iname '*.iso' \) -print0 2>/dev/null
    else
      find "$dir" -maxdepth 1 -type f \( -iname '*.cue' -o -iname '*.iso' \) -print0 2>/dev/null
    fi
  )
}

for p in "${paths[@]}"; do
  if [[ -d "$p" ]]; then
    scan_dir "$p"
  elif [[ -f "$p" ]]; then
    case "${p,,}" in
      *.cue|*.iso) add_file "$p" ;;
      *) printf 'Ignorando (nao e .cue/.iso): %s\n' "$p" >&2 ;;
    esac
  else
    printf 'Aviso: caminho nao encontrado: %s\n' "$p" >&2
  fi
done

if ((${#cues[@]} == 0 && ${#isos[@]} == 0)); then
  printf 'Nenhum .cue/.iso encontrado.\n'
  printf 'Se você tem apenas .bin, é necessário um .cue correspondente.\n'
  exit 0
fi

((${#cues[@]})) && mapfile -d '' -t cues < <(printf '%s\0' "${cues[@]}" | sort -z)
((${#isos[@]})) && mapfile -d '' -t isos < <(printf '%s\0' "${isos[@]}" | sort -z)

declare -A cue_stem=()
for c in "${cues[@]}"; do
  cdir="$(realpath -m -- "$(dirname -- "$c")")"
  cbase="$(basename -- "$c")"
  cstem="${cbase%.*}"
  cue_stem["$cdir/${cstem,,}"]=1
done

ok=0
fail=0
skipped=0

delete_cue_sources() {
  local cue="$1" cue_dir line track
  cue_dir="$(dirname -- "$cue")"

  while IFS= read -r line || [[ -n "$line" ]]; do
    track=""
    if [[ "$line" =~ ^[[:space:]]*[Ff][Ii][Ll][Ee][[:space:]]+\"([^\"]+)\" ]]; then
      track="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ ^[[:space:]]*[Ff][Ii][Ll][Ee][[:space:]]+([^[:space:]]+) ]]; then
      track="${BASH_REMATCH[1]}"
    fi
    [[ -n "$track" ]] || continue
    [[ "$track" = /* ]] || track="$cue_dir/$track"
    if [[ -e "$track" ]]; then
      if rm -f -- "$track"; then
        printf 'Apagado: %s\n' "$track"
      else
        printf 'Aviso: nao consegui apagar %s\n' "$track" >&2
      fi
    fi
  done < "$cue"

  if rm -f -- "$cue"; then
    printf 'Apagado: %s\n' "$cue"
  else
    printf 'Aviso: nao consegui apagar %s\n' "$cue" >&2
  fi
}

convert_disc() {
  local src="$1" kind="$2" dir base stem out tmp
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

  local args=(createcd)
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
    if [[ "$kind" == cue ]]; then
      delete_cue_sources "$src"
    else
      if rm -f -- "$src"; then
        printf 'Apagado: %s\n' "$src"
      else
        printf 'Aviso: nao consegui apagar %s\n' "$src" >&2
      fi
    fi
  fi

  return 0
}

for src in "${cues[@]}"; do
  convert_disc "$src" cue || true
done

for src in "${isos[@]}"; do
  idir="$(realpath -m -- "$(dirname -- "$src")")"
  ibase="$(basename -- "$src")"
  istem="${ibase%.*}"
  if [[ -n "${cue_stem["$idir/${istem,,}"]:-}" ]]; then
    printf 'Pulando ISO (existe .cue com o mesmo nome): %s\n' "$src"
    skipped=$((skipped + 1))
    continue
  fi
  convert_disc "$src" iso || true
done

printf '\nResumo: %d convertido(s), %d pulado(s), %d falha(s).\n' "$ok" "$skipped" "$fail"

if ((fail > 0)); then
  exit 1
fi
exit 0
