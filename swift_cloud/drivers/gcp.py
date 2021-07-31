import io
import json
import pytz
import logging
import datetime
from uuid import uuid4

from swift.common.swob import Response, wsgi_to_str
from swift.common.utils import split_path, Timestamp
from swift.common.header_key_dict import HeaderKeyDict
from swift.common.exceptions import ChunkReadError

from google.cloud import storage
from google.cloud.exceptions import NotFound, Conflict
from google.oauth2.service_account import Credentials

from swift_cloud.drivers.base import BaseDriver
from swift_cloud.tools import SwiftCloudTools
from swift_cloud.decorators import cors_validation

log = logging.getLogger(__name__)

BUCKET_LOCATION = 'SOUTHAMERICA-EAST1'
RESERVED_META = [
    'x-delete-at',
    'x-delete-after',
    'x-versions-location',
    'x-history-location',
    'x-undelete-enabled',
    'x-container-sysmeta-undelete-enabled'
]


def is_container(blob):
    chunks = blob.name.split('/')
    return len(chunks) == 2 and chunks[-1] == ''


def is_object(level, blob):
    chunks = blob.name.split('/')
    return len(chunks) >= 2 and chunks[-1] != '' and len(chunks) - 1 == level


def is_pseudofolder(level, blob):
    chunks = blob.name.split('/')
    return len(chunks) > 2 and chunks[-1] == '' and len(chunks) - 2 == level


def all_objects(blob):
    chunks = blob.name.split('/')
    return (len(chunks) == 2 and chunks[-1] != '') or (len(chunks) > 2 and 'application/directory' not in blob.content_type)


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

        self.tools = SwiftCloudTools(conf)

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

        prefix = self.req.params.get('prefix')

        self.prefix = prefix[:-1] if prefix else ''
        self.account = account.lower() if account else None
        self.container = container
        self.obj = obj

        if account and container and obj:
            return self.handle_object()
        elif account and container:
            return self.handle_container()
        elif account and not container and not obj:
            return self.handle_account()

        return self._error_response(b'Invalid request path')

    def _get_client(self):
        try:
            credentials_path = self.conf.get('gcp_credentials')
            credentials = Credentials.from_service_account_file(
                credentials_path)
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

    def _error_response(self, error, status=500):
        self.headers['Content-Type'] = 'application/json; charset=utf-8'
        body = {'error': str(error)}
        return Response(body=json.dumps(body), status=status,
                        headers=HeaderKeyDict(**self.headers),
                        request=self.req)

    def _is_authorized(self):
        if 'swift.authorize' in self.req.environ:
            return self.req.environ['swift.authorize'](self.req)
        return self.app

    def handle_account(self):
        aresp = self._is_authorized()
        if aresp:
            return aresp

        if self.req.method == 'HEAD':
            return self.head_account()

        if self.req.method == 'GET':
            return self.get_account()

        if self.req.method in ['POST']:
            """POST requests for Account will be forwarded"""
            return self.app

        if self.req.method == 'DELETE':
            return self.delete_account()

    def _get_or_create_bucket(self, bucket_name):
        try:
            return self.client.get_bucket(
                bucket_name,
                timeout=30
            )
        except NotFound:
            bucket = self.client.create_bucket(
                bucket_name, location=BUCKET_LOCATION)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = False
            bucket.patch()
            return bucket
        except Exception as err:
            log.error(err)
            return None

    def head_account(self):
        account_bucket = self._get_or_create_bucket(self.account)

        if not account_bucket:
            return self._error_response('Get Account Error.')

        labels = account_bucket.labels

        headers = {
            'X-Account-Container-Count': labels.get('container-count', 0),
            'X-Account-Object-Count': labels.get('object-count', 0),
            'X-Account-Bytes-Used': labels.get('bytes-used', 0)
        }

        account_meta = self.account_info.get('meta')
        for key in account_meta:
            new_key = 'X-Account-Meta-{}'.format(key)
            headers[new_key] = account_meta[key]

        return self._default_response('', 204, headers)

    def get_account(self):
        account_bucket = self._get_or_create_bucket(self.account)

        if not account_bucket:
            return self._error_response('Get Account Error.')

        account_blobs, containers = [], []

        try:
            account_blobs = list(account_bucket.list_blobs())
            containers = filter(is_container, account_blobs)
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        container_list = []
        for item in containers:
            metadata = item.metadata or {}
            container_list.append({
                'count': metadata.get('object-count', 0),
                'bytes': metadata.get('bytes-used', 0),
                'name': item.name.replace('/', ''),
                'last_modified': item.updated.isoformat()
            })

        labels = account_bucket.labels

        headers = {
            'X-Account-Container-Count': labels.get('container-count', 0),
            'X-Account-Object-Count': labels.get('object-count', 0),
            'X-Account-Bytes-Used': labels.get('bytes-used', 0)
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

    def delete_account(self):
        try:
            account_bucket = self.client.get_bucket(
                bucket_name,
                timeout=30
            )
            account_bucket.delete()
        except NotFound:
            return self._default_response('Account not found.', 404)
        except Conflict:
            return self._error_response('Account must be empty.')

        return self._default_response('', 204, headers)

    def handle_container(self):
        aresp = self._is_authorized()
        if aresp:
            return aresp

        if self.req.method == 'HEAD':
            return self.head_container(self.req)

        if self.req.method == 'GET':
            return self.get_container(self.req)

        if self.req.method == 'PUT':
            return self.put_container(self.req)

        if self.req.method == 'POST':
            return self.post_container(self.req)

        if self.req.method == 'DELETE':
            return self.delete_container(self.req)

    @cors_validation
    def head_container(self, req, bucket=None, obj=None):
        try:
            if not bucket:
                bucket = self.client.get_bucket(
                    self.account,
                    timeout=30
                )
            prefix = '/'.join([self.container, self.prefix])
            blob = bucket.get_blob(prefix)
            container_blobs = list(bucket.list_blobs(prefix=prefix))
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        headers = {}
        if blob and blob.metadata:
            for key, value in blob.metadata.items():
                if key.lower() not in RESERVED_META:
                    headers['X-Container-{}'.format(key)] = value
                else:
                    headers[key] = value

        return self._default_response('', 204, headers)

    @cors_validation
    def get_container(self, req, bucket=None, obj=None):
        try:
            if not bucket:
                bucket = self.client.get_bucket(
                    self.account,
                    timeout=30
                )
            prefix = '/'.join([self.container, self.prefix])
            blob = bucket.get_blob(prefix)
            blobs = list(bucket.list_blobs(prefix=prefix))
            level = len(prefix[:-1].split('/'))
            pseudofolders = filter(lambda x: is_pseudofolder(level, x), blobs)
            objects = filter(lambda x: is_object(level, x), blobs)
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

        headers = {}
        if blob and blob.metadata:
            for key, value in blob.metadata.items():
                if key.lower() not in RESERVED_META:
                    headers['X-Container-{}'.format(key)] = value
                else:
                    headers[key] = value

        status = 200
        if self.req.params.get('marker'):  # TODO: pagination
            container_list = []
            status = 204

        return self._json_response(object_list, status, headers)

    def _set_container_metadata(self, blob):
        metadata = blob.metadata or {}

        if not metadata.get('object-count'):
            metadata['object-count'] = 0

        if not metadata.get('bytes-used'):
            metadata['bytes-used'] = 0

        for item in self.req.headers.iteritems():
            key, value = item
            key = key.lower()
            prefix = key.split('x-container-meta-')

            if len(prefix) > 1:
                meta = 'meta-{}'.format(prefix[1].lower())
                metadata[meta] = item[1].lower()
                continue

            prefix = key.split('x-remove-container-meta-')

            if len(prefix) > 1:
                meta = 'meta-{}'.format(prefix[1].lower())
                if metadata.get(meta):
                    metadata[meta] = None
                continue

            if key == 'x-container-read' and value == '.r:*':
                metadata["read"] = value
                continue

            if (key == 'x-container-read' and value == '') or key == 'x-remove-container-read':
                if metadata.get('read'):
                    metadata["read"] = None
                continue

            if key == 'x-versions-location' or key == 'x-history-location':
                metadata["x-versions-location"] = '_version_{}'.format(self.container)
                continue

            if key == 'x-remove-versions-location' or key == 'x-remove-history-location':
                if metadata.get('x-versions-location'):
                    metadata["x-versions-location"] = None
                continue

            if key == 'x-undelete-enabled':
                metadata["x-container-sysmeta-undelete-enabled"] = value
                metadata["x-undelete-enabled"] = value
                continue

            if key == 'x-container-sharding':
                metadata["x-container-sharding"] = value
                continue

        return metadata

    @cors_validation
    def put_container(self, req, bucket=None, obj=None):
        try:
            if not bucket:
                bucket = self.client.get_bucket(
                    self.account,
                    timeout=30
                )
        except NotFound:
            bucket = self.client.create_bucket(
                self.account, location=BUCKET_LOCATION)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = False
            bucket.patch()
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        blob = bucket.blob(self.container + '/')
        blob.upload_from_string(
            '', content_type='application/directory;charset=UTF-8')

        metadata = self._set_container_metadata(blob)

        blob.metadata = metadata
        blob.patch()

        # updates account container count
        labels = bucket.labels
        container_count = int(labels.get('container-count', 0))
        labels['container-count'] = container_count + 1
        bucket.labels = labels
        bucket.patch()

        return self._default_response('', 201)

    @cors_validation
    def post_container(self, req, bucket=None, obj=None):
        try:
            if not bucket:
                bucket = self.client.get_bucket(
                    self.account,
                    timeout=30
                )
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        blob = bucket.get_blob(self.container + '/')

        if not blob:
            return self._default_response('', 404)

        metadata = self._set_container_metadata(blob)

        blob.metadata = metadata
        blob.patch()

        return self._default_response('', 204)

    @cors_validation
    def delete_container(self, req, bucket=None, obj=None):
        try:
            if not bucket:
                bucket = self.client.get_bucket(
                    self.account,
                    timeout=30
                )
        except Exception as err:
            log.error(err)
            return self._error_response(err)

        if not bucket.exists():
            return self._default_response('', 404)

        prefix = self.container + '/'
        blob = bucket.get_blob(prefix)
        if not blob:
            return self._default_response('', 404)

        blobs = list(bucket.list_blobs(prefix=prefix, max_results=3))
        if len(blobs) > 1:
            return self._default_response('', 409)

        blob.delete()

        # updates account container count
        labels = bucket.labels
        container_count = int(labels.get('container-count', 0))
        labels['container-count'] = max(0, container_count - 1)
        bucket.labels = labels
        bucket.patch()

        return self._default_response('', 204)

    def handle_object(self):
        if self.req.method == 'HEAD':
            return self.head_object(self.req)

        if self.req.method == 'GET':
            return self.get_object(self.req)

        aresp = self._is_authorized()
        if aresp:
            return aresp

        if self.req.method == 'PUT':
            return self.put_object(self.req)

        if self.req.method == 'POST':
            return self.post_object(self.req)

        if self.req.method == 'DELETE':
            return self.delete_object(self.req)

    def get_object_headers(self, blob):
        headers = {
            'Content-Type': blob.content_type,
            'Etag': blob.etag,
            'Last-Modified': datetime.datetime.strftime(
                blob.updated,
                '%a, %d %b %Y %H:%M:%S GMT'
            )
        }

        if blob.cache_control:
            headers['Cache-Control'] = blob.cache_control

        if blob.content_encoding:
            headers['Content-Encoding'] = blob.content_encoding

        if blob.content_disposition:
            headers['Content-Disposition'] = blob.content_disposition

        if blob.size:
            headers['Content-Length'] = blob.size

        if blob.metadata:
            for key, value in blob.metadata.items():
                if key.lower() not in RESERVED_META:
                    headers['x-object-meta-{}'.format(key)] = value
                else:
                    headers[key] = value

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

        reserved_keys = filter(lambda x: x.lower() in RESERVED_META,
                               self.req.headers.keys())

        if blob.metadata:
            for key in blob.metadata.keys():
                metadata[key] = blob.metadata[key]

        for item in meta_keys:
            key = item.lower().split('x-object-meta-')[-1]
            metadata[key] = self.req.headers.get(item)

        for item in reserved_keys:
            key = item.lower()
            metadata[key] = self.req.headers.get(item)

        if len(meta_keys) or len(reserved_keys):
            blob.metadata = metadata
            updated = True

        return updated, blob

    @cors_validation
    def head_object(self, req, bucket=None, obj=None):
        if not bucket:
            bucket = self.client.get_bucket(
                self.account,
                timeout=30
            )
        obj_path = "{}/{}".format(self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob or not blob.exists():
            return self._default_response('', 404)

        metadata = blob.metadata or {}
        read = metadata.get('read')

        if not read or read != '.r:*':
            aresp = self._is_authorized()
            if aresp:
                return self._default_response('', 401)

        headers = self.get_object_headers(blob)

        return self._default_response('', 204, headers)

    @cors_validation
    def get_object(self, req, bucket=None, blob=None):
        if not bucket:
            bucket = self.client.get_bucket(
                self.account,
                timeout=30
            )

        if not blob:
            blob = bucket.get_blob(self.container + '/')

        if not blob:
            return self._default_response('', 404)

        metadata = blob.metadata or {}
        read = metadata.get('read')

        if not read or read != '.r:*':
            aresp = self._is_authorized()
            if aresp:
                return self._default_response('', 401)

        obj_path = "%s/%s" % (self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob or not blob.exists():
            return self._default_response('', 404)

        headers = self.get_object_headers(blob)

        return self._default_response(
            blob.download_as_bytes(), 200, headers)

    def update_delete_at(self, blob):
        result = True
        delete_at = self.req.headers.get('x-delete-at')
        delete_after = self.req.headers.get('x-delete-after')
        remove_delete_at = self.req.headers.get('x-remove-delete-at')
        remove_delete_after = self.req.headers.get('x-remove-delete-after')
        date = None

        if delete_at and delete_at != '':
            result, date = self.tools.convert_timestamp_to_datetime(delete_at)

            if not result:
                return False, blob

        if delete_after and delete_after != '':
            try:
                seconds = int(delete_after)
            except ValueError:
                return False, blob

            now_time = datetime.datetime.now(pytz.timezone('Brazil/East'))
            date_time = now_time + datetime.timedelta(seconds=seconds)
            date = date_time.strftime('%Y-%m-%d %H:%M:%S')

        if date:
            result, msg = self.tools.add_delete_at(
                self.account, self.container, self.obj, date)
            log.info(msg)

            if not result:
                return False, blob

        empty_del_at = delete_at and delete_at == ''
        empty_del_after = delete_after and delete_after == ''

        if empty_del_at or empty_del_after or remove_delete_at or remove_delete_after:
            metadata = blob.metadata or {}

            if metadata.get('x-delete-at'):
                blob.metadata['x-delete-at'] = None

            if metadata.get('x-delete-after'):
                blob.metadata['x-delete-after'] = None

            result, msg = self.tools.remove_delete_at(
                self.account, self.container, self.obj)
            log.info(msg)

            if not result:
                return False, blob

        return True, blob

    def _update_counters(self,
                         account_bucket,
                         container_blob,
                         bytes_used,
                         remove=False):
        labels = account_bucket.labels or {}
        metadata = container_blob.metadata or {}

        account_obj_count = int(labels.get('object-count', 0))
        account_bytes_used = int(labels.get('bytes-used', 0))
        container_obj_count = int(metadata.get('object-count', 0))
        container_bytes_used = int(metadata.get('bytes-used', 0))

        if remove:
            labels['object-count'] = max(0, account_obj_count - 1)
            labels['bytes-used'] = max(0, account_bytes_used - bytes_used)
            metadata['object-count'] = max(0, container_obj_count - 1)
            metadata['bytes-used'] = max(0, container_bytes_used - bytes_used)
        else:
            labels['object-count'] = account_obj_count + 1
            labels['bytes-used'] = account_bytes_used + bytes_used
            metadata['object-count'] = container_obj_count + 1
            metadata['bytes-used'] = container_bytes_used + bytes_used

        account_bucket.labels = labels
        container_blob.metadata = metadata

        account_bucket.patch()
        container_blob.patch()

    @cors_validation
    def put_object(self, req, bucket=None, obj=None):
        if not bucket:
            bucket = self.client.get_bucket(
                self.account,
                timeout=30
            )

        container_blob = bucket.get_blob(self.container + '/')

        if not container_blob:
            return self._default_response('The resource could not be found', 404)

        obj_path = "{}/{}".format(self.container, self.obj)
        blob = bucket.blob(obj_path)
        content_type = self.req.headers.get('Content-Type')
        delete_at = self.req.headers.get('x-delete-at')
        delete_after = self.req.headers.get('x-delete-after')

        _, blob = self.update_object_headers(blob)

        if delete_at or delete_after:
            delete_at_result, blob = self.update_delete_at(blob)
            if not delete_at_result:
                return self._error_response('X-Delete Error')

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

        headers = self.get_object_headers(blob)
        headers['Content-Length'] = 0

        self._update_counters(bucket, container_blob, len(obj_data))

        return self._default_response('', 201, headers)

    @cors_validation
    def post_object(self, req, bucket=None, obj=None):
        if not bucket:
            bucket = self.client.get_bucket(
                self.account,
                timeout=30
            )
        obj_path = "{}/{}".format(self.container, self.obj)
        blob = bucket.get_blob(obj_path)

        if not blob or not blob.exists():
            return self._default_response('', 404)

        updated, blob = self.update_object_headers(blob)

        delete_at_result, blob = self.update_delete_at(blob)

        if not delete_at_result:
            return self._error_response('X-Delete Error')

        if updated:
            blob.patch()

        return self._default_response('', 202)  # Accepted

    @cors_validation
    def delete_object(self, req, bucket=None, obj=None):
        if not bucket:
            bucket = self.client.get_bucket(
                self.account,
                timeout=30
            )
        obj_path = "{}/{}".format(self.container, self.obj)

        container_blob = bucket.get_blob(self.container + '/')
        blob = bucket.get_blob(obj_path)

        if not blob or not blob.exists():
            return self._default_response('', 404)

        headers = self.get_object_headers(blob)
        delete_at = headers.get('x-delete-at')

        if delete_at:
            result, msg = self.tools.remove_delete_at(
                self.account, self.container, self.obj)

            if not result:
                return self._error_response(msg)

        blob.delete()

        self._update_counters(bucket, container_blob, blob.size, remove=True)

        return self._default_response('', 204)
