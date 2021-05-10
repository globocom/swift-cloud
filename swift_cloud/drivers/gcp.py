import io
import json
import logging
from uuid import uuid4

from swift.common.swob import Response, wsgi_to_str
from swift.common.utils import split_path, Timestamp
from swift.common.header_key_dict import HeaderKeyDict
from swift.common.exceptions import ChunkReadError

from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.oauth2.service_account import Credentials

from swift_cloud.drivers.base import BaseDriver

log = logging.getLogger(__name__)

BUCKET_LOCATION = 'SOUTHAMERICA-EAST1'


def is_container(blob):
    n = blob.name.split('/')
    return len(n) == 2 and n[-1] == ''


def is_object(blob):
    n = blob.name.split('/')
    return len(n) >= 2 and n[-1] != ''


def is_pseudofolder(blob):
    n = blob.name.split('/')
    return len(n) > 2 and n[-1] == ''


def blobs_size(blob_list):
    size = 0
    for blob in blob_list:
        size += blob.size
    return size


class SwiftGCPDriver(BaseDriver):

    def __init__(self, req, account_info, app, conf):
        self.req = req
        self.account_info = account_info
        self.app = app
        self.conf = conf

        self.max_results = int(conf.get('max_results'))
        self.client = self._get_client()

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
        if not self.client:
            return self.app

        version, account, container, obj = split_path(
            wsgi_to_str(self.req.path), 1, 4, True)

        self.account = account.lower() if account else None
        self.container = container
        self.obj = obj

        if account and container and obj:
            return self.handle_object()
        elif account and container:
            return self.handle_container()
        elif account and not container and not obj:
            return self.handle_account()

        return self._default_response(b'Invalid request path', 500)

    def _get_client(self):
        try:
            credentials_path = self.conf.get('gcp_credentials')
            credentials = Credentials.from_service_account_file(credentials_path)
            return storage.Client(credentials=credentials)
        except Exception as err:
            log.error(err)
            return None

    def _default_response(self, body, status, headers={}):
        self.headers.update(headers)
        return Response(body=body, status=status,
                        headers=HeaderKeyDict(**self.headers),
                        request=self.req)

    def _json_response(self, body, status, headers={}):
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

        if self.req.method == 'POST':
            """All POST requests for Account will be forwarded"""
            return self.app

    def _get_or_create_bucket(self, bucket_name):
        try:
            return self.client.get_bucket(bucket_name)
        except NotFound:
            bucket = self.client.create_bucket(bucket_name, location=BUCKET_LOCATION)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = False
            bucket.patch()
            return bucket
        except Exception as err:
            log.error(err)
            return None

    def head_account(self):
        account_bucket = self._get_or_create_bucket(self.account)

        if not account_bucket:
            return self._error_response('Accout bucket not found.')

        account_blobs, containers, objects = [], [], []

        try:
            account_blobs = list(account_bucket.list_blobs())
            containers = filter(is_container, account_blobs)
            objects = filter(is_object, account_blobs)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        headers = {
            'X-Account-Container-Count': len(containers),
            'X-Account-Object-Count': len(objects),
            'X-Account-Bytes-Used': blobs_size(account_blobs)
        }

        account_meta = self.account_info.get('meta')
        for key in account_meta:
            new_key = 'X-Account-Meta-{}'.format(key)
            headers[new_key] = account_meta[key]

        return self._default_response('', 204, headers)

    def get_account(self):
        account_bucket = self._get_or_create_bucket(self.account)

        if not account_bucket:
            return self._error_response('Accout bucket not found.')

        account_blobs, containers, objects = [], [], []

        try:
            account_blobs = list(account_bucket.list_blobs())
            containers = filter(is_container, account_blobs)
            objects = filter(is_object, account_blobs)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        container_list = []
        for item in containers:
            folder_blobs = list(account_bucket.list_blobs(prefix=item.name))
            container_list.append({
                'count': len(folder_blobs) - 1,  # all blobs except main folder (container)
                'bytes': blobs_size(folder_blobs),
                'name': item.name.replace('/', ''),
                'last_modified': item.updated.isoformat()
            })

        headers = {
            'X-Account-Container-Count': len(container_list),
            'X-Account-Object-Count': len(objects),
            'X-Account-Bytes-Used': blobs_size(account_blobs)
        }

        account_meta = self.account_info.get('meta')
        for key in account_meta:
            new_key = 'X-Account-Meta-{}'.format(key)
            headers[new_key] = account_meta[key]

        status = 200
        if self.req.params.get('marker'):  # TODO: pagination
            container_list = []
            status = 204

        return self._json_response(container_list, status, headers)

    def handle_container(self):
        if self.req.method == 'HEAD':
            return self.head_container()

        if self.req.method == 'GET':
            return self.get_container()

        if self.req.method == 'PUT':
            return self.put_container()

        if self.req.method == 'POST':
            return self.post_container()

        if self.req.method == 'DELETE':
            return self.delete_container()

    def head_container(self):
        try:
            account_bucket = self.client.get_bucket(self.account)
            prefix = self.container + '/'
            container_blobs = list(account_bucket.list_blobs(prefix=prefix))
            objects = filter(is_object, container_blobs)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        headers = {
            'X-Container-Object-Count': len(objects),
            'X-Container-Bytes-Used': blobs_size(objects)
        }

        return self._default_response('', 204, headers)

    def get_container(self):
        try:
            account_bucket = self.client.get_bucket(self.account)
            prefix = self.container + '/'
            blobs = list(account_bucket.list_blobs(prefix=prefix))
            objects = filter(is_object, blobs)
            pseudofolders = filter(is_pseudofolder, blobs)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        object_list = []
        for item in (objects + pseudofolders):
            object_list.append({
                'name': item.name.replace(self.container + '/', ''),
                'bytes': item.size,
                'hash': item.md5_hash,
                'content_type': item.content_type,
                'last_modified': item.updated.isoformat()
            })

        headers = {
            'X-Container-Object-Count': len(object_list),
            'X-Container-Bytes-Used': blobs_size(objects)
        }

        status = 200
        if self.req.params.get('marker'):  # TODO: pagination
            container_list = []
            status = 204

        return self._json_response(object_list, status, headers)

    def put_container(self):
        try:
            bucket = self.client.get_bucket(self.account)
        except NotFound:
            bucket = self.client.create_bucket(self.account, location=BUCKET_LOCATION)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = False
            bucket.patch()
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        blob = bucket.blob(self.container + '/')
        blob.upload_from_string('', content_type='application/directory;charset=UTF-8')

        return self._default_response('', 201)

    def post_container(self):
        try:
            bucket = self.client.get_bucket(self.account)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        blob = bucket.get_blob(self.container + '/')

        if not blob:
            return self._default_response('', 404)

        metadata = blob.metadata or {}

        for item in self.req.headers.iteritems():
            key, value = item
            prefix = key.split('X-Container-Meta-')

            if len(prefix) > 1:
                meta = prefix[1].lower()
                metadata[meta] = item[1].lower()
                continue

            prefix = key.split('X-Remove-Container-Meta-')

            if len(prefix) > 1:
                meta = prefix[1].lower()
                if metadata.get(meta):
                    metadata[meta] = None
                continue

            if key == 'X-Container-Read':
                if value == '.r:*':
                    # bucket.make_public(recursive=True, future=True, client=self.client)
                    metadata["read"] = value
                    continue

            if key == 'X-Remove-Container-Read':
                # bucket.make_private(recursive=True, future=True, client=self.client)
                if metadata.get('read'):
                    metadata["read"] = None
                continue

            if key == 'X-Versions-Location' or key == 'X-History-Location':
                bucket.versioning_enabled = True
                bucket.patch()
                continue

            if key == 'X-Remove-Versions-Location' or key == 'X-Remove-History-Location':
                bucket.versioning_enabled = False
                bucket.patch()
                continue

        blob.metadata = metadata
        blob.patch()

        return self._default_response('', 204)

    def delete_container(self):
        try:
            bucket = self.client.get_bucket(self.account)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        if not bucket.exists():
            return self._default_response('', 404)

        prefix = self.container + '/'
        blobs = list(bucket.list_blobs(prefix=prefix))

        for blob in blobs:
            blob.delete()

        return self._default_response('', 204)

    def handle_object(self):
        if self.req.method == 'HEAD':
            return self.head_object()

        if self.req.method == 'GET':
            return self.get_object()

        if self.req.method == 'PUT':
            return self.put_object()

        if self.req.method == 'POST':
            return self.post_object()

        if self.req.method == 'DELETE':
            return self.delete_object()

    def get_object_headers(self, blob):
        headers = {
            'Content-Type': blob.content_type,
            'Etag': blob.etag,
            'Last-Modified': blob.updated.isoformat()
        }

        if blob.cache_control:
            headers['Cache-Control'] = blob.cache_control

        if blob.content_encoding:
            headers['Content-Encoding'] = blob.content_encoding

        if blob.content_disposition:
            headers['Content-Disposition'] = blob.content_disposition

        if blob.metadata:
            for key, value in blob.metadata.items():
                headers['X-Object-Meta-{}'.format(key)] = value

        return headers

    def update_object_headers(self, blob):
        updated = False

        cache_control = self.req.headers.get('cache-control')
        if cache_control:
            blob.cache_control = cache_control
            updated = True

        content_encoding = self.req.headers.get('content-encoding')
        if content_encoding:
            blob.content_encoding = content_encoding
            updated = True

        content_disposition = self.req.headers.get('content-disposition')
        if content_disposition:
            blob.content_disposition = content_disposition
            updated = True

        metadata = {}
        meta_keys = filter(lambda x: 'x-object-meta' in x.lower(),
                           self.req.headers.keys())

        if blob.metadata:
            for key in blob.metadata.keys():
                metadata[key] = None

        for item in meta_keys:
            key = item.lower().split('x-object-meta-')[-1]
            metadata[key] = self.req.headers.get(item)

        if len(meta_keys):
            blob.metadata = metadata
            updated = True

        return updated, blob

    def head_object(self):
        bucket = self.client.get_bucket(self.account)
        obj_path = "%s/%s" % (self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob.exists():
            return self._default_response('', 404)

        headers = self.get_object_headers(blob)

        return self._default_response('', 204, headers)

    def get_object(self):
        bucket = self.client.get_bucket(self.account)
        obj_path = "%s/%s" % (self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob.exists():
            return self._default_response('', 404)

        headers = self.get_object_headers(blob)

        return self._default_response(
            blob.download_as_bytes(), 200, headers)

    def put_object(self):
        bucket = self.client.get_bucket(self.account)
        obj_path = "%s/%s" % (self.container, self.obj)
        blob = bucket.blob(obj_path)
        content_type = self.req.headers.get('Content-Type')

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

        _, blob = self.update_object_headers(blob)

        blob.upload_from_string(obj_data, content_type=content_type)

        headers = self.get_object_headers(blob)

        return self._default_response('', 201, headers)

    def post_object(self):
        bucket = self.client.get_bucket(self.account)
        obj_path = "%s/%s" % (self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob.exists():
            return self._default_response('', 404)

        updated, blob = self.update_object_headers(blob)

        if updated:
            blob.patch()

        return self._default_response('', 202)  # Accepted

    def delete_object(self):
        bucket = self.client.get_bucket(self.account)
        obj_path = "%s/%s" % (self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob.exists():
            return self._default_response('', 404)

        blob.delete()

        return self._default_response('', 204)
