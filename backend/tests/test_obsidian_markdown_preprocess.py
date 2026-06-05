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
        self.assertNotIn("cssclasses", body)
        self.assertNotIn("![[avatar.png]]", body)
        self.assertNotIn("![logo]", body)
        self.assertNotIn("[[03_Companies/Binah", body)
        self.assertIn("Binah", body)
        self.assertIn("VELA -> `02_Projects/VELA`", body)
        self.assertEqual(metadata["removed_embed_count"], 2)

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
