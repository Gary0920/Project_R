import json
import os
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

import core.gbrain_project_ingest as project_ingest
from core.email_structured_extraction import EmailStructuredExtractionResult
from core.extractor_classifier import ExtractorClassification
from core.gbrain import GBrainSettings
from core.gbrain_project_ingest import PROJECT_INGEST_MANIFEST_NAME, compile_project_workspace_sources
from core.image_structured_extraction import ImageStructuredExtractionResult
from core.media_transcription import MediaTranscriptionResult
from core.pdf_structured_extraction import PDFStructuredExtractionResult


class GBrainProjectIngestTests(unittest.TestCase):
    def setUp(self):
        self._preprocessed_dir = tempfile.TemporaryDirectory()
        self.preprocessed_root = Path(self._preprocessed_dir.name)
        self._env = patch.dict(os.environ, {"GBRAIN_PREPROCESSED_ROOT": str(self.preprocessed_root)})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._preprocessed_dir.cleanup()

    def _settings(self) -> GBrainSettings:
        return GBrainSettings(enabled=False, base_url="", local_git_enabled=False)

    def _workspace(self, root: Path):
        return SimpleNamespace(
            id=7,
            brand="BFI",
            slug="BG007",
            name="BG007",
            storage_path=str(root),
            workspace_kind="project",
        )

    def _project_ready(self) -> Path:
        return self.preprocessed_root / "project" / "BFI" / "7-BG007" / "gbrain-ready"

    def _project_manifests(self) -> Path:
        return self.preprocessed_root / "project" / "BFI" / "7-BG007" / "manifests"

    def test_compiles_project_markdown_to_project_derived_with_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            source_dir = root / "03-会议纪要"
            source_dir.mkdir(parents=True)
            source = source_dir / "启动会.md"
            source.write_text("# 启动会\n\n项目决定使用黑色窗框。\n", encoding="utf-8")
            generated = root / "derived" / "meetings" / "generated.md"
            generated.parent.mkdir(parents=True)
            generated.write_text("must not be rescanned", encoding="utf-8")
            manifest_dir = root / "manifests"
            manifest_dir.mkdir()
            (manifest_dir / "old.json").write_text("{}", encoding="utf-8")

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                enable_pdf_structured_extraction=False,
            )

            target = self._project_ready() / "meetings" / "启动会.md"
            self.assertEqual(manifest["source_id"], "project-bfi-7")
            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["project_r_workspace_id"], 7)
            self.assertEqual(frontmatter["project_r_workspace_brand"], "BFI")
            self.assertEqual(frontmatter["project_r_source_file"], "03-会议纪要/启动会.md")
            self.assertEqual(frontmatter["content_kind"], "project_text_source")
            self.assertIn("项目决定使用黑色窗框", body)
            self.assertFalse((root / "derived" / "meetings" / "启动会.md").exists())
            saved_manifest = json.loads((self._project_manifests() / PROJECT_INGEST_MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["items"][0]["target_file"], "meetings/启动会.md")

    def test_project_ingest_can_be_scoped_to_current_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            meeting_dir = root / "03-会议纪要"
            quote_dir = root / "01-合同与报价"
            meeting_dir.mkdir(parents=True)
            quote_dir.mkdir(parents=True)
            (meeting_dir / "启动会.md").write_text("# 启动会\n\n会议内容。\n", encoding="utf-8")
            (quote_dir / "报价说明.md").write_text("# 报价说明\n\n报价内容。\n", encoding="utf-8")

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                source_path="03-会议纪要",
                recursive=True,
                enable_pdf_structured_extraction=False,
            )

            self.assertEqual(manifest["ingest_path"], "03-会议纪要")
            self.assertTrue(manifest["ingest_recursive"])
            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertEqual(manifest["items"][0]["source_file"], "03-会议纪要/启动会.md")
            self.assertTrue((self._project_ready() / "meetings" / "启动会.md").exists())
            self.assertFalse((self._project_ready() / "documents" / "报价说明.md").exists())

    def test_project_complex_pdf_is_pending_capability_until_structured_extraction_is_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            pdf = root / "02-图纸与技术资料" / "Drawing.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\nnot a real pdf")
            sidecar = pdf.with_suffix("")
            sidecar.mkdir()
            (sidecar / "p001.png").write_bytes(b"not a real png")

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                enable_pdf_structured_extraction=False,
            )

            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertEqual(manifest["summary"]["pending_extractor_capability"], 1)
            self.assertEqual(manifest["items"][0]["source_file"], "02-图纸与技术资料/Drawing.pdf")
            self.assertEqual(manifest["items"][0]["status"], "pending_extractor_capability")
            self.assertEqual(manifest["items"][0]["file_kind"], "pdf")
            self.assertEqual(manifest["items"][0]["extraction_complexity"], "vision_required")
            self.assertEqual(manifest["items"][0]["extractor_profile"], "mimo_vision")
            self.assertIn("structured extraction", manifest["items"][0]["error"])

    def test_project_audio_with_transcript_sidecar_goes_directly_to_project_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            media = root / "03-会议纪要" / "site-meeting.mp4"
            transcript = root / "03-会议纪要" / "site-meeting.transcript.txt"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"not a real video file")
            transcript.write_text(
                "[00:00] PM: 决定现场安装顺序按 A 区先行。\n"
                "[00:30] Site: 行动项：Site team 明天确认脚手架。\n"
                "[01:00] PM: 风险是材料到货时间不确定。\n",
                encoding="utf-8",
            )

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                enable_media_transcription=False,
                enable_email_extraction=False,
                enable_image_extraction=False,
            )

            target = self._project_ready() / "meetings" / "site-meeting.md"
            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["project_r_workspace_id"], 7)
            self.assertEqual(frontmatter["content_kind"], "meeting_structured_extract")
            self.assertEqual(frontmatter["review_status"], "approved")
            self.assertEqual(frontmatter["source_scope_review_policy"], "project_no_admin_review")
            self.assertEqual(frontmatter["project_r_transcript_file"], "03-会议纪要/site-meeting.transcript.txt")
            self.assertIn("Site team 明天确认脚手架", body)
            self.assertEqual(manifest["items"][0]["target_file"], "meetings/site-meeting.md")
            self.assertEqual(manifest["items"][0]["review_status"], "approved")

    def test_project_pdf_structured_extraction_goes_directly_to_project_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            pdf = root / "02-图纸与技术资料" / "Drawing.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\nnot a real pdf")

            def fake_pdf_extractor(path: Path) -> PDFStructuredExtractionResult:
                self.assertEqual(path, pdf)
                return PDFStructuredExtractionResult(
                    markdown=(
                        "# Drawing\n\n"
                        "## 核心结论 / Key Conclusions\n\n"
                        "- 中文：窗框颜色为黑色。\n"
                        "  English: The frame colour is black.\n\n"
                        "## 待审核问题 / Review Questions\n\n"
                        "- 中文：需复核图纸页码。\n"
                        "  English: Drawing page references require review.\n"
                    ),
                    page_count=1,
                    pages_analyzed=1,
                    model_profile="test-profile",
                    provider="test-provider",
                    model="test-model",
                )

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                pdf_extractor=fake_pdf_extractor,
                enable_pdf_structured_extraction=True,
            )

            target = self._project_ready() / "technical" / "Drawing.md"
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["content_kind"], "project_pdf_structured_extract")
            self.assertEqual(frontmatter["review_status"], "approved")
            self.assertEqual(frontmatter["source_scope_review_policy"], "project_no_admin_review")
            self.assertEqual(frontmatter["extractor_review_status"], "pending_review")
            self.assertEqual(frontmatter["language_policy"], "bilingual_zh_en_aligned")
            self.assertIn("The frame colour is black", body)
            self.assertEqual(manifest["items"][0]["target_file"], "technical/Drawing.md")
            self.assertEqual(manifest["items"][0]["review_status"], "approved")

    def test_project_simple_pdf_text_route_compiles_to_project_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            pdf = root / "02-图纸与技术资料" / "Spec.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\nfake simple pdf")

            original_classifier = project_ingest.classify_source_file
            original_compile_pdf = project_ingest._compile_project_pdf_text_source

            def fake_classifier(path: Path, *, source_scope: str = "project") -> ExtractorClassification:
                if path == pdf:
                    return ExtractorClassification(
                        source_scope,
                        "pdf",
                        "simple_text",
                        "deepseek_text",
                        "test selectable PDF route",
                    )
                return original_classifier(path, source_scope=source_scope)

            def fake_compile_pdf(source_path, target_path, workspace, paths, ingested_at, source_hash, classification):
                frontmatter = {
                    **project_ingest._project_frontmatter(workspace, source_path, paths, ingested_at, source_hash),
                    **classification.to_manifest_metadata(),
                    "title": source_path.stem,
                    "content_kind": "project_pdf_text_extracted",
                    "extraction_status": "pdf_text_extracted",
                    "review_status": "approved",
                }
                project_ingest._write_markdown(target_path, frontmatter, "# Spec\n\nExtracted selectable PDF text.\n")

            project_ingest.classify_source_file = fake_classifier
            project_ingest._compile_project_pdf_text_source = fake_compile_pdf
            try:
                manifest = compile_project_workspace_sources(self._workspace(root), self._settings())
            finally:
                project_ingest.classify_source_file = original_classifier
                project_ingest._compile_project_pdf_text_source = original_compile_pdf

            target = self._project_ready() / "technical" / "Spec.md"
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            self.assertEqual(manifest["items"][0]["file_kind"], "pdf")
            self.assertEqual(manifest["items"][0]["extraction_complexity"], "simple_text")
            self.assertEqual(manifest["items"][0]["extractor_profile"], "deepseek_text")
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["content_kind"], "project_pdf_text_extracted")
            self.assertIn("Extracted selectable PDF text", body)

    def test_project_image_audio_and_email_are_visible_pending_states(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            site = root / "06-现场与客诉" / "site.png"
            media = root / "03-会议纪要" / "meeting.mp3"
            email = root / "99-未归档文件" / "client.eml"
            site.parent.mkdir(parents=True)
            media.parent.mkdir(parents=True)
            email.parent.mkdir(parents=True)
            site.write_bytes(b"fake png")
            media.write_bytes(b"fake mp3")
            email.write_text("From: a@example.com\nSubject: Test\n\nBody", encoding="utf-8")

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                enable_media_transcription=False,
                enable_email_extraction=False,
                enable_image_extraction=False,
            )

            self.assertEqual(manifest["summary"]["total"], 3)
            self.assertEqual(manifest["summary"]["pending_extractor_capability"], 2)
            self.assertEqual(manifest["summary"]["pending_transcription"], 1)
            items = {item["source_file"]: item for item in manifest["items"]}
            self.assertEqual(items["06-现场与客诉/site.png"]["status"], "pending_extractor_capability")
            self.assertEqual(items["06-现场与客诉/site.png"]["file_kind"], "image")
            self.assertEqual(items["03-会议纪要/meeting.mp3"]["status"], "pending_transcription")
            self.assertEqual(items["03-会议纪要/meeting.mp3"]["transcription_status"], "pending_transcription")
            self.assertEqual(items["99-未归档文件/client.eml"]["status"], "pending_extractor_capability")
            self.assertEqual(items["99-未归档文件/client.eml"]["file_kind"], "email")

    def test_project_image_can_compile_to_project_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            image = root / "99-未归档文件" / "审批流程规则.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"fake png")

            def fake_image_extractor(path: Path) -> ImageStructuredExtractionResult:
                self.assertEqual(path, image)
                return ImageStructuredExtractionResult(
                    markdown="# 审批流程规则\n\n- 中文：截图显示审批流程需要经理确认。\n  English: The screenshot shows the approval process requires manager confirmation.",
                    model_profile="mimo-test",
                    provider="mimo",
                    model="mimo-v2.5",
                    token_usage={"input_tokens": 11, "output_tokens": 22},
                )

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                image_extractor=fake_image_extractor,
                enable_image_extraction=True,
            )

            target = self._project_ready() / "unfiled" / "审批流程规则.md"
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            item = manifest["items"][0]
            self.assertEqual(item["file_kind"], "image")
            self.assertEqual(item["status"], "compiled")
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["content_kind"], "image_structured_extract")
            self.assertIn("manager confirmation", body)

    def test_project_media_without_transcript_can_auto_transcribe_and_compile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            media = root / "03-会议纪要" / "site-meeting.mp4"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"fake mp4")

            def fake_transcriber(path: Path) -> MediaTranscriptionResult:
                self.assertEqual(path, media)
                return MediaTranscriptionResult(
                    transcript_text="[00:00] PM: 决定 A 区先安装。\n[00:10] Site: 需要明天确认脚手架。",
                    model_profile="mimo-test",
                    provider="mimo",
                    model="mimo-v2.5",
                    token_usage={"input_tokens": 10, "output_tokens": 20},
                )

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                media_transcriber=fake_transcriber,
                enable_media_transcription=True,
            )

            target = self._project_ready() / "meetings" / "site-meeting.md"
            transcript = root / "03-会议纪要" / "site-meeting.auto.transcript.md"
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            self.assertTrue(transcript.exists())
            item = manifest["items"][0]
            self.assertEqual(item["status"], "compiled")
            self.assertEqual(item["transcription_status"], "auto_transcribed")
            self.assertEqual(item["generated_transcript_file"], "03-会议纪要/site-meeting.auto.transcript.md")
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["transcription_status"], "auto_transcribed")
            self.assertEqual(frontmatter["project_r_transcript_file"], "03-会议纪要/site-meeting.auto.transcript.md")
            self.assertIn("A 区先安装", body)

    def test_project_eml_compiles_to_project_email_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            email = root / "99-未归档文件" / "client.eml"
            email.parent.mkdir(parents=True)
            email.write_text("From: client@example.com\nTo: pm@example.com\nSubject: Apt 5 Window\n\nPlease confirm window type 5.", encoding="utf-8")

            def fake_email_extractor(path: Path) -> EmailStructuredExtractionResult:
                self.assertEqual(path, email)
                return EmailStructuredExtractionResult(
                    markdown="# Apt 5 Window\n\n- 中文：客户要求确认 5 型窗。\n  English: The client asks to confirm type 5 window.",
                    subject="Apt 5 Window",
                    sender="client@example.com",
                    recipients=("pm@example.com",),
                    message_date="",
                )

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                email_extractor=fake_email_extractor,
                enable_email_extraction=True,
            )

            target = self._project_ready() / "unfiled" / "client.md"
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertTrue(target.exists())
            item = manifest["items"][0]
            self.assertEqual(item["file_kind"], "email")
            self.assertEqual(item["status"], "compiled")
            self.assertEqual(item["email_subject"], "Apt 5 Window")
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["content_kind"], "email_thread_structured_extract")
            self.assertEqual(frontmatter["review_status"], "approved")
            self.assertIn("type 5 window", body)

    def test_project_eml_attachment_is_extracted_and_recursively_compiled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            email = root / "99-未归档文件" / "client.eml"
            email.parent.mkdir(parents=True)

            message = EmailMessage()
            message["From"] = "client@example.com"
            message["To"] = "pm@example.com"
            message["Subject"] = "Attachment Thread"
            message.set_content("Please review attached site instruction.")
            message.add_attachment(
                "# Site Instruction\n\n- 中文：附件要求现场先完成检查。\n  English: The attachment requires site inspection first.\n",
                subtype="markdown",
                filename="site-instruction.md",
            )
            email.write_bytes(message.as_bytes())

            def fake_email_extractor(path: Path) -> EmailStructuredExtractionResult:
                self.assertEqual(path, email)
                return EmailStructuredExtractionResult(
                    markdown="# Attachment Thread\n\n- 中文：邮件要求查看附件。\n  English: The email asks to review the attachment.",
                    subject="Attachment Thread",
                    sender="client@example.com",
                    recipients=("pm@example.com",),
                    attachment_names=("site-instruction.md",),
                )

            manifest = compile_project_workspace_sources(
                self._workspace(root),
                self._settings(),
                email_extractor=fake_email_extractor,
                enable_email_extraction=True,
                enable_image_extraction=False,
                enable_email_attachment_recursion=True,
            )

            items = {item["source_file"]: item for item in manifest["items"]}
            attachment_source = "99-未归档文件/client.attachments/site-instruction.md"
            self.assertEqual(manifest["summary"]["compiled"], 2)
            self.assertIn("99-未归档文件/client.eml", items)
            self.assertIn(attachment_source, items)
            self.assertEqual(items[attachment_source]["status"], "compiled")
            self.assertEqual(
                items["99-未归档文件/client.eml"]["email_extracted_attachment_files"],
                [attachment_source],
            )
            target = self._project_ready() / "unfiled" / "client.attachments" / "site-instruction.md"
            self.assertTrue(target.exists())
            _, body = self._read_frontmatter(target)
            self.assertIn("site inspection first", body)

    def _read_frontmatter(self, path: Path):
        text = path.read_text(encoding="utf-8")
        _, raw_frontmatter, body = text.split("---", 2)
        return yaml.safe_load(raw_frontmatter), body


if __name__ == "__main__":
    unittest.main()
