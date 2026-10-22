import unittest
from unittest.mock import patch

from signin.core.config import ServerConfig
from signin.core.message import ServerChanSender


class ServerChanSenderTest(unittest.TestCase):
    @patch("signin.core.message.httpx.Client")
    def test_missing_key_does_not_send_request(self, client):
        sender = ServerChanSender(ServerConfig())

        result = sender.send("title", "message")

        self.assertFalse(result)
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
