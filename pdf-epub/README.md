# Conversão de PDF para EPUB

Conversor de PDFs em lote para EPUB usando `pymupdf` (extração de texto e
imagens) e `ebooklib` (montagem do EPUB). Faz parte do repositório
`chd-conversores` como uma ferramenta separada.

## Pré-requisitos

- Python 3.8+
- `pymupdf` (`pip install pymupdf`)
- `ebooklib` (`pip install ebooklib`)
- Internet **só na primeira conversão** de cada livro, para baixar a capa
  no [Open Library](https://openlibrary.org) (usa `urllib` da stdlib, sem
  dependência extra)

## Uso

Coloque os PDFs na pasta `PDF/` (ou na raiz de `pdf-epub/`) e rode:

```bash
python3 converter.py
```

Se o `.epub` já existir, o script pula. Para regerar todos:

```bash
python3 converter.py --force
```

| Flag | Efeito |
|------|--------|
| `--force` | Regera EPUBs que já existem |
| `--no-images` | Ignora as imagens das páginas (só texto + capa) |
| `--refresh-covers` | Baixa a capa de novo, ignorando o cache em `covers/` |

## Capas e títulos

- **Capa:** o script baixa a capa no Open Library (busca por título +
  autor; há consultas alternativas para edições cujo título em português
  não tem capa). Se não encontrar — ou se a imagem for um placeholder
  minúsculo — gera a capa a partir da **página 1 do PDF**. A capa baixada
  é guardada em `covers/` e reaproveitada nas próximas vezes.
- **Título e autor:** vêm do dicionário `BOOKS`, no topo do
  `converter.py`, que corrige os nomes bagunçados dos arquivos (ex.:
  `SIMUND FREUD ...` → "O Futuro de uma Ilusão" / "Sigmund Freud"). O nome
  do `.epub` de saída também é limpo a partir do título. Livros fora do
  dicionário usam o nome do arquivo limpo e não têm autor.
- **Capítulos internos:** a primeira linha de cada página vira o título do
  capítulo **apenas** se parecer um cabeçalho (marcador tipo
  "Capítulo X"/"Introdução"/"Sumário" ou linha toda em maiúsculas); caso
  contrário fica "Página N". Isso evita encher o sumário com frases
  quebradas por linha.
- **Imagens:** embutidas como arquivos no formato original (JPEG/PNG), sem
  recomprimir nem usar base64. Em PDFs digitalizados isso evita EPUBs
  gigantes (um livro de 593 páginas escaneadas fica ~156 MB).

> Dica: nomes de arquivo em Unicode NFD (ex.: "Jesse" + acento separado)
> são normalizados para NFC antes de casar com o dicionário `BOOKS`.

## Organização das pastas

```
pdf-epub/
├── converter.py
├── README.md
├── covers/            # capas baixadas (cache), nomeadas pelo título
└── PDF/               # PDFs de origem (movidos para cá após a conversão)
```

Após a conversão, os PDFs originais são movidos para `PDF/`. Os `.epub`
saem na raiz de `pdf-epub/`, nomeados pelo título corrigido. O `.gitignore`
do repositório ignora `PDF/`, `covers/` e `*.epub` — a biblioteca em si
não vai para o git.

## Arrumar EPUB corrompido (sem conteúdo)

Se os EPUBs estiverem sem páginas (esqueleto vazio):

**1. Garanta que os PDFs originais estão na pasta `PDF/`.**

**2. Regenere:**

```bash
python3 converter.py --force
```

**3. Verificação:**

```python
from ebooklib import epub

book = epub.read_epub('nome.do.livro.epub')
print(f'{len(book.spine)} páginas')
```

### Pegadinhas conhecidas

- `EpubItem` não aceita o kwarg `properties`.
- Ao montar EPUB na mão, evite caminhos duplicados (`EPUB/EPUB/page_X.xhtml`)
  e a referência `toc="ncx"` no `<spine>` quando não existe arquivo NCX.
- O dicionário `BOOKS` é específico desta biblioteca; ajuste títulos/autores
  conforme os seus PDFs.
