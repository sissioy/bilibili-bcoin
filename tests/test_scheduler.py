import unittest

from signin.core.config import Config
from signin.scheduler.scheduler import Scheduler


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        Config._instance = None

    def tearDown(self):
        Config._instance = None

    def test_default_cron_is_valid(self):
        scheduler = Scheduler(Config())

        trigger = scheduler.parse_cron(scheduler.config.app.scheduled.cron)

        self.assertIsNotNone(trigger)


if __name__ == "__main__":
    unittest.main()
