import unittest
from unittest.mock import patch

from signin.core.config import BilibiliAccount, BrowserAuthConfig, BilibiliConfig, Config
from signin.scheduler.executor import TaskExecutor
from signin.scripts.base import BaseTask, CompositeTask, TaskStatus


class ResultTask(BaseTask):
    task_name = "result"

    def __init__(self, result):
        super().__init__("account")
        self._execution_result = result

    def check_authentication(self):
        return True

    def execute(self):
        return self._execution_result


class TaskExecutorTest(unittest.TestCase):
    def setUp(self):
        Config._instance = None

    def tearDown(self):
        Config._instance = None

    def test_load_tasks_uses_account_profile_dirs(self):
        config = Config()
        config.browserAuth = BrowserAuthConfig(
            enabled=True,
            profileDir="config/global-profile",
            authUrl="https://www.bilibili.com",
            authWaitSeconds=120,
        )
        config.bilibili = BilibiliConfig(
            enabled=True,
            accounts=[
                BilibiliAccount(name="account1", profileDir="config/bilibili-profile-1"),
                BilibiliAccount(name="account2", profileDir="config/bilibili-profile-2"),
            ],
        )

        executor = TaskExecutor(config)
        with patch("signin.scheduler.executor.BilibiliTask") as task_class:
            executor.load_tasks()

        first_auth = task_class.call_args_list[0].args[2]
        second_auth = task_class.call_args_list[1].args[2]
        self.assertEqual(first_auth.profileDir, "config/bilibili-profile-1")
        self.assertEqual(second_auth.profileDir, "config/bilibili-profile-2")
        self.assertEqual(first_auth.authUrl, "https://www.bilibili.com")
        self.assertIsNot(first_auth, config.browserAuth)
        self.assertIsNot(second_auth, config.browserAuth)

    def test_empty_run_is_finalized_and_saved(self):
        executor = TaskExecutor(Config())

        report = executor.run_all()

        self.assertIs(report, executor.report)
        self.assertIsNotNone(report.end_time)

    def test_result_statuses_are_counted_separately(self):
        executor = TaskExecutor(Config())
        tasks = [
            ResultTask({"success": True}),
            ResultTask({"success": False}),
            ResultTask({"success": False, "skipped": True}),
        ]

        with patch.object(executor, "load_tasks", side_effect=lambda: executor._tasks.extend(tasks)):
            report = executor.run_all()

        self.assertEqual(report.success_count, 1)
        self.assertEqual(report.failed_count, 1)
        self.assertEqual(report.skipped_count, 1)
        self.assertEqual(tasks[1].status, TaskStatus.FAILED)
        self.assertEqual(tasks[2].status, TaskStatus.SKIPPED)

    def test_composite_propagates_child_failure(self):
        task = CompositeTask("account", [
            ResultTask({"success": True}),
            ResultTask({"success": False}),
        ])

        result = task.run()

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.data["failed"], 1)


if __name__ == "__main__":
    unittest.main()
