from webob import Request, Response


class SwiftGCPMiddleware(object):
    """
    Swift GCP Middleware

    Middleware for Openstack Swift to store objecs on Google Cloud Storage.
    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf

    def __call__(self, environ, start_response):
        req = Request(environ)

        if 'X-Object-GCP' in environ:
            return self.swift_gcp_response(req)(environ, start_response)

        return self.app(environ, start_response)

    def swift_gcp_response(self, req):
        return Response(request=req,
                        body='',
                        content_type="text/plain")


def filter_factory(global_conf, **local_conf):
    """
    WSGI filtered app for paste.deploy.
    """

    conf = global_conf.copy()
    conf.update(local_conf)

    def swift_gcp_filter(app):
        return SwiftGCPMiddleware(app, conf)

    return swift_gcp_filter
