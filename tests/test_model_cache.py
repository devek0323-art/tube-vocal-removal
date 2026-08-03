import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import config
from app.pipeline import ALL_MODEL_MODES, MODEL_REQUIRED_FILES, Pipeline


class ModelCacheTests(unittest.TestCase):
    def test_existing_complete_model_skips_worker(self):
        events = []
        pipeline = Pipeline(events.append)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(config, "MODELS_DIR", Path(tmp)):
            for filename in MODEL_REQUIRED_FILES["karaoke"]:
                path = Path(tmp) / filename
                path.write_bytes(b"model")
            with mock.patch("app.pipeline.threading.Thread") as thread:
                self.assertTrue(pipeline.download_model("karaoke", dict(config.DEFAULTS)))
                thread.assert_not_called()

        self.assertTrue(events[-1]["already_installed"])
        self.assertFalse(events[-1]["running"])

    def test_zero_length_or_missing_file_is_not_installed(self):
        pipeline = Pipeline(lambda _event: None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(config, "MODELS_DIR", Path(tmp)):
            first = MODEL_REQUIRED_FILES["best"][0]
            (Path(tmp) / first).write_bytes(b"")
            self.assertFalse(pipeline._model_group_installed("best"))

    def test_all_status_reports_every_group(self):
        pipeline = Pipeline(lambda _event: None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(config, "MODELS_DIR", Path(tmp)):
            for mode in ALL_MODEL_MODES:
                for filename in MODEL_REQUIRED_FILES[mode]:
                    (Path(tmp) / filename).write_bytes(b"model")
            status = pipeline.model_download_status()

        self.assertTrue(status["all_installed"])
        self.assertTrue(all(status["installed"][mode] for mode in ALL_MODEL_MODES))


if __name__ == "__main__":
    unittest.main()
