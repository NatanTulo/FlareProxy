import unittest
import json
from unittest.mock import patch, MagicMock


def mock_flaresolverr_post(url, headers=None, json=None, timeout=None):
    cmd = json.get("cmd") if json else None
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    if cmd == "sessions.create":
        mock_resp.json.return_value = {"session": "test-session-id"}
    elif cmd == "request.get":
        mock_resp.json.return_value = {"solution": {"response": "<html>Mock response</html>"}}
    else:
        mock_resp.json.return_value = {}
    return mock_resp


class TestFlareProxy(unittest.TestCase):
    """Test suite for FlareProxy"""

    @patch('flareproxy.requests.post', side_effect=mock_flaresolverr_post)
    def test_do_GET_constructs_url_correctly(self, mock_post):
        """Test that GET requests construct URLs correctly"""
        from flareproxy import ProxyHTTPRequestHandler

        with patch.object(ProxyHTTPRequestHandler, '__init__', lambda self, *args, **kwargs: None):
            handler = ProxyHTTPRequestHandler(None, None, None)
            handler.path = "http://example.com/test"
            handler.command = "GET"
            handler.headers = {}

            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.wfile = MagicMock()

            handler.do_GET()

            # Find the call for request.get
            get_calls = [
                call for call in mock_post.call_args_list
                if call[1].get('json', {}).get('cmd') == 'request.get'
            ]
            self.assertEqual(len(get_calls), 1)
            self.assertEqual(get_calls[0][1]['json']['url'], 'https://example.com/test')

    @patch('flareproxy.generate_self_signed_cert')
    @patch('ssl.SSLContext')
    @patch('flareproxy.requests.post', side_effect=mock_flaresolverr_post)
    def test_do_CONNECT_supports_https(self, mock_post, mock_ssl_context, mock_gen_cert):
        """Test that CONNECT requests perform TLS handshake and handle inner GET request"""
        from flareproxy import ProxyHTTPRequestHandler

        with patch.object(ProxyHTTPRequestHandler, '__init__', lambda self, *args, **kwargs: None):
            handler = ProxyHTTPRequestHandler(None, None, None)
            handler.path = "mediamarkt.pl:443"
            handler.command = "CONNECT"

            # Mock connection socket
            mock_conn = MagicMock()
            handler.connection = mock_conn

            # Mock SSL socket returned after wrap_socket
            mock_ssl_sock = MagicMock()
            # Inner request line over TLS socket
            mock_ssl_sock.makefile.return_value.readline.return_value = b"GET /pl/category/123 HTTP/1.1\r\n"
            mock_ssl_context.return_value.wrap_socket.return_value = mock_ssl_sock

            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.wfile = MagicMock()

            # Mock parse_request to populate path and headers
            def mock_parse():
                handler.command = "GET"
                handler.path = "/pl/category/123"
                handler.headers = {"Host": "mediamarkt.pl"}
                return True

            handler.parse_request = mock_parse

            handler.do_CONNECT()

            # Verify CONNECT response was sent
            handler.send_response.assert_any_call(200, "Connection Established")

            # Find the call for request.get to FlareSolverr
            get_calls = [
                call for call in mock_post.call_args_list
                if call[1].get('json', {}).get('cmd') == 'request.get'
            ]
            self.assertEqual(len(get_calls), 1)
            self.assertEqual(get_calls[0][1]['json']['url'], 'https://mediamarkt.pl/pl/category/123')

    @patch('flareproxy.requests.post', side_effect=mock_flaresolverr_post)
    def test_handle_get_request_includes_timeout(self, mock_post):
        """Test that requests include maxTimeout parameter"""
        from flareproxy import ProxyHTTPRequestHandler

        with patch.object(ProxyHTTPRequestHandler, '__init__', lambda self, *args, **kwargs: None):
            handler = ProxyHTTPRequestHandler(None, None, None)

            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.wfile = MagicMock()

            handler.handle_get_request("https://example.com")

            get_calls = [
                call for call in mock_post.call_args_list
                if call[1].get('json', {}).get('cmd') == 'request.get'
            ]
            self.assertEqual(len(get_calls), 1)
            self.assertEqual(get_calls[0][1]['json']['maxTimeout'], 60000)

    @patch('flareproxy.requests.post')
    def test_error_handling(self, mock_post):
        """Test that errors are handled gracefully"""
        from flareproxy import ProxyHTTPRequestHandler

        mock_post.side_effect = Exception("Connection failed")

        with patch.object(ProxyHTTPRequestHandler, '__init__', lambda self, *args, **kwargs: None):
            handler = ProxyHTTPRequestHandler(None, None, None)

            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.wfile = MagicMock()

            handler.handle_get_request("https://example.com")

            handler.send_response.assert_called_with(500)
            handler.wfile.write.assert_called_once()

            written_data = handler.wfile.write.call_args[0][0]
            error_json = json.loads(written_data.decode('utf-8'))
            self.assertIn('error', error_json)
            self.assertIn('Connection failed', error_json['error'])

    def test_flaresolverr_url_env_default(self):
        """Test that FLARESOLVERR_URL defaults correctly"""
        import flareproxy

        self.assertEqual(flareproxy.FLARESOLVERR_URL, "http://flaresolverr:8191/v1")


if __name__ == '__main__':
    unittest.main()