---
name: spreadsheet-preprocess
description: Marks spreadsheet-like sources as a known pending preprocessing capability for Project_R. Use when Project_R encounters CSV, TSV, XLS, XLSX, XLSM, quotations, contact lists, schedules, or tabular business records before a reviewed spreadsheet extractor exists.
---

# Spreadsheet Preprocess

## Current B1 behavior

This Skill is intentionally a pending-capability placeholder.

Project_R must recognise spreadsheet files as a future supported preprocessor type, but B1 must not turn them into GBrain-ready Markdown until a reviewed table extraction workflow exists.

Supported pending extensions:

- `.csv`
- `.tsv`
- `.xls`
- `.xlsx`
- `.xlsm`

## Required manifest state

When a project workspace contains a spreadsheet source, Project_R records:

```yaml
file_kind: spreadsheet
extraction_complexity: pending_capability
extractor_profile: pending_extractor_capability
status: pending_extractor_capability
extraction_status: pending_spreadsheet_extraction
preprocess_skill: spreadsheet-preprocess
preprocess_status: pending_capability
```

No final Markdown is written to `gbrain-ready/`.
No GBrain sync/import is triggered for the spreadsheet file itself.

## Why it is pending

Spreadsheet files often contain merged cells, formulas, hidden sheets, multi-table layouts, row/column headers with visual meaning, contact data, quotations, and commercially sensitive numbers.

Until extraction is implemented and reviewed, Project_R must preserve the original file and expose a clear pending state instead of producing low-confidence Markdown.

## Future implementation boundary

When implemented, this Skill should produce GBrain-friendly Markdown with:

- workbook and sheet inventory
- table summaries
- key entities such as people, companies, projects, products, locations, dates, and currencies
- evidence references using sheet names and row/column coordinates
- formula/merged-cell/hidden-sheet warnings
- bilingual `zh/en` aligned facts when the source is business-facing

## Rejection rules

Do not:

- parse spreadsheet bytes with ad hoc string matching
- flatten formulas without marking them as formulas
- drop sheet names, row numbers, or column evidence
- send contact lists or commercial pricing into company-wide sources without source-scope checks
- create `gbrain-ready/` Markdown while this Skill is still in pending-capability mode
