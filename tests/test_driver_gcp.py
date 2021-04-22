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
