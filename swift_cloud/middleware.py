import logging

from swift.common.swob import Request, Response
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
        self.driver_name = conf.get('driver', 'gcp')

    def swift_cloud_handler(self, req):
        if self.driver_name == 'gcp':
            credentials_path = self.conf.get('gcp_credentials')
            driver = SwiftGCPDriver(req, credentials_path)
            return driver.response()

        return Response(request=req, status=500, body=b'Invalid driver',
                        content_type="text/plain")

    def __call__(self, environ, start_response):
        req = Request(environ)

        if self.driver_name:
            return self.swift_cloud_handler(req)(environ, start_response)

        return self.app(environ, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
