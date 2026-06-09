import os
import tempfile
import unittest
from pathlib import Path

import core.gbrain._adapter as gbrain_adapter


class GBrainSettingsEnvTests(unittest.TestCase):
    def setUp(self):
        self._old_env = {
            key: os.environ.get(key)
            for key in ("GBRAIN_SERVICE_BEARER_TOKEN", "GBRAIN_BASE_URL", "GBRAIN_DOTENV_AUTOLOAD")
        }
        self._old_default_env_path = gbrain_adapter.DEFAULT_BACKEND_ENV_PATH
        self._old_loaded_paths = set(gbrain_adapter._DOTENV_LOADED_PATHS)
        for key in self._old_env:
            os.environ.pop(key, None)
        gbrain_adapter._DOTENV_LOADED_PATHS.clear()

    def tearDown(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        gbrain_adapter.DEFAULT_BACKEND_ENV_PATH = self._old_default_env_path
        gbrain_adapter._DOTENV_LOADED_PATHS.clear()
        gbrain_adapter._DOTENV_LOADED_PATHS.update(self._old_loaded_paths)

    def test_load_gbrain_settings_loads_backend_dotenv_for_direct_imports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "GBRAIN_SERVICE_BEARER_TOKEN=test-service-token\n"
                "GBRAIN_BASE_URL=http://127.0.0.1:3999\n",
                encoding="utf-8",
            )
            gbrain_adapter.DEFAULT_BACKEND_ENV_PATH = env_path

            settings = gbrain_adapter.load_gbrain_settings()

            self.assertEqual(settings.service_bearer_token, "test-service-token")
            self.assertEqual(settings.base_url, "http://127.0.0.1:3999")

    def test_dotenv_loader_does_not_override_existing_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "GBRAIN_SERVICE_BEARER_TOKEN=dotenv-token\n"
                "GBRAIN_BASE_URL=http://127.0.0.1:3999\n",
                encoding="utf-8",
            )
            gbrain_adapter.DEFAULT_BACKEND_ENV_PATH = env_path
            os.environ["GBRAIN_SERVICE_BEARER_TOKEN"] = "existing-token"

            settings = gbrain_adapter.load_gbrain_settings()

            self.assertEqual(settings.service_bearer_token, "existing-token")
            self.assertEqual(settings.base_url, "http://127.0.0.1:3999")

    def test_dotenv_loader_can_be_disabled_for_isolated_tests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "GBRAIN_SERVICE_BEARER_TOKEN=dotenv-token\n"
                "GBRAIN_BASE_URL=http://127.0.0.1:3999\n",
                encoding="utf-8",
            )
            gbrain_adapter.DEFAULT_BACKEND_ENV_PATH = env_path
            os.environ["GBRAIN_DOTENV_AUTOLOAD"] = "false"

            settings = gbrain_adapter.load_gbrain_settings()

            self.assertEqual(settings.service_bearer_token, "")
            self.assertEqual(settings.base_url, "http://127.0.0.1:3131")


if __name__ == "__main__":
    unittest.main()
