"""Split AS 2047 PDF into two halves, extract each separately, then combine."""
import sys
import os
import tempfile
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(str(backend_dir))

from dotenv import load_dotenv
load_dotenv()

from app.features.preprocessing.pdf_structured import (
    extract_pdf_structured_markdown,
    load_pdf_extraction_options,
)

PDF_PATH = Path(
    "D:/Zion/AI/Project_R/Project_R/backend/workspace_data/project/BFI/nini/"
    "90-通用上传资料/PDF预处理测试/AS 2047-2014 (2017).pdf"
)

OUTPUT_DIR = PDF_PATH.parent
OUTPUT_PATH = OUTPUT_DIR / "AS 2047-2014 (2017) 结构化提炼.md"

# Increase output token limit for MiMo V2.5
os.environ["MIMO_MAX_TOKENS"] = "16384"
os.environ["MIMO_TIMEOUT_SECONDS"] = "300"
os.environ["LLM_TIMEOUT_SECONDS"] = "300"

print(f"Source PDF: {PDF_PATH}")
print(f"Output:     {OUTPUT_PATH}")
print(f"MIMO_MAX_TOKENS: {os.environ.get('MIMO_MAX_TOKENS')}")
print()

# Split PDF into two halves
import fitz

doc = fitz.open(str(PDF_PATH))
total_pages = doc.page_count
mid = total_pages // 2
print(f"Total pages: {total_pages}, splitting at page {mid}")

# Create temp PDFs for each half
tmp_dir = Path(tempfile.mkdtemp())
part1_path = tmp_dir / "part1.pdf"
part2_path = tmp_dir / "part2.pdf"

part1_doc = fitz.open()
part1_doc.insert_pdf(doc, from_page=0, to_page=mid - 1)
part1_doc.save(str(part1_path))
part1_doc.close()

part2_doc = fitz.open()
part2_doc.insert_pdf(doc, from_page=mid, to_page=total_pages - 1)
part2_doc.save(str(part2_path))
part2_doc.close()
doc.close()

print(f"Part 1: pages 1-{mid} -> {part1_path}")
print(f"Part 2: pages {mid+1}-{total_pages} -> {part2_path}")
print()

results = []
for i, (part_path, page_range) in enumerate([(part1_path, f"1-{mid}"), (part2_path, f"{mid+1}-{total_pages}")], 1):
    print(f"=== Extracting Part {i} ({page_range}) ===")
    try:
        result = extract_pdf_structured_markdown(part_path)
        results.append(result)
        print(f"  Done: {result.pages_analyzed} pages, {len(result.markdown)} chars")
        print(f"  Token usage: {result.token_usage}")
        if result.warnings:
            for w in result.warnings:
                print(f"  Warning: {w}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    print()

# Combine results
if len(results) == 2:
    # Use part 1's title as the main title, append part 2's content
    part1_lines = results[0].markdown.split("\n")
    part2_lines = results[1].markdown.split("\n")

    # Find where part 2's actual content starts (skip its title if it has one)
    part2_start = 0
    for j, line in enumerate(part2_lines):
        if line.startswith("## "):
            part2_start = j
            break

    combined = results[0].markdown.rstrip() + "\n\n---\n\n" + "\n".join(part2_lines[part2_start:])
    OUTPUT_PATH.write_text(combined, encoding="utf-8")
    print(f"Combined output saved to: {OUTPUT_PATH}")
    print(f"  Size: {len(combined)} chars, {len(combined.split(chr(10)))} lines")
    total_tokens = {
        "input_tokens": sum(r.token_usage.get("input_tokens", 0) for r in results),
        "output_tokens": sum(r.token_usage.get("output_tokens", 0) for r in results),
    }
    print(f"  Total tokens: {total_tokens}")
elif len(results) == 1:
    OUTPUT_PATH.write_text(results[0].markdown, encoding="utf-8")
    print(f"Single part output saved to: {OUTPUT_PATH}")
else:
    print("ERROR: No results to combine")
    sys.exit(1)

# Cleanup temp files
part1_path.unlink(missing_ok=True)
part2_path.unlink(missing_ok=True)
tmp_dir.rmdir()
print("\nTemp files cleaned up.")
