from mock import patch, Mock
from unittest import TestCase
from swift.common.swob import Response, Request
from swift_cloud.middleware import SwiftCloudMiddleware


class FakeApp:
    def __call__(self, environ, start_response):
        return Response(body="Fake App")(environ, start_response)


class FakeGCPDriver:
    def response(self):
        return Response(body='Fake GCP Driver')


class MiddlewareTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conf = {
            'cloud_providers': 'cloudone',
            'max_results': 999,
            'tools_api_url': 'http://swift-cloud-tools',
            'tools_api_token': 'token',
            'x_cloud_bypass': '123456'
        }
        cls.fake_app = FakeApp()
        cls.app = SwiftCloudMiddleware(cls.fake_app, cls.conf)

    def setUp(self):
        self.app.providers = ['cloudone']
        self.environ = {
            'PATH_INFO': '/v1/account/container/object',
            'REQUEST_METHOD': 'GET',
            'swift.authorize': lambda req: False
        }
        self.mock_get_account_info = patch(
            'swift_cloud.middleware.get_account_info', Mock()).start()
        self.mock_get_account_info.return_value = {'meta': {}}

    def tearDown(self):
        patch.stopall()

    def test_invalid_path_foward_the_request(self):
        self.environ['PATH_INFO'] = '/invalid-path'
        res = Request(self.environ).get_response(self.app)
        self.assertEquals(res.body, "Fake App")

    def test_if_swift_authorize_not_in_environ_skips_swift_cloud(self):
        del self.environ['swift.authorize']
        res = Request(self.environ).get_response(self.app)
        self.assertEquals(res.body, "Fake App")

    def test_get_account_info_call_with_environ_and_next_app(self):
        res = Request(self.environ).get_response(self.app)
        self.mock_get_account_info.assert_called_once_with(
            self.environ, self.fake_app)

    def test_foward_request_if_account_meta_cloud_not_present(self):
        res = Request(self.environ).get_response(self.app)
        self.assertEquals(res.body, "Fake App")

    def test_foward_request_if_cloud_name_not_in_providers_conf(self):
        self.mock_get_account_info.return_value = {
            'meta': {'cloud': 'mycloud'}}
        res = Request(self.environ).get_response(self.app)
        self.assertEquals(res.body, "Fake App")

    @patch('swift_cloud.middleware.SwiftGCPDriver')
    def test_if_authorized_return_handler_with_default_gcp_driver(self, mock_driver):
        mock_driver.return_value = FakeGCPDriver()
        self.app.providers = ['gcp']
        self.mock_get_account_info.return_value = {
            'meta': {'cloud': 'gcp'}}
        res = Request(self.environ).get_response(self.app)
        self.assertEquals(res.body, "Fake GCP Driver")
