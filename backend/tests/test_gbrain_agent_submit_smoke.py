import unittest

from scripts import gbrain_agent_submit_smoke as script


class GBrainAgentSubmitSmokeScriptTest(unittest.TestCase):
    def test_extract_job_id_from_top_level_id(self):
        self.assertEqual(script._extract_job_id({"id": 42}), 42)

    def test_extract_job_id_from_result(self):
        self.assertEqual(script._extract_job_id({"result": {"id": "43"}}), 43)

    def test_extract_job_id_missing(self):
        self.assertIsNone(script._extract_job_id({"status": "ok"}))


if __name__ == "__main__":
    unittest.main()
