import logging
from webob import Request
from swift_cloud.drivers.gcp import SwiftGCPClient

log = logging.getLogger(__name__)


class SwiftCloudMiddleware(object):
    """
    Swift Cloud Middleware

    Middleware for Openstack Swift to store objecs in multiple cloud providers
    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf

    def __call__(self, environ, start_response):
        req = Request(environ)

        # def custom_response(status, headers):
        #     return start_response(status, headers)

        # return self.app(environ, custom_response)

        return self.swift_cloud_response(req)(environ, start_response)

    def swift_cloud_response(self, req):
        driver = self.conf.get('driver', 'gcp')
        client = None

        if driver == 'gcp':
            client = SwiftGCPClient(req)

        if client:
            return client.response()

        return self.app


def filter_factory(global_conf, **local_conf):
    """
    WSGI filtered app for paste.deploy.
    """

    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_cloud_filter(app):
        return SwiftCloudMiddleware(app, conf)

    return swift_cloud_filter
