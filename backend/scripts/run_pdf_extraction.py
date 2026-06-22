"""Run standard PDF preprocessing on AS 2047-2014 and save output to target directory."""
import sys
import os
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
OUTPUT_PATH = OUTPUT_DIR / f"{PDF_PATH.stem} 结构化提炼.md"

print(f"Source PDF: {PDF_PATH}")
print(f"Output:     {OUTPUT_PATH}")
print()

# Increase output token limit for MiMo V2.5 to support full knowledge manual output
os.environ["MIMO_MAX_TOKENS"] = "16384"
# Increase timeout because MiMo V2.5 with vision + large output needs more time
os.environ["MIMO_TIMEOUT_SECONDS"] = "300"
os.environ["LLM_TIMEOUT_SECONDS"] = "300"

print(f"MIMO_MAX_TOKENS: {os.environ.get('MIMO_MAX_TOKENS')}")
print(f"Timeout: {os.environ.get('MIMO_TIMEOUT_SECONDS')}s")
print()

mimo_key = os.environ.get("MIMO_API_KEYS", "")
if not mimo_key:
    print("ERROR: MIMO_API_KEYS not found in .env!")
    sys.exit(1)
print(f"MiMo API key: SET (prefix: {mimo_key[:10]}...)")
print()

print("Starting PDF extraction... This may take several minutes.")
print()

try:
    result = extract_pdf_structured_markdown(PDF_PATH)
    print(f"Extraction complete!")
    print(f"  Pages: {result.page_count}")
    print(f"  Pages analyzed: {result.pages_analyzed}")
    print(f"  Model profile: {result.model_profile}")
    print(f"  Provider: {result.provider}")
    print(f"  Model: {result.model}")
    print(f"  Token usage: {result.token_usage}")
    print(f"  Subkind: {result.pdf_subkind}")
    print(f"  Vision pages: {result.vision_pages}")
    print(f"  Vision images: {result.vision_image_count}")
    print(f"  Review status: {result.review_status}")
    if result.warnings:
        print(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")

    OUTPUT_PATH.write_text(result.markdown, encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")
    print(f"Output size: {len(result.markdown)} chars, {len(result.markdown.splitlines())} lines")

except Exception as e:
    print(f"\nERROR during extraction: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
