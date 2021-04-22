from mock import patch, Mock
from unittest import TestCase
from swift.common.swob import Request
from swift_cloud.drivers.gcp import SwiftGCPDriver


class FakeApp:
    def __call__(self, environ, start_response):
        return Response(body="Fake App")(environ, start_response)


class SwiftGCPDriverTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conf = {
            'gcp_credentials': '/path/to/credentials.json',
            'max_results': 999
        }
        cls.account_info = {
            'meta': {'cloud': 'gcp'}
        }
        cls.app = FakeApp()
        patch('swift_cloud.drivers.gcp.storage', Mock()).start()
        patch('swift_cloud.drivers.gcp.Credentials', Mock()).start()

    def _driver(self, path, method='GET'):
        environ = {
            'PATH_INFO': path,
            'REQUEST_METHOD': method,
            'swift.authorize': lambda req: False
        }
        return SwiftGCPDriver(Request(environ),
            self.account_info, self.app, self.conf)

    def test_invalid_request_path(self):
        res = self._driver('/invalid-path').response()
        self.assertEquals(res.body, 'Invalid request path')

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.handle_account')
    def test_call_account_handler(self, mock_handle_account):
        res = self._driver('/v1/account').response()
        mock_handle_account.assert_called_once()

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.handle_container')
    def test_call_container_handler(self, mock_handle_container):
        driver = self._driver('/v1/account/container').response()
        mock_handle_container.assert_called_once()

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.handle_object')
    def test_call_object_handler(self, mock_handle_object):
        driver = self._driver('/v1/account/container/object').response()
        mock_handle_object.assert_called_once()

    # Account tests

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.head_account')
    def test_call_head_account(self, mock_head_account):
        res = self._driver('/v1/account', 'HEAD').response()
        mock_head_account.assert_called_once()

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.get_account')
    def test_call_get_account(self, mock_get_account):
        res = self._driver('/v1/account', 'GET').response()
        mock_get_account.assert_called_once()

    def test_post_account_foward_request_to_next_app(self):
        res = self._driver('/v1/account', 'POST').response()
        self.assertIsInstance(res, FakeApp)

    def test_head_account_returns_a_204_status_code(self):
        res = self._driver('/v1/account', 'HEAD').response()
        self.assertEquals(res.status_int, 204)

    def test_head_account_returns_x_account_headers(self):
        res = self._driver('/v1/account', 'HEAD').response()
        self.assertIn('X-Account-Container-Count', res.headers)
        self.assertIn('X-Account-Object-Count', res.headers)
        self.assertIn('X-Account-Bytes-Used', res.headers)
        self.assertIn('X-Account-Meta-Cloud', res.headers)

    def test_get_account_returns_account_headers_and_container_list_as_json(self):
        res = self._driver('/v1/account', 'GET').response()
        self.assertIn('X-Account-Container-Count', res.headers)
        self.assertIn('X-Account-Object-Count', res.headers)
        self.assertIn('X-Account-Bytes-Used', res.headers)
        self.assertIn('X-Account-Meta-Cloud', res.headers)
        self.assertEquals(res.content_type, 'application/json')
        self.assertEquals(res.body, '[]')

    # Container tests

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.head_container')
    def test_call_head_container(self, mock_head_container):
        res = self._driver('/v1/account/container', 'HEAD').response()
        mock_head_container.assert_called_once()

    # Object tests

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.head_object')
    def test_call_head_object(self, mock_head_object):
        res = self._driver('/v1/account/container/object', 'HEAD').response()
        mock_head_object.assert_called_once()
