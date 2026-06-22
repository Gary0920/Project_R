"""Batch extract 4 standards using A版 (pdf_structured.py)."""
import sys
import os
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(str(backend_dir))

from dotenv import load_dotenv
load_dotenv()

from app.features.preprocessing.pdf_structured import extract_pdf_structured_markdown

SOURCE_DIR = Path("workspace_data/project/BFI/nini/90-通用上传资料/01-PDF与报告")
OUTPUT_DIR = Path("workspace_data/project/BFI/nini/90-通用上传资料/PDF提炼报告")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

os.environ["MIMO_MAX_TOKENS"] = "16384"
os.environ["MIMO_TIMEOUT_SECONDS"] = "300"
os.environ["LLM_TIMEOUT_SECONDS"] = "300"

PDFs = [
    "ANSI ASHRAE Standard 160-2021.pdf",
    "AS 5216-2021.pdf",
    "AS NZS 4859.1-2018+ Amd 1-2024.pdf",
    "ISO 9224-2012.pdf",
]

print(f"Source: {SOURCE_DIR}")
print(f"Output: {OUTPUT_DIR}")
print(f"Files: {len(PDFs)}")
print()

for i, name in enumerate(PDFs, 1):
    pdf_path = SOURCE_DIR / name
    out_name = f"{pdf_path.stem} 结构化提炼.md"
    out_path = OUTPUT_DIR / out_name

    print(f"[{i}/{len(PDFs)}] {name}")
    if not pdf_path.exists():
        print(f"  SKIP: file not found")
        continue

    try:
        result = extract_pdf_structured_markdown(pdf_path)
        out_path.write_text(result.markdown, encoding="utf-8")
        print(f"  OK: {result.page_count} pages, {len(result.markdown)} chars, {len(result.markdown.splitlines())} lines")
        print(f"  Saved: {out_path}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    print()

print("Done")
