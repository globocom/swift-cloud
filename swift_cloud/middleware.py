import logging

from swift.common.swob import Request
from swift.common.utils import split_path
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

    def gcp_handler(self, req, account_info, has_account):
        driver = SwiftGCPDriver(req, account_info, self.app, self.conf)
        http_verbs = ['HEAD', 'GET', 'POST', 'DELETE']
        resp = driver.response()

        if req.method == 'POST' and has_account:
            return self.app

        if req.method in http_verbs and resp.status_int == 404:
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

        if cloud_name and cloud_name in self.providers:
            req = Request(environ)
            handler = self.app

            if cloud_name == 'gcp':
                has_account = account and not container and not obj
                handler = self.gcp_handler(req, account_info, has_account)

            return handler(environ, start_response)

        return self.app(environ, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
