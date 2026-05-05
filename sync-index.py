#!/usr/bin/env python3
"""Sync _index.md with EPUB books in a content directory.

For each EPUB, extract the cover to static/covers/ and generate a Hextra
{{< card >}} entry in the sibling _index.md.

Usage:
    ./sync-index.py content/books/文学/

The script preserves existing front matter in _index.md and only
replaces the content body with an auto-generated card grid.
"""

import os
import sys
import re
import zipfile
import xml.etree.ElementTree as ET
import urllib.parse
from pathlib import Path
from io import BytesIO

PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_COVERS = PROJECT_ROOT / "static" / "covers"
MARKER = "<!-- AUTO_GENERATED_CARDS -->"


def extract_epub_info(epub_path: Path) -> dict | None:
    """Extract title and cover image from an EPUB file."""
    try:
        with zipfile.ZipFile(epub_path) as zf:
            # Locate OPF file via container.xml
            with zf.open("META-INF/container.xml") as f:
                tree = ET.parse(f)
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfile = tree.find(".//c:rootfile", ns)
            if rootfile is None:
                return None
            opf_path = rootfile.get("full-path")

            with zf.open(opf_path) as f:
                tree = ET.parse(f)
            opf_root = tree.getroot()

            ns_opf = {
                "opf": "http://www.idpf.org/2007/opf",
                "dc": "http://purl.org/dc/elements/1.1/",
            }

            # Extract title
            title_el = opf_root.find(".//dc:title", ns_opf)
            title = title_el.text.strip() if title_el is not None and title_el.text else epub_path.stem

            # Find cover image
            cover_href = None
            cover_mime = None

            # Check meta cover first
            cover_id = None
            for meta in opf_root.findall(".//opf:meta", ns_opf):
                if meta.get("name") == "cover":
                    cover_id = meta.get("content")
                    break

            for item in opf_root.findall(".//opf:item", ns_opf):
                pid = item.get("id", "")
                href = item.get("href", "")
                mtype = item.get("media-type", "")
                props = item.get("properties", "")
                if cover_id and pid == cover_id:
                    cover_href = href
                    cover_mime = mtype
                    break
                if "cover-image" in (props or ""):
                    cover_href = href
                    cover_mime = mtype
                    break
                if pid == "cover-image":
                    cover_href = href
                    cover_mime = mtype
                    break

            # Convert relative OPF path to absolute within ZIP
            if cover_href:
                opf_dir = os.path.dirname(opf_path)
                if opf_dir and not opf_dir.endswith("/"):
                    opf_dir += "/"
                cover_zip_path = opf_dir + cover_href if opf_dir else cover_href
                # Normalize
                cover_zip_path = os.path.normpath(cover_zip_path)

                try:
                    cover_data = zf.read(cover_zip_path)
                except KeyError:
                    # Try without directory prefix
                    cover_data = zf.read(cover_href)

                return {
                    "title": title,
                    "cover_data": cover_data,
                    "cover_mime": cover_mime or "image/jpeg",
                    "epub_stem": epub_path.stem,
                }
            else:
                return {
                    "title": title,
                    "cover_data": None,
                    "cover_mime": "image/jpeg",
                    "epub_stem": epub_path.stem,
                }
    except Exception as e:
        print(f"  Warning: failed to parse {epub_path.name}: {e}", file=sys.stderr)
        return None


def save_cover(book: dict, epub_stem: str) -> str | None:
    """Save cover image to static/covers/ and return the URL path."""
    if not book["cover_data"]:
        return None

    STATIC_COVERS.mkdir(parents=True, exist_ok=True)

    mime_to_ext = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    ext = mime_to_ext.get(book.get("cover_mime", "image/jpeg"), ".jpg")

    # Slugify the stem for a safe filename
    safe_name = re.sub(r"[^\w\-]", "_", epub_stem)
    filename = safe_name + ext
    filepath = STATIC_COVERS / filename

    # Only overwrite if changed
    existing = filepath.read_bytes() if filepath.exists() else b""
    if existing != book["cover_data"]:
        filepath.write_bytes(book["cover_data"])
        print(f"  Cover saved: /covers/{filename}")
    else:
        print(f"  Cover unchanged: /covers/{filename}")

    return f"/covers/{filename}"


def make_slug(filename: str) -> str:
    """Turn a Chinese filename into a sane slug for links."""
    return filename


def generate_index_md(directory: Path, books: list[dict]):
    """Generate or update _index.md with Hextra card entries."""
    index_path = directory / "_index.md"

    # Read existing front matter
    fm_lines = []
    fm_open = False
    existing_content = []

    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        i = 0
        if lines and lines[0].strip() == "---":
            fm_lines.append(lines[0])
            i = 1
            while i < len(lines):
                fm_lines.append(lines[i])
                if lines[i].strip() == "---":
                    i += 1
                    break
                i += 1
        existing_content = lines[i:]

    # Build card entries
    card_lines = []
    for book in books:
        epub_stem = book["epub_stem"]
        slug = make_slug(epub_stem)
        link = f"./{slug}/"
        title = book["title"]
        cover_url = book.get("cover_url", "")
        if cover_url:
            card_lines.append(
                f'  {{{{< card link="{link}" title="{title}" image="{cover_url}" imageStyle="max-height:200px;object-fit:cover" >}}}}'
            )
        else:
            card_lines.append(
                f'  {{{{< card link="{link}" title="{title}" >}}}}'
            )

    # Build output
    out = []
    # Front matter
    for line in fm_lines:
        out.append(line)
    if not fm_lines:
        # Default front matter
        folder_name = directory.name
        out.append("---")
        out.append(f"title: {folder_name}")
        out.append("type: docs")
        out.append("sidebar:")
        out.append("  open: true")
        out.append("---")

    out.append("")
    out.append(MARKER)

    if card_lines:
        out.append("")
        out.append("{{< cards >}}")
        out.extend(card_lines)
        out.append("{{< /cards >}}")
    else:
        out.append("")
        out.append(f"该目录下暂无书籍。")

    result = "\n".join(out) + "\n"
    index_path.write_text(result, encoding="utf-8")
    print(f"  _index.md updated ({len(books)} books)")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <content-directory>", file=sys.stderr)
        print(f"Example: {sys.argv[0]} content/books/文学/", file=sys.stderr)
        sys.exit(1)

    target = Path(sys.argv[1])
    if not target.is_dir():
        print(f"Error: {target} is not a directory", file=sys.stderr)
        sys.exit(1)

    epub_files = sorted(target.glob("*.epub"))
    if not epub_files:
        print(f"No EPUB files found in {target}")
        # Still generate empty _index.md
        generate_index_md(target, [])
        return

    print(f"Found {len(epub_files)} EPUB(s) in {target}")
    books = []

    for epub_path in epub_files:
        print(f"Processing: {epub_path.name}")
        info = extract_epub_info(epub_path)
        if not info:
            continue

        cover_url = save_cover(info, epub_path.stem)

        # Determine display title: prefer filename-derived short title over full metadata title
        short_title = re.sub(r"[（(][^)）]*[)）]$", "", epub_path.stem).strip()
        display_title = short_title or info["title"]

        book = {
            "epub_stem": epub_path.stem,
            "title": display_title,
            "cover_url": cover_url,
        }
        books.append(book)

    generate_index_md(target, books)


if __name__ == "__main__":
    main()
