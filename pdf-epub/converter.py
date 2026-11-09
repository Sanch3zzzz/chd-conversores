import os
import re
import sys
import json
import shutil
import struct
import unicodedata
import urllib.request
import urllib.parse
import pymupdf
from ebooklib import epub

LIVROS_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(LIVROS_DIR, "PDF")
COVERS_DIR = os.path.join(LIVROS_DIR, "covers")

# Metadados corretos por arquivo PDF (sem a extensao).
# chave -> (titulo, autor)
BOOKS = {
    "1984": ("1984", "George Orwell"),
    "A ARTE DA GUERRA": ("A Arte da Guerra", "Sun Tzu"),
    "ASSIM FALOU ZARATUSTRA": ("Assim Falou Zaratustra", "Friedrich Nietzsche"),
    "Como-as-Democracias-Morrem-Steven-Levitsky": (
        "Como as Democracias Morrem", "Steven Levitsky e Daniel Ziblatt"),
    "Fisica Basica vol 1 - Moyses Nussenzveig 4ed_Mecanica": (
        "Física Básica - Volume 1: Mecânica", "Moysés Nussenzveig"),
    "Jessé-Souza-A-Elite-do-Atraso": ("A Elite do Atraso", "Jessé Souza"),
    "Kurose - Redes de computadores e a internet-Uma Abordagem Top-Down - 6a": (
        "Redes de Computadores e a Internet: Uma Abordagem Top-Down",
        "James F. Kurose e Keith W. Ross"),
    "MAQUIAVEL - O PRINCIPE": ("O Príncipe", "Nicolau Maquiavel"),
    "O Capital - Karl Marx": ("O Capital", "Karl Marx"),
    "SIMUND FREUD - O FUTURO DE UMA ILUSÃO": ("O Futuro de uma Ilusão", "Sigmund Freud"),
    "STEPHEN HAWKING BREVE HISTORIO DO TEMPO": ("Breve História do Tempo", "Stephen Hawking"),
    "Tanenbaum Rede de Computadores 6a": ("Redes de Computadores", "Andrew S. Tanenbaum"),
    "as-veias-abertas-da-america-latina-eduardo-galeano": (
        "As Veias Abertas da América Latina", "Eduardo Galeano"),
    "orwell - a revolução dos bichos": ("A Revolução dos Bichos", "George Orwell"),
}

# Consultas extras de capa, tentadas antes de cair no fallback (pagina 1 do PDF).
# Util para edicoes cujo titulo em portugues nao tem capa no Open Library.
COVER_QUERY_ALTS = {
    "STEPHEN HAWKING BREVE HISTORIO DO TEMPO": [("A Brief History of Time", "Stephen Hawking")],
}


def ensure_pdf_dir():
    os.makedirs(PDF_DIR, exist_ok=True)


def move_to_pdf(filepath):
    dest = os.path.join(PDF_DIR, os.path.basename(filepath))
    shutil.move(filepath, dest)
    print(f"  Movido para: PDF/{os.path.basename(filepath)}")


def book_meta(pdf_stem):
    # Alguns nomes vem em Unicode NFD (acento separado, ex.: "Jesse\u0301").
    # Normaliza para NFC para casar com as chaves de BOOKS.
    key = unicodedata.normalize('NFC', pdf_stem)
    if key in BOOKS:
        return BOOKS[key]
    title = key.replace('_', ' ')
    title = re.sub(r'\s*-\s*', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return (title or pdf_stem, "")


def safe_filename(name):
    # ':' vira ' - ' (ex.: "Volume 1: Mecânica" -> "Volume 1 - Mecânica"),
    # o resto dos caracteres invalidos vira '-'.
    name = re.sub(r'\s*:\s*', ' - ', name)
    name = re.sub(r'[\\/:*?"<>|]', '-', name)
    return re.sub(r'\s+', ' ', name).strip()


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (converter.py)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def image_size(data):
    """Dimensoes (w, h) de um JPEG/PNG, ou None se desconhecido."""
    if data[:2] == b'\xff\xd8':
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                h = struct.unpack('>H', data[i + 5:i + 7])[0]
                w = struct.unpack('>H', data[i + 7:i + 9])[0]
                return (w, h)
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + struct.unpack('>H', data[i + 2:i + 4])[0]
    elif data[:8] == b'\x89PNG\r\n\x1a\n':
        return (struct.unpack('>I', data[16:20])[0], struct.unpack('>I', data[20:24])[0])
    return None


def valid_cover(data):
    """Rejeita placeholders minusculos do Open Library."""
    if not data or len(data) < 5000:
        return False
    size = image_size(data)
    if size and min(size) < 150:
        return False
    return True


def download_cover(candidates):
    for title, author in candidates:
        params = {"title": title, "limit": 5, "fields": "title,cover_i"}
        if author:
            params["author"] = author
        url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
        try:
            docs = json.loads(http_get(url)).get("docs", [])
        except Exception:
            continue
        for doc in docs:
            cover_id = doc.get("cover_i")
            if not cover_id:
                continue
            try:
                data = http_get(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg")
            except Exception:
                continue
            if valid_cover(data):
                return data
    return None


def render_cover(pdf_path):
    doc = pymupdf.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2))
        return pix.tobytes("jpeg")
    finally:
        doc.close()


def get_cover(pdf_path, pdf_stem, title, author):
    os.makedirs(COVERS_DIR, exist_ok=True)
    cache = os.path.join(COVERS_DIR, safe_filename(title) + ".jpg")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        with open(cache, "rb") as fh:
            return fh.read()

    candidates = [(title, author)]
    candidates += COVER_QUERY_ALTS.get(pdf_stem, [])
    candidates.append((title, ""))
    seen = set()
    unique = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    data = download_cover(unique)
    if data:
        print("  Capa: baixada do Open Library")
    else:
        print("  Capa: nao encontrada online, usando pagina 1 do PDF")
        data = render_cover(pdf_path)

    with open(cache, "wb") as fh:
        fh.write(data)
    return data


IMAGE_MIME = {
    "jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "bmp": "image/bmp", "tiff": "image/tiff",
    "jpx": "image/jp2", "jp2": "image/jp2",
}


def add_page_images(book, doc, page, registry, counter):
    """Adiciona as imagens da pagina ao EPUB usando os bytes ORIGINAIS
    (JPEG/PNG/etc), sem recomprimir nem embutir base64 -- e o que evita
    EPUBs gigantes em PDFs digitalizados. Retorna os caminhos relativos na
    ordem em que as imagens aparecem na pagina."""
    refs = []
    for img in page.get_images(full=True):
        xref = img[0]
        if xref in registry:
            refs.append(registry[xref])
            continue
        try:
            info = doc.extract_image(xref)
            ext = info["ext"].lower()
            data = info["image"]
        except Exception:
            continue
        if not data or ext not in IMAGE_MIME:
            continue
        counter[0] += 1
        fname = f"images/img_{counter[0]}.{ext}"
        book.add_item(epub.EpubItem(
            uid=f"img_{counter[0]}",
            file_name=fname,
            media_type=IMAGE_MIME[ext],
            content=data,
        ))
        registry[xref] = fname
        refs.append(fname)
    return refs


CHAPTER_RE = re.compile(
    r'^(cap[íi]tulo|chapter|parte|se[çc][ãa]o|pref[áa]cio|introdu[çc][ãa]o|'
    r'sum[áa]rio|prólogo|ep[íi]logo|conclus[ãa]o)\b', re.I)


def guess_heading(text, page_num):
    """Usa a primeira linha como titulo do capitulo so quando ela parece um
    cabecalho (marcador de capitulo ou linha toda em maiusculas). Caso
    contrario mantem 'Pagina N' para nao poluir o sumario."""
    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    if not lines:
        return f"Página {page_num}"
    first = lines[0]
    if len(first) <= 60 and CHAPTER_RE.match(first):
        return first
    if 4 <= len(first) <= 60 and first.upper() == first and any(c.isalpha() for c in first):
        return first
    return f"Página {page_num}"


def create_epub(pdf_path, epub_path, title, author, cover_data, with_images=True):
    doc = pymupdf.open(pdf_path)
    book = epub.EpubBook()

    book.set_identifier(f'id_{safe_filename(title)}')
    book.set_title(title)
    book.set_language('pt-br')
    if author:
        book.add_author(author)

    css_content = """
    body { background-color: #000000; color: #FFFFFF; }
    p { color: #FFFFFF; background-color: #000000; }
    h1, h2, h3, h4, h5, h6 { color: #FFFFFF; background-color: #000000; }
    div { color: #FFFFFF; background-color: #000000; }
    img { max-width: 100%; height: auto; }
    """

    book.add_item(epub.EpubItem(
        uid="style_css",
        file_name="style.css",
        media_type="text/css",
        content=css_content
    ))

    if cover_data:
        book.set_cover("cover.jpg", cover_data)

    total_pages = len(doc)
    full_text = []
    page_image_data = []
    registry = {}
    counter = [0]

    for page_num in range(total_pages):
        page = doc[page_num]
        text = page.get_text()
        full_text.append(text)
        if with_images:
            page_image_data.append(add_page_images(book, doc, page, registry, counter))
        else:
            page_image_data.append([])
        print(f"\r  Pagina {page_num + 1}/{total_pages}", end="", flush=True)

    doc.close()
    print()

    chapters = []
    for i, text in enumerate(full_text):
        if not text.strip() and not page_image_data[i]:
            continue
        chapter_title = guess_heading(text, i + 1)
        page_title = f"{title} - pagina {i + 1}"
        escaped = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html_body = '<br>'.join(escaped.split('\n'))

        img_tags = ''
        if with_images:
            for img_src in page_image_data[i]:
                img_tags += f'<img src="{img_src}" /><br>'

        chapter_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{page_title}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    {img_tags}{html_body}
</body>
</html>'''

        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=f'page_{i+1}.xhtml',
            lang='pt-br'
        )
        chapter.id = f'page_{i+1}'
        chapter.content = chapter_content
        book.add_item(chapter)
        chapters.append(chapter)

    nav = epub.EpubNav()
    nav.id = 'nav'
    book.add_item(nav)
    book.toc = tuple(chapters)

    spine = (['cover'] if cover_data else []) + ['nav'] + chapters
    book.spine = spine

    epub.write_epub(epub_path, book, {})
    print(f"  OK: {os.path.basename(epub_path)}")


def main():
    pdf_files_root = sorted([f for f in os.listdir(LIVROS_DIR) if f.endswith('.pdf')])
    pdf_in_subdir = sorted([os.path.join("PDF", f) for f in os.listdir(PDF_DIR) if f.endswith('.pdf')]) if os.path.isdir(PDF_DIR) else []

    if pdf_files_root:
        pdf_files = pdf_files_root
    elif pdf_in_subdir:
        pdf_files = pdf_in_subdir
    else:
        print("Nenhum arquivo PDF encontrado.")
        return

    ensure_pdf_dir()
    print(f"Encontrados {len(pdf_files)} arquivo(s) PDF.\n")

    force = '--force' in sys.argv
    no_images = '--no-images' in sys.argv
    # Sobrescreve a capa baixada mesmo que ja exista em covers/.
    no_cover_cache = '--refresh-covers' in sys.argv

    for f in pdf_files:
        is_subdir = os.path.dirname(f) == 'PDF'
        pdf_path = os.path.join(LIVROS_DIR, f)
        base_name = os.path.basename(f)
        pdf_stem = base_name[:-4]

        title, author = book_meta(pdf_stem)
        epub_path = os.path.join(LIVROS_DIR, safe_filename(title) + ".epub")
        legacy_path = os.path.join(LIVROS_DIR, pdf_stem + ".epub")

        if os.path.exists(epub_path) and not force:
            print(f"  PULADO: {os.path.basename(epub_path)} ja existe. Use --force para regerar.")
            continue

        print(f"Convertendo: {base_name}")
        try:
            if no_cover_cache:
                cache = os.path.join(COVERS_DIR, safe_filename(title) + ".jpg")
                if os.path.exists(cache):
                    os.remove(cache)
            cover_data = get_cover(pdf_path, pdf_stem, title, author)
            create_epub(pdf_path, epub_path, title, author, cover_data,
                        with_images=not no_images)
            if not is_subdir and os.path.exists(pdf_path):
                move_to_pdf(pdf_path)
            if legacy_path != epub_path and os.path.exists(legacy_path):
                os.remove(legacy_path)
                print(f"  Removido nome antigo: {os.path.basename(legacy_path)}")
        except Exception as e:
            print(f"  ERRO em {base_name}: {e}")

    print("\nConversao completa!")


if __name__ == '__main__':
    main()
