#!/usr/bin/env python3
"""Update book content: scan EPUBs, generate pages, extract covers, sync _index.md, build site.

Usage:
    ./update.py               # incremental
    ./update.py --force       # force-regenerate all auto-generated pages
    ./update.py --no-build    # skip Hugo build
"""

import os
import re
import sys
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONTENT_DIR = PROJECT_ROOT / "content"
STATIC_COVERS = PROJECT_ROOT / "static" / "covers"
MARKER_MD = "<!-- EPUB_AUTO_GENERATED -->"
MARKER_CARDS = "<!-- AUTO_GENERATED_CARDS -->"


# ──────────────────────────────────────────────────────────────
# Step 1: Scan EPUBs and generate .md pages
# ──────────────────────────────────────────────────────────────

def short_title(filename: str) -> str:
    """Extract title from filename: strip everything from first paren onward."""
    name = re.sub(r"\.[^.]+$", "", filename)  # drop extension
    return re.sub(r"[（(].*", "", name).strip() or name


def generate_md_pages(force: bool):
    """Scan content/ for .epub files and generate sibling .md pages."""
    epubs = sorted(CONTENT_DIR.rglob("*.epub"))
    count = 0
    skipped = 0

    print(f"Scanning content/ for .epub files...")
    print(f"  Found {len(epubs)} EPUB(s)")
    print()

    for epub_path in epubs:
        dir_path = epub_path.parent
        epub_stem = epub_path.stem
        epub_filename = epub_path.name
        md_path = dir_path / f"{epub_stem}.md"
        title = short_title(epub_filename)

        if md_path.exists():
            text = md_path.read_text(encoding="utf-8")
            if MARKER_MD in text:
                if not force:
                    print(f"  Skip (auto-generated, exists): {md_path.relative_to(PROJECT_ROOT)}")
                    skipped += 1
                    continue
                print(f"  Regenerate (--force): {md_path.relative_to(PROJECT_ROOT)}")
            else:
                print(f"  Skip (manual, preserve): {md_path.relative_to(PROJECT_ROOT)}")
                skipped += 1
                continue
        else:
            print(f"  Generate: {md_path.relative_to(PROJECT_ROOT)}  ({title})")

        md_path.write_text(
            f'---\ntitle: "{title}"\ntype: docs\n---\n\n'
            f"{MARKER_MD}\n\n"
            f'{{{{< epub-reader "{epub_filename}" >}}}}\n',
            encoding="utf-8",
        )
        count += 1

    print(f"  Done: generated {count} page(s), skipped {skipped}")
    print()
    return count + skipped


# ──────────────────────────────────────────────────────────────
# Step 2: Extract covers + sync _index.md cards
# ──────────────────────────────────────────────────────────────

def extract_epub_info(epub_path: Path) -> dict | None:
    """Extract title and cover image bytes from an EPUB."""
    try:
        with zipfile.ZipFile(epub_path) as zf:
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

            title_el = opf_root.find(".//dc:title", ns_opf)
            title = title_el.text.strip() if title_el is not None and title_el.text else epub_path.stem

            # Locate cover image id
            cover_id = None
            for meta in opf_root.findall(".//opf:meta", ns_opf):
                if meta.get("name") == "cover":
                    cover_id = meta.get("content")
                    break

            cover_href = None
            cover_mime = None
            for item in opf_root.findall(".//opf:item", ns_opf):
                pid = item.get("id", "")
                props = item.get("properties", "")
                if cover_id and pid == cover_id:
                    cover_href = item.get("href")
                    cover_mime = item.get("media-type")
                    break
                if "cover-image" in (props or ""):
                    cover_href = item.get("href")
                    cover_mime = item.get("media-type")
                    break
                if pid == "cover-image":
                    cover_href = item.get("href")
                    cover_mime = item.get("media-type")
                    break

            cover_data = None
            if cover_href:
                opf_dir = os.path.dirname(opf_path)
                if opf_dir:
                    opf_dir += "/"
                cover_zip_path = opf_dir + cover_href if opf_dir else cover_href
                cover_zip_path = os.path.normpath(cover_zip_path)
                try:
                    cover_data = zf.read(cover_zip_path)
                except KeyError:
                    cover_data = zf.read(cover_href)

            return {
                "title": title,
                "cover_data": cover_data,
                "cover_mime": cover_mime or "image/jpeg",
                "epub_stem": epub_path.stem,
            }
    except Exception as e:
        print(f"    Warning: {epub_path.name}: {e}", file=sys.stderr)
        return None


def save_cover(cover_data: bytes, epub_stem: str, mime: str) -> str | None:
    """Save cover image to static/covers/, return /covers/... URL."""
    if not cover_data:
        return None

    STATIC_COVERS.mkdir(parents=True, exist_ok=True)
    mime_to_ext = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg",
        "image/png": ".png", "image/gif": ".gif",
        "image/webp": ".webp", "image/bmp": ".bmp",
    }
    ext = mime_to_ext.get(mime, ".jpg")
    safe_name = re.sub(r"[^\w\-]", "_", epub_stem)
    filename = safe_name + ext
    filepath = STATIC_COVERS / filename

    existing = filepath.read_bytes() if filepath.exists() else b""
    if existing != cover_data:
        filepath.write_bytes(cover_data)
        print(f"    Cover saved: /covers/{filename}")
    else:
        print(f"    Cover unchanged: /covers/{filename}")
    return f"/covers/{filename}"


def make_slug(filename: str) -> str:
    """Turn a filename into Hugo-compatible slug (strip ：：（）())."""
    slug = filename
    for ch in "：:（）()":
        slug = slug.replace(ch, "")
    return slug


def sync_index_md():
    """For each content directory containing EPUBs, update _index.md with cards."""
    epubs = sorted(CONTENT_DIR.rglob("*.epub"))
    dirs = sorted({epub.parent for epub in epubs})

    print("Syncing _index.md with card grids...")
    print()

    for dir_path in dirs:
        epub_files = sorted(dir_path.glob("*.epub"))
        if not epub_files:
            continue

        index_path = dir_path / "_index.md"
        print(f"  {dir_path.relative_to(PROJECT_ROOT)}/ ({len(epub_files)} book(s))")

        # Read existing front matter
        fm_lines = []
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

        books = []
        for epub_path in epub_files:
            info = extract_epub_info(epub_path)
            if not info:
                continue

            cover_url = save_cover(info["cover_data"], epub_path.stem, info["cover_mime"])
            display_title = short_title(epub_path.name)
            books.append({
                "epub_stem": epub_path.stem,
                "title": display_title,
                "cover_url": cover_url,
            })

        # Build output
        out = []
        if fm_lines:
            out.extend(fm_lines)
        else:
            out.extend([
                "---",
                f"title: {dir_path.name}",
                "type: docs",
                "sidebar:",
                "  open: true",
                "---",
            ])

        out.append("")
        out.append(MARKER_CARDS)

        if books:
            cols = min(len(books), 4)
            out.append("")
            out.append(f"{{{{< cards cols=\"{cols}\" >}}}}")
            for book in books:
                slug = make_slug(book["epub_stem"])
                link = f"./{slug}/"
                if book["cover_url"]:
                    out.append(
                        f'  {{{{< card link="{link}" title="{book["title"]}" '
                        f'image="{book["cover_url"]}" '
                        f'imageStyle="max-height:180px;object-fit:contain" >}}}}'
                    )
                else:
                    out.append(
                        f'  {{{{< card link="{link}" title="{book["title"]}" >}}}}'
                    )
            out.append("{{< /cards >}}")
        else:
            out.append("")
            out.append("该目录下暂无书籍。")

        result = "\n".join(out) + "\n"
        index_path.write_text(result, encoding="utf-8")
        print(f"    Updated ({len(books)} cards)")

    print()


# ──────────────────────────────────────────────────────────────
# Step 3: Hugo build
# ──────────────────────────────────────────────────────────────

def build_site():
    """Run Hugo build."""
    print("Building site with Hugo...")
    subprocess.run(
        ["hugo", "--gc", "--minify"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    print("Done.")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    force = "--force" in sys.argv
    no_build = "--no-build" in sys.argv

    print("=" * 50)
    print("  Update")
    print("=" * 50)
    print()

    # Step 1: Generate .md pages
    generate_md_pages(force)

    # Step 2: Extract covers + sync _index.md
    sync_index_md()

    # Step 3: Build
    if not no_build:
        build_site()


if __name__ == "__main__":
    main()
