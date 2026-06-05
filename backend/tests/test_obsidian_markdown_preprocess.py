import json
import tempfile
import unittest
from pathlib import Path

import yaml

from core.obsidian_markdown_preprocess import clean_obsidian_markdown, preprocess_obsidian_markdown_tree


class ObsidianMarkdownPreprocessTests(unittest.TestCase):
    def test_clean_obsidian_markdown_removes_noise_and_preserves_links(self):
        source = Path("raw/01_Clients/Aaron Morris.md")
        text = (
            "---\n"
            "cssclasses: hide-properties\n"
            "type: person\n"
            "name: Aaron Morris\n"
            "company: '[[03_Companies/Binah]]'\n"
            "tags:\n"
            "  - project_manager\n"
            "notes: Long CRM note belongs in body\n"
            "age: 45\n"
            "operations_model: Should move for person files\n"
            "---\n"
            "# Aaron Morris\n\n"
            "> <span style=\"color:orange\">external</span> | [[03_Companies/Binah|Binah]]\n\n"
            "![[avatar.png]]\n"
            "![logo](logo.png)\n"
            "---\n"
            "Works on [[02_Projects/VELA]].\n"
        )

        frontmatter, body, metadata = clean_obsidian_markdown(
            text,
            source_path=source,
            source_scope="customer",
            source_id="customer-crm",
            source_file="01_Clients/Aaron Morris.md",
            source_sha256="abc",
            run_id="test-run",
            created_at="2026-06-05T00:00:00+00:00",
        )

        self.assertEqual(frontmatter["preprocess_skill"], "markdown-source-preprocess")
        self.assertEqual(frontmatter["content_kind"], "customer_person_source_record")
        self.assertEqual(frontmatter["obsidian_embed_removed_count"], 2)
        self.assertNotIn("cssclasses", frontmatter)
        self.assertNotIn("notes", frontmatter)
        self.assertNotIn("age", frontmatter)
        self.assertNotIn("operations_model", frontmatter)
        self.assertIn("## Source Notes", body)
        self.assertIn("Long CRM note belongs in body", body)
        source_notes = body.split("## Source Notes", 1)[1].split("## Preprocess Notes", 1)[0]
        self.assertNotIn("cssclasses", source_notes)
        self.assertNotIn("45", body)
        self.assertNotIn("![[avatar.png]]", body)
        self.assertNotIn("![logo]", body)
        self.assertNotIn("[[03_Companies/Binah", body)
        self.assertIn("## Extracted Facts", body)
        self.assertIn("## Entities Mentioned", body)
        self.assertIn("## Events / Timeline Signals", body)
        self.assertIn("## Original Evidence", body)
        self.assertIn("Binah", body)
        self.assertIn("VELA -> `02_Projects/VELA`", body)
        self.assertEqual(metadata["removed_embed_count"], 2)
        self.assertIn("notes", metadata["moved_frontmatter_keys"])
        self.assertIn("age", metadata["removed_frontmatter_keys"])

    def test_frontmatter_policy_preserves_and_canonicalizes_by_file_kind(self):
        source = Path("raw/03_Companies/Binah.md")
        text = (
            "---\n"
            "name: Binah\n"
            "type: company\n"
            "operations_model: Builder-led delivery\n"
            "pipeline_ecosystem: Consultant network\n"
            "competitors:\n"
            "  - Rival Facades\n"
            "decision: Move this to body\n"
            "key_decisions: Also move this to body\n"
            "---\n"
            "# Binah\n\n"
            "Company profile.\n"
        )

        frontmatter, body, metadata = clean_obsidian_markdown(
            text,
            source_path=source,
            source_scope="customer",
            source_id="customer-crm",
            source_file="03_Companies/Binah.md",
            source_sha256="abc",
            run_id="test-run",
            created_at="2026-06-05T00:00:00+00:00",
        )

        self.assertEqual(frontmatter["operation_model"], "Builder-led delivery")
        self.assertEqual(frontmatter["pipeline_ecology"], "Consultant network")
        self.assertEqual(frontmatter["competitors"], ["Rival Facades"])
        self.assertNotIn("operations_model", frontmatter)
        self.assertNotIn("pipeline_ecosystem", frontmatter)
        self.assertNotIn("decision", frontmatter)
        self.assertNotIn("key_decisions", frontmatter)
        self.assertIn("Move this to body", body)
        self.assertIn("Also move this to body", body)
        self.assertIn("decision", metadata["moved_frontmatter_keys"])
        self.assertIn("key_decisions", metadata["moved_frontmatter_keys"])

    def test_preprocess_tree_writes_company_gbrain_ready_manifest_without_modifying_raw(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw = root / "raw"
            preprocessed = root / "_preprocessed" / "company" / "company-wiki"
            raw.mkdir(parents=True)
            source = raw / "书面化原则.md"
            original = "# 书面化原则\n\n重要事项要[[留痕|书面留痕]]。\n"
            source.write_text(original, encoding="utf-8")

            manifest = preprocess_obsidian_markdown_tree(
                raw_path=raw,
                preprocessed_root=preprocessed,
                source_scope="company",
                source_id="company-wiki",
                run_id="unit-test",
            )

            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            target_file = manifest["items"][0]["target_file"]
            target = preprocessed / "gbrain-ready" / target_file
            self.assertTrue(target.exists())
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["source_scope"], "company")
            self.assertEqual(frontmatter["source_file"], "书面化原则.md")
            self.assertIn("书面留痕", body)
            latest = preprocessed / "manifests" / "latest-obsidian-markdown-preprocess.json"
            self.assertEqual(json.loads(latest.read_text(encoding="utf-8"))["summary"]["compiled"], 1)

    def test_dry_run_does_not_write_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw = root / "raw"
            preprocessed = root / "_preprocessed" / "company" / "company-wiki"
            raw.mkdir(parents=True)
            (raw / "rule.md").write_text("# Rule\n\nCreated on 2026-06-05.\n", encoding="utf-8")

            manifest = preprocess_obsidian_markdown_tree(
                raw_path=raw,
                preprocessed_root=preprocessed,
                source_scope="company",
                source_id="company-wiki",
                run_id="dry-run",
                dry_run=True,
            )

            self.assertTrue(manifest["dry_run"])
            self.assertEqual(manifest["summary"]["compiled"], 1)
            self.assertFalse((preprocessed / "gbrain-ready").exists())
            self.assertFalse((preprocessed / "manifests").exists())

    def test_preprocess_tree_routes_customer_crm_categories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw = root / "CRM" / "raw"
            preprocessed = root / "_preprocessed" / "customer" / "crm"
            company_dir = raw / "03_Companies"
            company_dir.mkdir(parents=True)
            (company_dir / "5Points.md").write_text(
                "---\nname: 5Points\ntype: company\n---\n# 5Points\n\nBarry from [[01_Clients/Barry Bourhill]].\n",
                encoding="utf-8",
            )

            manifest = preprocess_obsidian_markdown_tree(
                raw_path=raw,
                preprocessed_root=preprocessed,
                source_scope="customer",
                source_id="customer-crm",
                run_id="unit-test",
            )

            item = manifest["items"][0]
            self.assertEqual(item["status"], "compiled")
            self.assertTrue(item["target_file"].startswith("companies/"))
            target = preprocessed / "gbrain-ready" / item["target_file"]
            frontmatter, body = self._read_frontmatter(target)
            self.assertEqual(frontmatter["content_kind"], "customer_company_source_record")
            self.assertIn("Barry Bourhill", body)

    def _read_frontmatter(self, path: Path):
        text = path.read_text(encoding="utf-8")
        _, raw_frontmatter, body = text.split("---", 2)
        return yaml.safe_load(raw_frontmatter), body


if __name__ == "__main__":
    unittest.main()
