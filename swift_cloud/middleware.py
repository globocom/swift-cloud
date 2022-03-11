import logging

from swift.common.swob import Request
from swift.common.utils import split_path
from swift.common.middleware.proxy_logging import ProxyLoggingMiddleware
from swift.proxy.controllers.base import get_account_info

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

    def gcp_handler(self, req, account_info):
        driver = SwiftGCPDriver(req, account_info, self.app, self.conf)
        http_verbs = ['HEAD', 'GET', 'POST', 'DELETE']
        resp = driver.response()

        if isinstance(resp, ProxyLoggingMiddleware):
            return self.app

        cloud_migration = account_info['meta'].get('cloud-migration')

        if cloud_migration:
            return resp

        index = resp.request.url.find('/.trash-')

        if req.method in http_verbs and resp.status_int == 404 and index == -1:
            return self.app

        return resp

    def __call__(self, environ, start_response):
        try:
            (version, account, container, obj) = \
                split_path(environ['PATH_INFO'], 2, 4, True)
        except ValueError as err:
            return self.app(environ, start_response)

        account_info = get_account_info(environ, self.app)
        cloud_name = account_info['meta'].get('cloud')
        x_cloud_bypass = environ.get('HTTP_X_CLOUD_BYPASS')

        if x_cloud_bypass == self.x_cloud_bypass:
            return self.app(environ, start_response)

        if cloud_name and cloud_name in self.providers:
            req = Request(environ)
            handler = self.app

            if cloud_name == 'gcp':
                handler = self.gcp_handler(req, account_info)

            return handler(environ, start_response)

        return self.app(environ, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
