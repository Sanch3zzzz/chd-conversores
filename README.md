# chd-conversores

Scripts em Bash para converter imagens de disco de **PS1, PS2 e PSP**
para **CHD** usando o `chdman` (MAME), com verificação de integridade
antes de apagar o original.

## Requisitos

- `chdman` recente (MAME 0.255 ou mais novo, por causa do `createdvd`).
- No Arch Linux:

```bash
sudo pacman -S mame-tools
```

- Em outras distribuições, instale o pacote `mame-tools` ou baixe o
  `chdman` do site do MAME.

## Scripts

| Script | Plataforma | Comando |
|---|---|---|
| `ps1-cd-para-chd.sh` | PS1 | `createcd` |
| `ps2-iso-para-chd.sh` | PS2 (DVD) | `createdvd` |
| `psp-iso-para-chd.sh` | PSP (UMD) | `createdvd -hs 2048` |

Para PS2 em CD (raro), use `ps2-iso-para-chd.sh --cd` ou o script de PS1.

## Instalação opcional

Para chamar os scripts de qualquer pasta:

```bash
mkdir -p ~/.local/bin
cp ps*-para-chd.sh ~/.local/bin/
```

## Uso rápido

```bash
chmod +x ps*-para-chd.sh

# pasta inteira, sem subpastas
./ps2-iso-para-chd.sh ~/jogos/ps2

# com subpastas e apagando os ISOs depois do verify
./ps2-iso-para-chd.sh -r -d ~/jogos/ps2

# PS1: um .chd por disco
./ps1-cd-para-chd.sh "$HOME/jogos/ps1/Jogo (Disc 1).cue"

# PSP
./psp-iso-para-chd.sh ~/jogos/psp
```

Opções comuns:

| Opção | Efeito |
|---|---|
| `-r`, `--recursivo` | procura nas subpastas |
| `-d`, `--apagar` | apaga a origem após o `chdman verify` |
| `-f`, `--forcar` | sobrescreve `.chd` existente |
| `-c`, `--codec` | escolhe a compressão |
| `-j`, `--threads` | limita threads do `chdman` |
| `-h`, `--ajuda` | mostra a ajuda |

Variáveis de ambiente: `CHD_CODEC` e `CHD_THREADS`.

## Como funciona

1. O `.chd` é criado como `.chd.part` na mesma pasta da origem.
2. O script roda `chdman verify` e compara os SHA1.
3. Só depois do `verify` o `.part` vira `.chd`.
4. Com `-d`, a origem só é apagada depois disso.

Se a conversão falhar ou for interrompida, o `.part` é removido e o
original permanece intacto.

**Pegadinha:** se você converteu sem `-d` e depois rodar só com `-d`, o
`.chd` existente é pulado e o original **não** é apagado. Use `-f -d`
para reconverter e apagar, ou apague manualmente.

## CD x DVD

- **PS1** é CD: `.cue` + `.bin`, com suporte a várias trilhas e áudio.
- **PS2/PSP** são DVD: ISO com setor de 2048 bytes.
- No PSP o hunk é fixado em 2048 bytes porque o PPSSPP é sensível a isso.

## Compatibilidade

- PPSSPP lê CHD desde a 1.17 e zstd desde a 1.17.1.
- PCSX2 atual lê `createdvd` com zstd.
- AetherSX2/NetherSX2 antigos podem não ler `createdvd` ou zstd. Tente
  `-c zlib` ou atualize o emulador.
- CHD não funciona na PSP real; no hardware o formato é CSO.

## Manual completo

O passo a passo detalhado, com codecs, formatos aceitos, recuperação do
original e solução de problemas, está em
[`manual-conversao-chd.txt`](manual-conversao-chd.txt).

## Testado

- PS1: Klonoa (Redump), `.cue` + `.bin` MODE2/2352. CHD verificado.
- PS2: GTA San Andreas (ISO DVD). CHD verificado.
- PSP: conversão e `verify` com ISO sintética (falta teste com jogo real).
