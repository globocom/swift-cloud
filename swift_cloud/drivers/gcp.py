import io
import json
import logging
from uuid import uuid4

from swift.common.swob import Response, wsgi_to_str
from swift.common.utils import split_path, Timestamp
from swift.common.header_key_dict import HeaderKeyDict

from google.cloud import storage
from google.oauth2 import service_account

log = logging.getLogger(__name__)


def is_container(blob):
    n = blob.name.split('/')
    return len(n) == 2 and n[-1] == ''


def is_object(blob):
    n = blob.name.split('/')
    return len(n) >= 2 and n[-1] != ''


def format_content(content):
    return json.dumps(content)


class SwiftGCPDriver:

    def __init__(self, req, credentials_path):
        self.req = req
        self.client = self._get_client(credentials_path)

        self.account = None
        self.container = None
        self.obj = None

        self.headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-Timestamp': Timestamp.now().normal
        }

    def response(self):
        version, account, container, obj = split_path(
            wsgi_to_str(self.req.path), 1, 4, True)

        self.account = account.lower()
        self.container = container
        self.obj = obj

        if obj and container and account:
            return self.handle_object()
        elif container and account:
            return self.handle_container()
        elif account and not container and not obj:
            return self.handle_account()

        return self._default_response(b'Invalid request path', 500,
                                      {'Content-Type': 'text/plain'})

    def _get_client(self, credentials_path):
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        return storage.Client(credentials=credentials)

    def _default_response(self, body, status, headers):
        body = format_content(body)
        headers.update(self.headers)

        return Response(body=body, status=status,
                        headers=HeaderKeyDict(**headers),
                        request=self.req)

    def handle_account(self):
        # project_name = 'test'
        # project_id = '792079638c6441bca02071501f4eb273'

        if self.req.method == 'HEAD':
            return self.head_account()

        if self.req.method == 'GET':
            return self.get_account()

    def head_account(self):
        try:
            bucket = self.client.get_bucket(self.account)
            blobs = list(bucket.list_blobs())

            containers = filter(is_container, blobs)
            objects = filter(is_object, blobs)
        except Exception as err:
            log.error(err)

        headers = {
            'X-Account-Container-Count': len(containers),
            'X-Account-Object-Count': len(objects),
            'X-Account-Bytes-Used': 0
        }

        return self._default_response('', 204, headers)

    def get_account(self):
        containers = [
            {
                'count': 0,
                'bytes': 0,
                'name': 'test_container',
                'last_modified': "2021-03-22T19:30:10.500000"
            }
        ]

        headers = {
            'X-Account-Container-Count': 1,
            'X-Account-Object-Count': 0,
            'X-Account-Bytes-Used': 0
        }

        status = 200
        if self.req.params.get('marker'):
            status = 204

        return self._default_response(containers, status, headers)

    def handle_container(self):
        if self.req.method == 'HEAD':
            return self.head_container()

        if self.req.method == 'GET':
            return self.get_container()

    def head_container(self):
        headers = {
            'X-Container-Object-Count': 0,
            'X-Container-Bytes-Used': 0
        }

        return self._default_response('', 204, headers)

    def get_container(self):
        headers = {
            'X-Container-Object-Count': 0,
            'X-Container-Bytes-Used': 0
        }

        return self._default_response([], 200, headers)

    def handle_object(self):
        if self.req.method == 'GET':
            return self.get_object()

        if self.req.method == 'PUT':
            return self.put_object()

        if self.req.method == 'DELETE':
            return self.delete_object()

    def get_object(self):
        bucket = self.client.get_bucket(self.account)
        obj = '/'.join([self.container, self.obj])
        blob = bucket.blob(obj)

        if not blob.exists():
            headers = {
                'Content-Type': 'text/html; charset=UTF-8',
                'x-request-id': str(uuid4())
            }
            return self._default_response('', 404, headers)

        blob.get_iam_policy()
        blob_in_string = blob.download_as_string()
        blob_in_bytes = io.BytesIO(blob_in_string)

        headers = {
            'Content-Type': blob.content_type,
            'Accept-Ranges': 'bytes',
            'X-Object-Meta-Orig-Filename': self.obj,
            'X-Timestamp': Timestamp.now().normal
        }
        return Response(body=blob_in_bytes.getvalue(), status=200,
                        headers=HeaderKeyDict(**headers),
                        request=self.req)

    def put_object(self):
        bucket = self.client.get_bucket(self.account)
        obj = '/'.join([self.container, self.obj])
        blob = bucket.blob(obj)
        content_type = self.req.headers.get('Content-Type')
        blob_in_bytes = io.BytesIO(self.req.body)
        blob.upload_from_file(blob_in_bytes, content_type=content_type)

        headers = {
            'Content-Type': 'text/html; charset=UTF-8',
            'Etag': blob.etag
        }
        return Response(body='', status=201,
                        headers=HeaderKeyDict(**headers),
                        request=self.req)

    def delete_object(self):
        bucket = self.client.get_bucket(self.account)
        obj = '/'.join([self.container, self.obj])
        blob = bucket.blob(obj)

        if not blob.exists():
            headers = {
                'Content-Type': 'text/html; charset=UTF-8',
                'x-request-id': str(uuid4())
            }
            return self._default_response('', 404, headers)

        blob.delete()

        headers = {
            'Content-Type': 'text/html; charset=UTF-8'
        }
        return Response(body='', status=204,
                        headers=HeaderKeyDict(**headers),
                        request=self.req)
