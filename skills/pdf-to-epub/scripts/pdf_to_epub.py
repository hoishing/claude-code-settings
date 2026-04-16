# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "mistralai>=1.0,<2",
#     "openai",
#     "pymupdf",
#     "pypandoc-binary",
#     "ebooklib",
#     "beautifulsoup4",
#     "lxml",
# ]
# ///
"""
pdf_to_epub — convert a PDF to EPUB via OCR.

Two OCR providers:
  - mistral:    mistral-ocr-latest (text + embedded images, paid)
  - openrouter: google/gemma-4-31b-it:free (text only, free)

API keys come from MISTRAL_API_KEY / OPENROUTER_API_KEY in the process
environment, never from CLI flags.
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import sys
from base64 import b64decode
from pathlib import Path

import pymupdf
import pypandoc
from bs4 import BeautifulSoup
from ebooklib.epub import (
    EpubBook,
    EpubHtml,
    EpubItem,
    EpubNav,
    EpubNcx,
    Link,
    write_epub,
)
from openai import OpenAI

MISTRAL_MODEL = "mistral-ocr-latest"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "google/gemma-4-31b-it:free"
QWEN_PROMPT = (
    "Extract all text from this page as markdown. "
    "Use # / ## / ### for headings. "
    "Preserve lists, tables, code blocks, and inline emphasis. "
    "Do not describe images; only transcribe text. "
    "Output only the markdown, with no preamble or explanation."
)


# ============================================================ OCR providers


def mistral_ocr(pdf_path: Path) -> tuple[str, dict[str, bytes]]:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("error: MISTRAL_API_KEY not set in environment")

    from mistralai import Mistral

    client = Mistral(api_key=api_key)
    log(f"[mistral] uploading {pdf_path.name}")
    uploaded = client.files.upload(
        file={"file_name": pdf_path.name, "content": pdf_path.read_bytes()},
        purpose="ocr",
    )
    signed = client.files.get_signed_url(file_id=uploaded.id)
    log("[mistral] running ocr")
    response = client.ocr.process(
        model=MISTRAL_MODEL,
        document={"type": "document_url", "document_url": signed.url},
        include_image_base64=True,
    )

    markdown_parts: list[str] = []
    images: dict[str, bytes] = {}
    for page in response.pages:
        markdown_parts.append(page.markdown)
        for img in page.images:
            if not img.image_base64:
                continue
            data = img.image_base64
            if "," in data:
                data = data.split(",", 1)[1]
            images[img.id] = b64decode(data)

    log(f"[mistral] {len(response.pages)} pages, {len(images)} images")
    return "\n\n".join(markdown_parts), images


def qwen_ocr(pdf_path: Path, dpi: int) -> tuple[str, dict[str, bytes]]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("error: OPENROUTER_API_KEY not set in environment")

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    doc = pymupdf.open(pdf_path)
    total = len(doc)
    markdown_parts: list[str] = []

    for page_num, page in enumerate(doc, start=1):
        log(f"[qwen] page {page_num}/{total}")
        pix = page.get_pixmap(dpi=dpi)
        img_b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": QWEN_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            },
                        },
                    ],
                }
            ],
        )
        markdown_parts.append(response.choices[0].message.content or "")

    doc.close()
    log(
        "[qwen] note: fallback mode drops embedded images. "
        "use --provider mistral for image-fidelity EPUBs."
    )
    return "\n\n".join(markdown_parts), {}


# ============================================================ markdown → epub


def markdown_to_html(md: str) -> str:
    return pypandoc.convert_text(
        md, to="html", format="md", extra_args=["--mathml"]
    )


def ensure_heading_ids(soup: BeautifulSoup) -> None:
    for idx, el in enumerate(soup.find_all(["h1", "h2"])):
        if not el.get("id"):
            el["id"] = f"{el.name}-{idx}"


def build_toc(soup: BeautifulSoup, depth: int) -> tuple:
    def link(el) -> Link:
        return Link(
            f"main.xhtml#{el.get('id')}",
            el.get_text(strip=True),
            el.get("id"),
        )

    if depth == 1:
        h1s = soup.find_all("h1")
        if h1s:
            return tuple(link(h1) for h1 in h1s)
        return (Link("main.xhtml", "Main", "main"),)

    headings = soup.find_all(["h1", "h2"])
    if not headings:
        return (Link("main.xhtml", "Main", "main"),)

    if not any(el.name == "h1" for el in headings):
        log("[toc] no h1 headings; demoting to flat h2 toc")
        return tuple(link(el) for el in headings if el.name == "h2")

    entries: list = []
    current_h1: Link | None = None
    current_h2s: list[Link] = []

    def flush() -> None:
        nonlocal current_h1, current_h2s
        if current_h1 is None:
            return
        if current_h2s:
            entries.append((current_h1, tuple(current_h2s)))
        else:
            entries.append(current_h1)
        current_h1 = None
        current_h2s = []

    for el in headings:
        el_link = link(el)
        if el.name == "h1":
            flush()
            current_h1 = el_link
        else:
            if current_h1 is None:
                # Orphan h2 before the first h1 — keep it as a top-level entry
                entries.append(el_link)
            else:
                current_h2s.append(el_link)
    flush()

    return tuple(entries)


def build_epub(
    markdown: str,
    images: dict[str, bytes],
    title: str,
    author: str,
    toc_depth: int,
    cover_path: Path | None,
    output_path: Path,
) -> None:
    html = markdown_to_html(markdown)
    soup = BeautifulSoup(html, "lxml")
    ensure_heading_ids(soup)

    book = EpubBook()
    book.set_identifier(f"id-{output_path.stem}")
    book.set_title(title)
    book.add_author(author)

    if cover_path is not None:
        book.set_cover(cover_path.name, cover_path.read_bytes())

    body = soup.body
    body_html = body.decode_contents() if body else str(soup)

    chapter = EpubHtml(
        title="Main",
        file_name="main.xhtml",
        content=body_html,
        media_type="application/xhtml+xml",
    )
    book.add_item(chapter)
    book.spine = ["nav", chapter]

    book.toc = build_toc(soup, toc_depth)
    book.add_item(EpubNcx())
    book.add_item(EpubNav())

    for img_name, img_bytes in images.items():
        mime, _ = mimetypes.guess_type(img_name)
        if not (mime and mime.startswith("image")):
            continue
        book.add_item(
            EpubItem(
                uid=img_name,
                file_name=img_name,
                media_type=mime,
                content=img_bytes,
            )
        )

    write_epub(str(output_path), book)


# ============================================================ cli


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a PDF to EPUB via OCR"
    )
    parser.add_argument("--pdf", type=Path, required=True, help="input PDF path")
    parser.add_argument(
        "--provider",
        choices=["mistral", "openrouter"],
        required=True,
        help="OCR provider",
    )
    parser.add_argument(
        "--toc-depth",
        type=int,
        choices=[1, 2],
        default=1,
        help="TOC depth: 1 (h1 only) or 2 (h1 + h2)",
    )
    parser.add_argument("--cover", type=Path, default=None, help="cover image path")
    parser.add_argument("--output", type=Path, default=None, help="output EPUB path")
    parser.add_argument("--title", default=None, help="book title")
    parser.add_argument("--author", default="Unknown", help="book author")
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="page rasterization DPI for the openrouter provider",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file():
        sys.exit(f"error: pdf not found: {pdf_path}")

    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else pdf_path.with_suffix(".epub")
    )
    title = args.title or pdf_path.stem

    cover_path: Path | None = None
    if args.cover is not None:
        resolved_cover = args.cover.expanduser().resolve()
        if not resolved_cover.is_file():
            sys.exit(f"error: cover image not found: {resolved_cover}")
        cover_path = resolved_cover

    log(f"[ocr] provider={args.provider} pdf={pdf_path.name}")
    if args.provider == "mistral":
        markdown, images = mistral_ocr(pdf_path)
    else:
        markdown, images = qwen_ocr(pdf_path, args.dpi)

    log(
        f"[epub] building title={title!r} toc-depth={args.toc_depth} "
        f"images={len(images)} cover={cover_path.name if cover_path else 'none'}"
    )
    build_epub(
        markdown=markdown,
        images=images,
        title=title,
        author=args.author,
        toc_depth=args.toc_depth,
        cover_path=cover_path,
        output_path=output_path,
    )

    print(str(output_path))


if __name__ == "__main__":
    main()
