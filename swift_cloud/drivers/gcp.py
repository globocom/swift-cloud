import json
import io
from swift.common.swob import Response, wsgi_to_str
from swift.common.utils import split_path, Timestamp
from swift.common.header_key_dict import HeaderKeyDict
from google.oauth2 import service_account
from google.cloud import storage
from uuid import uuid4


class SwiftGCPDriver:

    def __init__(self, req, credentials_path):
        self.req = req
        self.credentials_path = credentials_path

        self.account = None
        self.container = None
        self.obj = None

        self.headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-Timestamp': Timestamp.now().normal
        }

    def response(self):
        params = {}
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

        return Response(**params)

    def handle_account(self):
        # project_name = 'test'
        # project_id = '792079638c6441bca02071501f4eb273'

        if self.req.method == 'HEAD':
            return self.head_account()

        if self.req.method == 'GET':
            return self.get_account()

    def head_account(self):
        headers = {
            'X-Account-Container-Count': 1,
            'X-Account-Object-Count': 0,
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
        if self.req.method == 'GET':
            return self.get_container()

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

    def get_client(self):
        credentials = service_account.Credentials.from_service_account_file(self.credentials_path)
        scoped_credentials = credentials.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        client = storage.Client(credentials=credentials)
        return client

    def get_object(self):
        client = self.get_client()
        bucket = client.get_bucket(self.account)
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
        return self._default_response('', 200, {})

    def delete_object(self):
        client = self.get_client()
        bucket = client.get_bucket(self.account)
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

    def _format_content(self, content):
        return json.dumps(content)

    def _default_response(self, body, status, headers):
        body = self._format_content(body)
        headers.update(self.headers)

        return Response(body=body, status=status,
                        headers=HeaderKeyDict(**headers),
                        request=self.req)
