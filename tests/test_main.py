import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main


class MainTest(unittest.TestCase):
    @patch("main.setup_logger")
    @patch("main.load_config")
    @patch("main.Scheduler")
    def test_once_returns_nonzero_when_task_failed(self, scheduler_class, load_config, setup_logger):
        report = SimpleNamespace(
            total_tasks=1,
            success_count=0,
            failed_count=1,
            skipped_count=0,
            duration_seconds=0.1,
        )
        scheduler_class.return_value.run_once.return_value = report
        load_config.return_value = Mock()

        exit_code = main.main(["--once"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
