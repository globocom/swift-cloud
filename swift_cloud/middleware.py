import logging

from swift.common.swob import Request
from swift.common.utils import split_path
from swift.common.middleware.proxy_logging import ProxyLoggingMiddleware

from google.oauth2.service_account import Credentials
from google.cloud import storage

from swift_cloud.drivers.gcp import SwiftGCPDriver

log = logging.getLogger(__name__)


class SwiftCloudMiddleware(object):
    """
    Swift Cloud Middleware

    Middleware for Openstack Swift to store objecs in multiple cloud providers
    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf
        self.providers = conf.get('cloud_providers').split()
        self.x_cloud_bypass = conf.get('x_cloud_bypass')

        credentials_path = conf.get('gcp_credentials')
        credentials = Credentials.from_service_account_file(credentials_path)
        self.client = storage.Client(credentials=credentials)

    def gcp_handler(self, req, labels):
        driver = SwiftGCPDriver(req, self.app, self.conf)
        http_verbs = ['HEAD', 'GET', 'POST', 'DELETE']
        resp = driver.response()

        if isinstance(resp, ProxyLoggingMiddleware):
            return self.app

        cloud_migration = labels.get('account-meta-cloud-migration')

        if cloud_migration:
            return resp

        index = req.url.find('/.trash-')

        if req.method in http_verbs and resp.status_int == 404 and index == -1:
            return self.app

        return resp

    def __call__(self, environ, start_response):
        try:
            (version, account, container, obj) = \
                split_path(environ['PATH_INFO'], 2, 4, True)
        except ValueError as err:
            return self.app(environ, start_response)

        cloud_name = ''
        x_cloud_bypass = environ.get('HTTP_X_CLOUD_BYPASS')
        new_cloud_name = environ.get('HTTP_X_ACCOUNT_META_CLOUD')

        path_info = environ.get('PATH_INFO')
        project = path_info.split('/')[2]
        labels = {}

        try:
            bucket = self.client.get_bucket(project.lower(), timeout=30)
            labels = bucket.labels
            cloud_name = labels.get('account-meta-cloud')
        except Exception:
            pass

        if x_cloud_bypass == self.x_cloud_bypass:
            return self.app(environ, start_response)

        if (new_cloud_name and new_cloud_name in self.providers) or \
            (cloud_name and cloud_name in self.providers):
            req = Request(environ)
            handler = self.app

            if cloud_name == 'gcp' or new_cloud_name == 'gcp':
                handler = self.gcp_handler(req, labels)

            return handler(environ, start_response)

        return self.app(environ, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
