# PRD: 8.D Project Knowledge Quality and File Preview

Version: v1.0  
Date: 2026-06-09  
Owner: Gary  
Status: Ready for agent implementation

## Problem Statement

Project_R already has the basic project workspace, file upload, project source ingest, GBrain sync, and `/query` path. The current problem is quality: users can place real project files into a project workspace, but the system cannot yet reliably answer practical project questions across drawings, schedules, screenshots, spreadsheets, emails, meeting recordings, and Office documents.

From the user's perspective, this means the knowledge base may look like it has ingested the files, but answers can still be wrong, vague, hard to verify, or sourced from the wrong file type. The clearest current failure is that drawing and payment screenshot questions can rank noisy meeting transcript chunks above the actual drawing or screenshot evidence. This breaks trust in the project knowledge base and directly affects whether the software feels useful.

8.D exists to move Project_R from "files can be synced" to "project knowledge can be trusted, inspected, and quality-regressed."

## Solution

Build a project knowledge quality layer around Project_R project workspaces. The solution has four product outcomes:

1. Project files are preprocessed according to their real file type and business meaning.
2. Project queries prefer the right class of source before asking GBrain to answer.
3. Answers include source evidence that can be opened in preview and inspected.
4. A repeatable 8.D quality report shows exactly which project questions pass, fail, or remain known gaps.

The first production-quality target is the TEST project sample set. It intentionally contains mixed real project files and mixed project names; this is acceptable because the test is about file capability and retrieval behavior, not project identity consistency.

## User Stories

1. As a project member, I want to ask a drawing question and have the system search drawings first, so that meeting transcripts do not outrank technical evidence.
2. As a project member, I want a screenshot payment question to return the payment screenshot, so that I can trust the answer came from the right file.
3. As a project member, I want the system to answer from emails when I ask about an email thread, so that project correspondence can be queried directly.
4. As a project member, I want material list questions to search spreadsheets, so that Excel project records are not invisible to the knowledge base.
5. As a project member, I want meeting questions to search meeting transcripts and media, so that discussions, decisions, and action items can be recovered.
6. As a project member, I want answers to show the original source file, so that I can verify important project information.
7. As a project member, I want PDF answers to include page references, so that I can quickly inspect the drawing or schedule page.
8. As a project member, I want screenshot answers to include the image source and relevant field, so that I can verify OCR or visual extraction.
9. As a project member, I want spreadsheet answers to include sheet and row references, so that I can check the original table.
10. As a project member, I want meeting answers to include timestamps, so that I can replay or inspect the relevant meeting moment.
11. As a project member, I want the system to say when a source was not extracted well enough, so that I do not mistake a weak answer for a verified fact.
12. As a project member, I want drawing schedule questions to return durations and dates from the programme PDF, so that project planning questions are answerable.
13. As a project member, I want window schedule questions to return window identifiers and dimensions, so that drawing tables become usable knowledge.
14. As a project member, I want payment screenshot questions to return normalized amount fields, so that financial screenshots can be queried consistently.
15. As a project member, I want internal contact sheet questions to return replenishment reason and replenishment items, so that change and variation records are searchable.
16. As a project member, I want noisy meeting transcripts to be downweighted for non-meeting questions, so that low-quality ASR does not pollute the whole project source.
17. As a project administrator, I want to see which files are compiled, pending, failed, or ignored, so that ingest quality can be managed.
18. As a project administrator, I want unsupported files to remain pending capability rather than polluting GBrain, so that the knowledge base stays trustworthy.
19. As a project administrator, I want a regression report for the TEST project, so that quality changes are measurable after each implementation.
20. As a project administrator, I want known gaps to be listed without failing the whole regression, so that unfinished capabilities remain visible but do not block unrelated progress.
21. As a system administrator, I want project quality reports in the admin GBrain area, so that knowledge quality is monitored like a first-class system health signal.
22. As a system administrator, I want to see the first hit source for every regression question, so that retrieval mistakes are easy to diagnose.
23. As a system administrator, I want stale or soft-deleted source counts to be visible and correct, so that source status does not mislead operators.
24. As a developer, I want 8.D tests to run against fixtures and monkeypatched services, so that automated tests do not pollute real project data.
25. As a developer, I want a controlled TEST smoke path for real GBrain checks, so that real integration quality can be verified without touching production project directories.
26. As a developer, I want each preprocessor to be testable in isolation, so that Excel, image, drawing, meeting, and citation quality can improve independently.
27. As a developer, I want file-type intent classification to be a deep module, so that query routing can evolve without scattering ranking rules through the codebase.
28. As a developer, I want source metadata normalized across file types, so that retrieval, citation, preview, and quality reporting use the same evidence vocabulary.
29. As Gary, I want 8.D to become the main knowledge-quality gate, so that Project_R can be judged by whether real project questions are answered correctly.
30. As Gary, I want development flow and PRD to stay separate, so that product goals and engineering checklists remain clear.

## Implementation Decisions

- The PRD scope is limited to project workspace knowledge quality and file preview. It does not redefine company wiki, customer intelligence, personal workspace, or the overall GBrain architecture.
- The TEST project sample set is the canonical first acceptance dataset. Files may come from different real projects, and inconsistent project names are not regression failures.
- Project_R remains responsible for source-file preprocessing, metadata, permissions, retrieval routing, preview payloads, quality reports, and admin presentation.
- GBrain remains responsible for source sync/import, chunking, embedding, query/think, and post-Markdown knowledge capabilities.
- The first deep module should be a project quality regression runner. It should load project question cases, execute query/think checks, score results, and save structured reports.
- The second deep module should be a project query intent classifier. It should infer file-kind hints such as drawing, schedule, image, meeting, email, spreadsheet, and Office document from the user question.
- The third deep module should be a source metadata normalizer. It should expose a stable evidence vocabulary across PDF pages, image regions, spreadsheet rows, meeting timestamps, email bodies, and Office text spans.
- The fourth deep module should be a ranking adjustment layer for project retrieval. It should boost matching file types and exact metadata while downweighting unrelated or low-quality meeting transcript chunks.
- Spreadsheet preprocessing should become a first-class preprocessor, not a generic text fallback. The first version should support workbook, sheet, table header, row, material code, and sheet-row citation.
- Drawing PDF preprocessing should be improved through page classification, visual/OCR extraction, prompt refinement, table extraction, and post-processing validation before considering any custom model training.
- Schedule PDF preprocessing should extract task name, scope, duration, start, finish, predecessor, and page evidence where available.
- Image and screenshot preprocessing should output both narrative description and structured extracted fields. Payment screenshots must normalize amount, direction, payment time, payment method, and related evidence.
- Meeting media processing should use ASR terminology. TTS is out of place because TTS means text-to-speech, while this feature needs speech-to-text transcription quality.
- Meeting transcript quality should include repeated-text detection, low-quality indicators, optional ASR provider evaluation, and retrieval downweighting for non-meeting questions.
- Citation and preview should share one contract. Answers should not invent precise locations when the preprocessor only has weak evidence.
- Admin quality reporting should store and display 8.D regression reports with pass, fail, known gap, unexpected pass, wrong source, missing answer point, missing citation, and service unavailable states.
- Known gaps are valid report states. They should not count as failed should-pass tests, but they must remain visible until the relevant capability is implemented.

## Testing Decisions

- Tests should focus on external behavior: source selection, report scoring, manifest status, generated Markdown evidence, citation payloads, and user-visible quality reports.
- Tests should avoid asserting private implementation details such as exact helper function internals or temporary prompt wording.
- Automated tests must use temporary databases, temporary workspace roots, fixtures, monkeypatches, or fake adapter responses.
- Real TEST project and real GBrain smoke checks are allowed only for controlled manual or script-driven validation of the TEST project source.
- The project quality regression runner should have unit tests for fixture validation, query result scoring, known-gap handling, wrong-source classification, and report serialization.
- The project query intent classifier should have unit tests for drawing, payment screenshot, meeting, email, spreadsheet, schedule, and Office-document queries.
- The ranking adjustment layer should have tests that prove matching file types outrank noisy meeting transcript results for non-meeting questions.
- Spreadsheet preprocessing should have fixture-based tests for sheet discovery, header detection, material-code extraction, merged cells, hidden sheets, formula values, and damaged files.
- Drawing and schedule preprocessing should have post-processing tests using fixed model response fixtures, especially for page, identifier, duration, finish date, and missing-field handling.
- Image preprocessing should have fixed model response tests for payment amount normalization and missing-field behavior.
- Meeting quality control should have tests for repeated transcript reduction, quality metrics, timestamp evidence, and non-meeting downweighting.
- Citation normalization should have tests for PDF page, image region, Office text span, spreadsheet sheet-row, and meeting timestamp payloads.
- Admin report APIs should have permission tests so that full project quality reports are available only to authorized administrators.
- Frontend tests should verify that report totals, failure categories, known gaps, and first-hit sources are displayed clearly.
- Manual acceptance should use the 14 TEST project questions and record whether the first source, answer points, and citations match expectations.

## Out of Scope

- Replacing GBrain with a Project_R-built knowledge engine.
- Restoring old RAG, Chroma, Wiki Router, or vector-store fallback.
- Running ordinary Chat through GBrain automatically.
- Creating a personal workspace knowledge source.
- Changing customer intelligence scope or CRM graph behavior.
- Training a custom drawing model as the first solution step.
- Supporting every possible Excel workbook layout in the first spreadsheet release.
- Perfect image region coordinates in the first screenshot release.
- Full professional diarization for meetings in the first ASR quality release.
- Automatically deleting GBrain knowledge when project source files are deleted.
- Touching real project directories outside the TEST project quality sample.

## Further Notes

- The current TEST baseline proves that source sync alone is not a sufficient quality bar.
- The payment screenshot already contains an extractable amount, but retrieval can still rank a meeting transcript first. That makes retrieval routing and ranking a priority before adding more surface UI.
- The Excel material list remains pending capability until spreadsheet preprocessing exists.
- Drawing questions should be treated as known gaps until drawing pages and tables are extracted with enough structure to answer safely.
- Meeting transcript noise should be treated as a project-wide quality risk because one low-quality source can distort unrelated queries.
- Development execution order should remain: project query regression, file-type intent and ranking, image field extraction, spreadsheet preprocessing, drawing/schedule extraction, meeting quality control, citation/preview, admin quality report.
