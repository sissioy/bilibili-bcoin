import unittest
from unittest.mock import Mock, patch

import httpx

from signin.core.exceptions import NetworkError
from signin.core.http import SyncHttpClient


class SyncHttpClientTest(unittest.TestCase):
    def setUp(self):
        SyncHttpClient._instance = None
        SyncHttpClient._client = None
        self.http = SyncHttpClient()
        self.client = Mock()
        self.http._client = self.client

    def tearDown(self):
        SyncHttpClient._instance = None
        SyncHttpClient._client = None

    @patch("signin.core.http.time.sleep")
    def test_get_retries_network_errors(self, sleep):
        response = httpx.Response(200, request=httpx.Request("GET", "https://example.com"))
        self.client.get.side_effect = [httpx.ConnectError("offline"), response]

        result = self.http.get("https://example.com")

        self.assertIs(result, response)
        self.assertEqual(self.client.get.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("signin.core.http.time.sleep")
    def test_get_retries_transient_status(self, sleep):
        for status_code in (408, 429, 503):
            with self.subTest(status_code=status_code):
                unavailable = httpx.Response(
                    status_code,
                    request=httpx.Request("GET", "https://example.com"),
                )
                success = httpx.Response(
                    200,
                    request=httpx.Request("GET", "https://example.com"),
                )
                self.client.get.reset_mock()
                sleep.reset_mock()
                self.client.get.side_effect = [unavailable, success]

                result = self.http.get("https://example.com")

                self.assertIs(result, success)
                self.assertEqual(self.client.get.call_count, 2)
                sleep.assert_called_once_with(1)

    @patch("signin.core.http.time.sleep")
    def test_get_does_not_retry_normal_client_error(self, sleep):
        response = httpx.Response(400, request=httpx.Request("GET", "https://example.com"))
        self.client.get.return_value = response

        result = self.http.get("https://example.com")

        self.assertIs(result, response)
        self.client.get.assert_called_once()
        sleep.assert_not_called()

    @patch("signin.core.http.time.sleep")
    def test_get_raises_after_three_transient_failures(self, sleep):
        self.client.get.side_effect = httpx.ConnectError("offline")

        with self.assertRaises(NetworkError):
            self.http.get("https://example.com")

        self.assertEqual(self.client.get.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])


if __name__ == "__main__":
    unittest.main()
