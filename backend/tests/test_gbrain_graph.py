import tempfile
import unittest
from pathlib import Path

from core.gbrain_graph import build_entity_merge_candidates, build_source_graph


class GBrainGraphTests(unittest.TestCase):
    def test_build_source_graph_reads_source_metadata_body_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "companies").mkdir()
            (root / "clients").mkdir()
            (root / "projects").mkdir()

            (root / "companies" / "acme.md").write_text(
                "---\n"
                "title: Acme\n"
                "content_kind: customer_company_source_record\n"
                "source_file: 03_Companies/Acme.md\n"
                "---\n\n"
                "# Acme\n\n"
                "## Source Metadata\n\n"
                "- **linked_people:** Bob Buyer\n"
                "- **linked_projects:** Tower One\n"
                "- **source_events:** 260101 Acme kickoff.txt\n\n"
                "## Cleaned Content\n",
                encoding="utf-8",
            )
            (root / "clients" / "bob.md").write_text(
                "---\n"
                "title: Bob Buyer\n"
                "content_kind: customer_person_source_record\n"
                "source_file: 01_Clients/Bob Buyer.md\n"
                "---\n\n"
                "# Bob Buyer\n",
                encoding="utf-8",
            )
            (root / "projects" / "tower.md").write_text(
                "---\n"
                "title: Tower One\n"
                "content_kind: customer_project_source_record\n"
                "source_file: 02_Projects/Tower One.md\n"
                "---\n\n"
                "# Tower One\n",
                encoding="utf-8",
            )

            graph = build_source_graph("customer-crm", derived_path=root, focus="Acme")

        self.assertTrue(graph["ok"])
        node_titles = {node["title"] for node in graph["nodes"]}
        self.assertIn("Bob Buyer", node_titles)
        self.assertIn("Tower One", node_titles)
        self.assertEqual(len(graph["events"]), 1)
        self.assertEqual(graph["events"][0]["date"], "2026-01-01")

    def test_entity_merge_candidates_use_body_metadata_unresolved_refs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.mkdir(exist_ok=True)
            (root / "person.md").write_text(
                "---\n"
                "title: Alice Manager\n"
                "content_kind: customer_person_source_record\n"
                "---\n\n"
                "# Alice Manager\n\n"
                "## Source Metadata\n\n"
                "- **linked_companies:** Missing Co\n",
                encoding="utf-8",
            )

            result = build_entity_merge_candidates("customer-crm", derived_path=root, focus="Alice")

        self.assertTrue(result["ok"])
        self.assertIn("Missing Co", {candidate["title"] for candidate in result["candidates"]})


if __name__ == "__main__":
    unittest.main()
