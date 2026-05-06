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
from datetime import datetime
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


def parse_front_matter(text: str) -> dict[str, str]:
    """Parse simple YAML front matter: extract key/value pairs between '---' delimiters."""
    result = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return result
    for line in lines[1:]:
        line = line.strip()
        if line == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


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

        existing = {}
        is_new = False
        if md_path.exists():
            text = md_path.read_text(encoding="utf-8")
            if MARKER_MD in text:
                if not force:
                    print(f"  Skip (auto-generated, exists): {md_path.relative_to(PROJECT_ROOT)}")
                    skipped += 1
                    continue
                print(f"  Regenerate (--force): {md_path.relative_to(PROJECT_ROOT)}")
                # Read existing front matter to preserve user edits
                existing = parse_front_matter(text)
            else:
                print(f"  Skip (manual, preserve): {md_path.relative_to(PROJECT_ROOT)}")
                skipped += 1
                continue
        else:
            print(f"  Generate: {md_path.relative_to(PROJECT_ROOT)}  ({title})")
            is_new = True

        folder_name = dir_path.name
        date_str = existing.get("weight") or datetime.now().strftime("%Y%m%d")
        comments_val = existing.get("comments", "true")
        tags_val = existing.get("tags", f'["{folder_name}"]')

        # Build front matter
        fm = f'---\ntitle: "{title}"\ntype: docs\n'
        fm += f"weight: {date_str}\n"
        fm += f"comments: {comments_val}\n"
        fm += f"tags: {tags_val}\n"
        fm += "---\n"

        md_path.write_text(
            fm + f"\n{MARKER_MD}\n\n"
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
    """Turn a filename into Hugo-compatible slug.
    Strips characters that Hugo removes from Chinese slugs:
    punctuation, spaces, dots, and other non-CJK/non-alphanumeric chars."""
    return re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9-]", "", filename)


def read_front_matter(index_path: Path) -> list[str]:
    """Read front matter lines from _index.md, or empty list if absent."""
    if not index_path.exists():
        return []
    content = index_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    i = 0
    fm_lines = []
    if lines and lines[0].strip() == "---":
        fm_lines.append(lines[0])
        i = 1
        while i < len(lines):
            fm_lines.append(lines[i])
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1
    return fm_lines


def default_front_matter(title: str) -> list[str]:
    return ["---", f"title: {title}", "type: docs", "---"]


def write_index_md(index_path: Path, fm_lines: list[str], card_lines: list[str]):
    """Write _index.md with front matter and card grid."""
    # Strip sidebar.open from preserved front matter (sidebar closed by default)
    fm = [line for line in fm_lines if "sidebar:" not in line and "open: true" not in line]
    out = fm if fm else default_front_matter(index_path.parent.name)
    out.append("")
    out.append(MARKER_CARDS)
    out.append("")
    if card_lines:
        cols = min(len(card_lines), 4)
        out.append(f"{{{{< cards cols=\"{cols}\" >}}}}")
        out.extend(card_lines)
        out.append("{{< /cards >}}")
    else:
        out.append("该目录下暂无内容。")
    result = "\n".join(out) + "\n"
    index_path.write_text(result, encoding="utf-8")


def sync_index_md():
    """Sync _index.md for EPUB directories (with covers) and subdir-only directories (text cards)."""
    epubs = sorted(CONTENT_DIR.rglob("*.epub"))
    epub_dirs = {epub.parent for epub in epubs}

    # Collect all content dirs that need syncing: EPUB dirs + their ancestor dirs
    all_dirs = set(epub_dirs)
    for d in epub_dirs:
        p = d.parent
        while p != CONTENT_DIR:
            all_dirs.add(p)
            p = p.parent

    # Also include dirs with subdirs but no EPUBs (e.g. new empty categories)
    for d in CONTENT_DIR.rglob("*"):
        if d.is_dir() and d != CONTENT_DIR:
            subdirs = [x for x in d.iterdir() if x.is_dir()]
            if subdirs:
                all_dirs.add(d)

    print("Syncing _index.md with card grids...")
    print()

    for dir_path in sorted(all_dirs):
        epub_files = sorted(dir_path.glob("*.epub"))
        subdirs = sorted(x for x in dir_path.iterdir() if x.is_dir())

        if not epub_files and not subdirs:
            continue

        index_path = dir_path / "_index.md"
        rel = dir_path.relative_to(PROJECT_ROOT)
        fm_lines = read_front_matter(index_path)

        if epub_files:
            # EPUB-containing directory: cards with covers
            print(f"  {rel}/ ({len(epub_files)} book(s))")
            card_lines = []
            for epub_path in epub_files:
                info = extract_epub_info(epub_path)
                if not info:
                    continue
                cover_url = save_cover(info["cover_data"], epub_path.stem, info["cover_mime"])
                display_title = short_title(epub_path.name)
                slug = make_slug(epub_path.stem)
                link = f"./{slug}/"
                if cover_url:
                    card_lines.append(
                        f'  {{{{< card link="{link}" title="{display_title}" '
                        f'image="{cover_url}" '
                        f'imageStyle="max-height:180px;object-fit:contain" >}}}}'
                    )
                else:
                    card_lines.append(
                        f'  {{{{< card link="{link}" title="{display_title}" >}}}}'
                    )
            write_index_md(index_path, fm_lines, card_lines)
            print(f"    Updated ({len(card_lines)} cards)")

        elif subdirs and not epub_files:
            # Subdirectory-only directory: text cards linking to child dirs
            print(f"  {rel}/ ({len(subdirs)} section(s))")
            card_lines = []
            for sd in subdirs:
                # Skip hidden dirs and non-content dirs
                if sd.name.startswith("."):
                    continue
                slug = make_slug(sd.name)
                link = f"./{slug}/"
                card_lines.append(
                    f'  {{{{< card link="{link}" title="{sd.name}" >}}}}'
                )
            write_index_md(index_path, fm_lines, card_lines)
            print(f"    Updated ({len(card_lines)} cards)")

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
