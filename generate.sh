#!/bin/bash
# ============================================================
# generate.sh — 扫描 content/ 下的 .epub 文件，自动生成 .md 页面
#
# 用法：
#   ./generate.sh               # 扫描所有 .epub，生成缺失的 .md
#   ./generate.sh --force       # 强制覆盖所有已存在的 .md
# ============================================================

set -euo pipefail

FORCE=false

for arg in "$@"; do
    if [[ "$arg" == "--force" ]]; then
        FORCE=true
    fi
done

echo "Scanning content/ for .epub files..."
echo ""

count=0
skipped=0

while IFS= read -r -d '' epub; do
    dir=$(dirname "$epub")
    epub_filename=$(basename "$epub")

    # 去掉 .epub 后缀
    epub_name="${epub_filename%.epub}"

    # 对应的 .md 文件路径
    md_file="${dir}/${epub_name}.md"

    # 提取书名：取第一个中文/英文括号之前的内容
    title=$(echo "$epub_name" | sed -E 's/[（(].*//' | xargs)

    # 如果提取后为空，就用原文件名
    if [[ -z "$title" ]]; then
        title="$epub_name"
    fi

    # 检查是否跳过已存在的文件
    if [[ -f "$md_file" ]]; then
        if grep -q "<!-- EPUB_AUTO_GENERATED -->" "$md_file" 2>/dev/null; then
            if [[ "$FORCE" != "true" ]]; then
                echo "  Skip (auto-generated, exists): $md_file"
                skipped=$((skipped + 1))
                continue
            fi
            echo "  Regenerate (--force): $md_file"
        else
            echo "  Skip (manual, preserve): $md_file"
            skipped=$((skipped + 1))
            continue
        fi
    else
        echo "  Generate: $md_file  ($title)"
    fi

    cat > "$md_file" << MDEOF
---
title: "${title}"
type: docs
---

<!-- EPUB_AUTO_GENERATED -->

{{< epub-reader "${epub_filename}" >}}
MDEOF

    count=$((count + 1))
done < <(find content -name "*.epub" -print0)

echo ""
echo "Done: generated $count page(s), skipped $skipped"
