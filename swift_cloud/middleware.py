import logging

from swift.common.swob import Request, Response
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

    def gcp_handler(self, req):
        credentials_path = self.conf.get('gcp_credentials')
        driver = SwiftGCPDriver(req, credentials_path)

        return driver.response()

    def __call__(self, environ, start_response):
        req = Request(environ)

        account_info = get_account_info(environ, self.app)
        cloud_name = account_info['meta'].get('cloud')

        if cloud_name and cloud_name == 'gcp':
            return self.gcp_handler(req)(environ, start_response)

        return self.app(environ, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
