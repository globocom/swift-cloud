from datetime import datetime, date
from mock import patch, Mock
from unittest import TestCase
from swift.common.swob import Response, Request
from swift_cloud.drivers.gcp import SwiftGCPDriver


class FakeApp:
    def __call__(self, environ, start_response):
        return Response(body="Fake App")(environ, start_response)


class FakeBlob:
    def __call__(self, path):
        return self

    def __init__(self, exists=True, header=True, folder=False):
        self._exists = exists
        self.name = None
        self.size = None
        self.md5_hash = None
        self.updated = datetime.now()
        self.content_type = None
        self.etag = None
        self.metadata = {}
        self.cache_control = None
        self.content_encoding = None
        self.content_disposition = None

        if header:
            self._set_headers(folder)

    def _set_headers(self, folder):
        self.name = 'blob'
        self.size = 100
        self.md5_hash = 'AJH45DGA8'
        self.updated = date(2021, 4, 4)
        self.content_type = 'text/html'
        self.etag = 'etag'
        self.metadata = {}
        self.cache_control = 10800
        self.content_encoding = 'gzip'
        self.content_disposition = 'inline'

        if folder:
            self.name += '/'

    def exists(self):
        return self._exists

    def patch(self):
        pass

    def download_as_bytes(self):
        pass

    def upload_from_string(self, obj_data, content_type):
        pass

    def delete(self):
        pass


class FakeBucket:
    def __init__(self, blob=FakeBlob(), blobs=[], labels={}, exists=True):
        self._exists = exists
        self.blob = blob
        self.blobs = blobs
        self.labels = labels

    def exists(self):
        return self._exists

    def get_blob(self, *args, **kwargs):
        return self.blob

    def list_blobs(self, *args, **kwargs):
        return self.blobs

    def patch(self):
        pass


class FakeClient:
    def __init__(self, bucket=FakeBucket(), error=None):
        self.bucket = bucket
        self.error = error

    def get_bucket(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.bucket


class FakeReader(object):
    def __init__(self):
        self.bytes = b'test'

    def read(self):
        try:
            x = self.bytes[0]
        except Exception:
            raise StopIteration
        self.bytes = self.bytes[1:]
        return x


class SwiftGCPDriverTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conf = {
            'gcp_credentials': '/path/to/credentials.json',
            'max_results': 999,
            'tools_api_url': 'http://swift-cloud-tools',
            'tools_api_token': 'token'
        }
        cls.account_info = {
            'meta': {'cloud': 'gcp'}
        }
        cls.app = FakeApp()

    def setUp(self):
        patch('swift_cloud.drivers.gcp.storage', Mock()).start()
        patch('swift_cloud.drivers.gcp.Credentials', Mock()).start()
        self.mock_client = patch(
            'swift_cloud.drivers.gcp.SwiftGCPDriver._get_client',
            Mock()).start()
        self.mock_client.return_value = FakeClient()

    def tearDown(self):
        patch.stopall()

    def _driver(self, path, method='GET', headers=None, params=None):
        environ = {
            'PATH_INFO': path,
            'REQUEST_METHOD': method,
            'swift.authorize': lambda req: False,
            'wsgi.input': FakeReader()
        }
        req = Request(environ)

        if headers:
            req.headers.update(headers)

        if params:
            req.params.update(params)

        return SwiftGCPDriver(req, self.account_info, self.app, self.conf)

    def test_invalid_request_path(self):
        res = self._driver('/invalid-path').response()
        self.assertEquals(res.body, '{"error": "Invalid request path"}')

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

    def test_head_account_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account', 'HEAD').response()
        self.assertEquals(res.status_int, 500)

    def test_get_account_returns_account_headers_and_container_list_as_json(self):
        res = self._driver('/v1/account', 'GET').response()
        self.assertIn('X-Account-Container-Count', res.headers)
        self.assertIn('X-Account-Object-Count', res.headers)
        self.assertIn('X-Account-Bytes-Used', res.headers)
        self.assertIn('X-Account-Meta-Cloud', res.headers)
        self.assertEquals(res.content_type, 'application/json')
        self.assertEquals(res.body, '[]')

    def test_get_account_with_marker_param(self):
        params = {"marker": "test"}
        res = self._driver('/v1/account', 'GET', params=params).response()
        self.assertEquals(res.status_int, 204)

    def test_get_account_with_containers(self):
        fake_blob = FakeBlob(exists=True, folder=True)
        fake_bucket = FakeBucket(blobs=[fake_blob])
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account', 'GET').response()
        self.assertEquals(res.status_int, 200)

    def test_get_account_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account', 'GET').response()
        self.assertEquals(res.status_int, 500)

    # Container tests

    def test_call_head_container(self):
        res = self._driver('/v1/account/container', 'HEAD').response()
        self.assertEquals(res.status_int, 204)

    def test_head_container_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account/container', 'HEAD').response()
        self.assertEquals(res.status_int, 500)

    def test_call_get_container(self):
        res = self._driver('/v1/account/container', 'GET').response()
        self.assertEquals(res.status_int, 204)

    def test_get_container_with_marker_param(self):
        params = {"marker": "test"}
        res = self._driver('/v1/account/container', 'GET', params=params).response()
        self.assertEquals(res.status_int, 204)

    def test_get_container_with_objects(self):
        fake_blob = FakeBlob(exists=True)
        fake_bucket = FakeBucket(blobs=[fake_blob])
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container', 'GET').response()
        self.assertEquals(res.status_int, 200)

    def test_get_container_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account/container', 'GET').response()
        self.assertEquals(res.status_int, 500)

    def test_call_put_container(self):
        res = self._driver('/v1/account/container', 'PUT').response()
        self.assertEquals(res.status_int, 201)

    def test_put_container_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account/container', 'PUT').response()
        self.assertEquals(res.status_int, 500)

    def test_post_container_add_custom_metadata(self):
        headers = {"X-Container-Meta-Name": "teste"}
        res = self._driver('/v1/account/container', 'POST', headers).response()
        self.assertEquals(res.status_int, 204)

    def test_post_container_del_custom_metadata(self):
        headers = {"X-Remove-Container-Meta-Name": "x"}
        res = self._driver('/v1/account/container', 'POST', headers).response()
        self.assertEquals(res.status_int, 204)

    def test_post_container_make_public(self):
        headers = {"X-Container-Read": ".r:*"}
        res = self._driver('/v1/account/container', 'POST', headers).response()
        self.assertEquals(res.status_int, 204)

    def test_post_container_make_private(self):
        headers = {"X-Remove-Container-Read": "x"}
        res = self._driver('/v1/account/container', 'POST', headers).response()
        self.assertEquals(res.status_int, 204)

    def test_post_container_add_versioning(self):
        headers = {"X-Versions-Location": "x"}
        res = self._driver('/v1/account/container', 'POST', headers).response()
        self.assertEquals(res.status_int, 204)

    def test_post_container_del_versioning(self):
        headers = {"X-Remove-History-Location": "x"}
        res = self._driver('/v1/account/container', 'POST', headers).response()
        self.assertEquals(res.status_int, 204)

    def test_post_container_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account/container', 'POST').response()
        self.assertEquals(res.status_int, 500)

    def test_post_container_404_if_blob_does_not_exists(self):
        fake_bucket = FakeBucket(blob=None)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container', 'POST').response()
        self.assertEquals(res.status_int, 404)

    def test_call_delete_container(self):
        res = self._driver('/v1/account/container', 'DELETE').response()
        self.assertEquals(res.status_int, 204)

    def test_delete_container_404_if_bucket_does_not_exists(self):
        fake_bucket = FakeBucket(exists=False)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container', 'DELETE').response()
        self.assertEquals(res.status_int, 404)

    def test_delete_container_with_blobs(self):
        fake_blobs = FakeBlob(exists=True)
        fake_bucket = FakeBucket(blobs=[fake_blobs])
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container', 'DELETE').response()
        self.assertEquals(res.status_int, 204)

    def test_delete_container_with_error(self):
        self.mock_client.return_value = FakeClient(error=Exception())
        res = self._driver('/v1/account/container', 'DELETE').response()
        self.assertEquals(res.status_int, 500)

    # Object tests

    def test_call_head_object(self):
        res = self._driver('/v1/account/container/object', 'HEAD').response()
        self.assertEquals(res.headers.get('Content-Disposition'), 'inline')
        self.assertEquals(res.status_int, 204)

    def test_call_head_object_with_headers(self):
        fake_blob = FakeBlob(exists=True, header=False)
        fake_bucket = FakeBucket(blob=fake_blob)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container/object', 'HEAD').response()
        self.assertEquals(res.status_int, 204)

    @patch('google.cloud.storage')
    def test_call_get_object(self, mock_storage):
        res = self._driver('/v1/account/container/object', 'GET').response()
        self.assertEquals(res.status_int, 200)

    def test_call_get_object_404_if_blob_does_not_exists(self):
        fake_blob = FakeBlob(exists=False)
        fake_bucket = FakeBucket(blob=fake_blob)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container/object', 'GET').response()
        self.assertEquals(res.status_int, 404)

    def test_call_put_object(self):
        res = self._driver('/v1/account/container/object', 'PUT').response()
        self.assertEquals(res.status_int, 201)

    @patch('swift_cloud.drivers.gcp.SwiftGCPDriver.post_object')
    def test_call_post_object(self, mock_post_object):
        res = self._driver('/v1/account/container/object', 'POST').response()
        mock_post_object.assert_called_once()

    def test_call_post_object_with_headers(self):
        headers = {"X-Object-Meta-Name": "teste", "Cache-Control": 1000,
            "Content-Encoding": "gzip", "Content-Disposition": "attachment"}
        res = self._driver('/v1/account/container/object', 'POST', headers).response()
        self.assertEquals(res.status_int, 202)

    def test_call_post_object_without_headers(self):
        fake_blob = FakeBlob(exists=True, header=False)
        fake_bucket = FakeBucket(blob=fake_blob)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container/object', 'POST').response()
        self.assertEquals(res.status_int, 202)

    def test_call_post_object_404_if_blob_does_not_exists(self):
        fake_blob = FakeBlob(exists=False)
        fake_bucket = FakeBucket(blob=fake_blob)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container/object', 'POST').response()
        self.assertEquals(res.status_int, 404)

    def test_call_delete_object(self):
        res = self._driver('/v1/account/container/object', 'DELETE').response()
        self.assertEquals(res.status_int, 204)

    def test_call_delete_object_404_if_blob_does_not_exists(self):
        fake_blob = FakeBlob(exists=False)
        fake_bucket = FakeBucket(blob=fake_blob)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container/object', 'DELETE').response()
        self.assertEquals(res.status_int, 404)

    def test_head_object_returns_204_status_code(self):
        res = self._driver('/v1/account/container/object', 'HEAD').response()
        self.assertEquals(res.status_int, 204)

    def test_head_object_returns_404_if_blob_does_not_exists(self):
        fake_blob = FakeBlob(exists=False)
        fake_bucket = FakeBucket(blob=fake_blob)
        self.mock_client.return_value = FakeClient(bucket=fake_bucket)
        res = self._driver('/v1/account/container/object', 'HEAD').response()
        self.assertEquals(res.status_int, 404)

    def test_head_object_headers(self):
        res = self._driver('/v1/account/container/object', 'HEAD').response()
        self.assertIn('Content-Type', res.headers)
        self.assertIn('Etag', res.headers)

    @patch('swift_cloud.tools.SwiftCloudTools.add_delete_at')
    def test_call_post_object_add_delete_at(self, mock_add):
        mock_add.return_value = True, 'ok'
        headers = {"x-delete-at": 1623767403}
        res = self._driver('/v1/account/container/object', 'POST', headers).response()
        self.assertEquals(res.status_int, 202)

    @patch('swift_cloud.tools.SwiftCloudTools.remove_delete_at')
    def test_call_post_object_add_delete_at(self, mock_remove):
        mock_remove.return_value = True, 'ok'
        headers = {"x-delete-at": ''}
        res = self._driver('/v1/account/container/object', 'POST', headers).response()
        self.assertEquals(res.status_int, 202)

    @patch('swift_cloud.tools.SwiftCloudTools.add_delete_at')
    def test_post_object_delete_at_fails_returns_error(self, mock_add):
        mock_add.return_value = False, 'Error'
        headers = {"x-delete-at": 1623767403}
        res = self._driver('/v1/account/container/object', 'POST', headers).response()
        self.assertIn(res.body, '{"error": "X-Delete Error"}')

    @patch('swift_cloud.tools.SwiftCloudTools.convert_timestamp_to_datetime')
    def test_object_delete_at_invalid_date_returns_error(self, mock_date):
        mock_date.return_value = False, 'Error'
        headers = {"x-delete-at": 1623767403}
        res = self._driver('/v1/account/container/object', 'POST', headers).response()
        self.assertIn(res.body, '{"error": "X-Delete Error"}')

    @patch('swift_cloud.tools.SwiftCloudTools.add_delete_at')
    def test_call_put_object_add_delete_at(self, mock_add):
        mock_add.return_value = True, 'ok'
        headers = {"x-delete-at": 1623767403}
        res = self._driver('/v1/account/container/object', 'PUT', headers).response()
        self.assertEquals(res.status_int, 201)

    @patch('swift_cloud.tools.SwiftCloudTools.remove_delete_at')
    def test_call_post_object_add_delete_at(self, mock_remove):
        mock_remove.return_value = True, 'ok'
        headers = {"x-delete-at": ''}
        res = self._driver('/v1/account/container/object', 'PUT', headers).response()
        self.assertEquals(res.status_int, 201)

    @patch('swift_cloud.tools.SwiftCloudTools.add_delete_at')
    def test_put_object_delete_at_fails_returns_error(self, mock_add):
        mock_add.return_value = False, 'Error'
        headers = {"x-delete-at": 1623767403}
        res = self._driver('/v1/account/container/object', 'PUT', headers).response()
        self.assertEquals(res.status_int, 500)
