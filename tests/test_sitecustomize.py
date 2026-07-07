import importlib.util
import subprocess
import unittest
from unittest.mock import patch


class SiteCustomizeTests(unittest.TestCase):
    def test_install_is_triggered_when_dependencies_are_missing(self):
        spec = importlib.util.find_spec("sitecustomize")
        self.assertIsNotNone(spec)

        with patch("sitecustomize.subprocess.check_call") as check_call, patch("sitecustomize.importlib.util.find_spec", side_effect=lambda name: None):
            import sitecustomize
            sitecustomize.ensure_dependencies()

        check_call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
