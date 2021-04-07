import logging

from swift.common.swob import Request
from swift.common.utils import split_path
from swift_cloud.drivers.gcp import SwiftGCPDriver
from swift.proxy.controllers.base import get_account_info

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

    def gcp_handler(self, req):
        credentials_path = self.conf.get('gcp_credentials')
        max_results = int(self.conf.get('max_results'))
        driver = SwiftGCPDriver(req, credentials_path, max_results)
        return driver.response()

    def __call__(self, environ, start_response):
        try:
            (version, account, container, obj) = \
                split_path(environ['PATH_INFO'], 2, 4, True)
        except ValueError as err:
            return self.app(environ, start_response)

        if 'swift.authorize' not in environ:
            self.log.info('No authentication, skipping swift_cloud')
            return self.app(environ, start_response)

        req = Request(environ)

        account_info = get_account_info(environ, self.app)
        cloud_name = account_info['meta'].get('cloud')

        if cloud_name and cloud_name in self.providers:
            aresp = environ['swift.authorize'](req)
            if aresp:
                return aresp(environ, start_response)

            if cloud_name == 'gcp':
                return self.gcp_handler(req)(environ, start_response)

        return self.app(environ, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
