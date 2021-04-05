import io
import json
import logging
from uuid import uuid4

from swift.common.swob import Response, wsgi_to_str
from swift.common.utils import split_path, Timestamp
from swift.common.header_key_dict import HeaderKeyDict
from swift.common.exceptions import ChunkReadError

from google.cloud import storage
from google.oauth2 import service_account

from swift_cloud.drivers.base import BaseDriver

log = logging.getLogger(__name__)


def is_container(blob):
    n = blob.name.split('/')
    return len(n) == 2 and n[-1] == ''


def is_object(blob):
    n = blob.name.split('/')
    return len(n) >= 2 and n[-1] != ''


def  is_pseudofolder(blob):
    n = blob.name.split('/')
    return len(n) > 2 and n[-1] == ''


def blobs_size(blob_list):
    size = 0
    for blob in blob_list:
        size += blob.size
    return size


class SwiftGCPDriver(BaseDriver):

    def __init__(self, req, credentials_path):
        self.req = req
        self.client = self._get_client(credentials_path)

        self.account = None
        self.container = None
        self.obj = None

        self.headers = {
            'Content-Type': 'text/html; charset=utf-8',
            'X-Timestamp': Timestamp.now().normal,
            'X-Trans-Id': str(uuid4()),
            'Accept-Ranges': 'bytes'
        }

    def response(self):
        version, account, container, obj = split_path(
            wsgi_to_str(self.req.path), 1, 4, True)

        self.account = account.lower()
        self.container = container
        self.obj = obj

        self.project_id = self.account.replace('auth_', '')
        self.bucket_name = '{}_{}'.format(self.project_id, container)

        if obj and container and account:
            return self.handle_object()
        elif container and account:
            return self.handle_container()
        elif account and not container and not obj:
            return self.handle_account()

        return self._default_response(b'Invalid request path', 500)

    def _get_client(self, credentials_path):
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        return storage.Client(credentials=credentials)

    def _default_response(self, body, status, headers={}):
        self.headers.update(headers)
        return Response(body=body, status=status,
                        headers=HeaderKeyDict(**self.headers),
                        request=self.req)

    def _json_response(self, body, status, headers):
        self.headers.update(headers)
        self.headers['Content-Type'] = 'application/json; charset=utf-8'
        return Response(body=json.dumps(body), status=status,
                        headers=HeaderKeyDict(**self.headers),
                        request=self.req)

    def _error_response(self, error):
        self.headers['Content-Type'] = 'application/json; charset=utf-8'
        body = {'error': str(error)}
        return Response(body=json.dumps(body), status=500,
                        headers=HeaderKeyDict(**self.headers),
                        request=self.req)

    def handle_account(self):
        if self.req.method == 'HEAD':
            return self.head_account()

        if self.req.method == 'GET':
            return self.get_account()

    def head_account(self):
        try:
            bucket_list = list(
                self.client.list_buckets(prefix=self.project_id))
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        objects, containers = [], []
        for bucket in bucket_list:
            objects += list(bucket.list_blobs())
            containers.append(bucket)

        headers = {
            'X-Account-Container-Count': len(containers),
            'X-Account-Object-Count': len(objects),
            'X-Account-Bytes-Used': blobs_size(objects)
        }

        return self._default_response('', 204, headers)

    def get_account(self):
        try:
            buckets = list(
                self.client.list_buckets(prefix=self.project_id))
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        total_blobs, containers = [], []
        for bucket in buckets:
            blobs = list(bucket.list_blobs())
            containers.append({
                'count': len(blobs),
                'bytes': blobs_size(blobs),
                'name': bucket.name.replace(self.project_id + '_', ''),
                'last_modified': bucket.time_created.isoformat()  # TODO: show last update on bucket
            })
            total_blobs += blobs

        headers = {
            'X-Account-Container-Count': len(containers),
            'X-Account-Object-Count': len(total_blobs),
            'X-Account-Bytes-Used': blobs_size(total_blobs),
            'X-Account-Meta-Temp-Url-Key': 'secret'
        }

        status = 200
        if self.req.params.get('marker'):  # TODO: pagination
            containers = []
            status = 204

        return self._json_response(containers, status, headers)

    def handle_container(self):
        if self.req.method == 'HEAD':
            return self.head_container()

        if self.req.method == 'GET':
            return self.get_container()

        if self.req.method == 'PUT':
            return self.put_container()

        if self.req.method == 'DELETE':
            return self.delete_container()

    def head_container(self):
        try:
            bucket = self.client.get_bucket(self.bucket_name)
            blobs = list(bucket.list_blobs())
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        headers = {
            'X-Container-Object-Count': len(blobs),
            'X-Container-Bytes-Used': blobs_size(blobs)
        }

        return self._default_response('', 204, headers)

    def get_container(self):
        try:
            bucket = self.client.get_bucket(self.bucket_name)
            blobs = list(bucket.list_blobs())
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        objects = []
        for item in blobs:
            objects.append({
                'name': item.name,
                'bytes': item.size,
                'hash': item.md5_hash,
                'content_type': item.content_type,
                'last_modified': item.updated.isoformat()
            })

        headers = {
            'X-Container-Object-Count': len(objects),
            'X-Container-Bytes-Used': blobs_size(blobs),
            'X-Container-Meta-Temp-Url-Key': 'secret'
        }

        status = 200
        if self.req.params.get('marker'):  # TODO: pagination
            objects = []
            status = 204

        return self._json_response(objects, status, headers)

    def put_container(self):
        try:
            bucket = self.client.create_bucket(self.bucket_name,
                                               location='SOUTHAMERICA-EAST1')
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        return self._default_response('', 201)

    def delete_container(self):
        try:
            bucket = self.client.get_bucket(self.bucket_name)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        if not bucket.exists():
            return self._default_response('', 404)

        bucket.delete()

        return self._default_response('', 204)

    def handle_object(self):
        if self.req.method == 'HEAD':
            return self.head_object()

        if self.req.method == 'GET':
            return self.get_object()

        if self.req.method == 'PUT':
            return self.put_object()

        if self.req.method == 'DELETE':
            return self.delete_object()

    def head_object(self):
        bucket = self.client.get_bucket(self.bucket_name)
        blob = bucket.get_blob(self.obj)

        if not blob.exists():
            return self._default_response('', 404)

        headers = {
            'Content-Type': blob.content_type,
            'Etag': blob.etag
        }

        return self._default_response('', 204, headers)

    def get_object(self):
        bucket = self.client.get_bucket(self.bucket_name)
        blob = bucket.get_blob(self.obj)

        if not blob.exists():
            return self._default_response('', 404)

        headers = {
            'Content-Type': blob.content_type,
            'Etag': blob.etag
        }

        return self._default_response(blob.download_as_bytes(), 200, headers)

    def put_object(self):
        bucket = self.client.get_bucket(self.bucket_name)
        blob = bucket.blob(self.obj)
        content_type = self.req.headers.get('Content-Type')

        # blob_in_bytes = io.BytesIO(self.req.body)
        # blob.upload_from_file(blob_in_bytes, content_type=content_type)

        def reader():
            try:
                return self.req.environ['wsgi.input'].read()
            except (ValueError, IOError) as e:
                raise ChunkReadError(str(e))

        data_source = iter(reader, b'')
        obj_data = b''

        while True:
            try:
                chunk = next(data_source)
            except StopIteration:
                break
            obj_data += chunk

        blob.upload_from_string(obj_data, content_type=content_type)

        headers = {
            'Etag': blob.etag
        }

        return self._default_response('', 201, headers)

    def delete_object(self):
        bucket = self.client.get_bucket(self.bucket_name)
        blob = bucket.get_blob(self.obj)

        if not blob.exists():
            return self._default_response('', 404)

        blob.delete()

        return self._default_response('', 204)
