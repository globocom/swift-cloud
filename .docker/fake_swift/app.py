import json
import routes
import webob
import webob.dec
import webob.exc


class App(object):

    map = routes.Mapper()
    map.connect('info', '/info', method='info', conditions=dict(method=['GET']))
    map.connect('post_account', '/v1/{account}', method='post_account', conditions=dict(method=['POST']))
    map.connect('get_account', '/v1/{account}', method='get_account', conditions=dict(method=['GET']))
    map.connect('get_container', '/v1/{account}/{container}', method='get_container', conditions=dict(method=['GET']))
    map.connect('get_object', '/v1/{account}/{container}/{obj}', method='get_object', conditions=dict(method=['GET']))

    @webob.dec.wsgify
    def __call__(self, req):
        results = self.map.routematch(environ=req.environ)
        if not results:
            return webob.exc.HTTPNotFound()
        match, route = results
        link = routes.URLGenerator(self.map, req.environ)
        req.urlvars = ((), match)
        kwargs = match.copy()
        method = kwargs.pop('method')
        req.link = link
        return getattr(self, method)(req, **kwargs)

    def info(self, req):
        body = json.dumps({'fake_swift': {'version': '0.0.1'}})
        return webob.Response(body=body, content_type='application/json')

    def get_account(self, req, account=None):
        resp = webob.Response(body=json.dumps([]), content_type='application/json')
        resp.headers.update({
            'X-Account-Bytes-Used': '0',
            'X-Account-Container-Count': '0',
            'X-Account-Object-Count': '0',
            'Accept-Ranges': 'bytes',
            'X-Timestamp': '1616116845',
            'X-Account-Meta-Cloud': 'gcp',
            'X-Account-Meta-Temp-Url-Key': 'secret'
        })
        return resp

    def post_account(self, req, account=None):
        resp = webob.Response()
        resp.status = 204
        resp.headers.update({
            'Content-Type': 'text/html; charset=utf-8',
            'X-Timestamp': '1616116845'
        })
        return resp

    def get_container(self, req, account=None, container=None):
        resp = webob.Response(body=json.dumps([]), content_type='application/json')
        resp.headers.update({
            'X-Container-Bytes-Used': '0',
            'X-Container-Object-Count': '0',
            'Accept-Ranges': 'bytes',
            'X-Timestamp': '1616116845'
        })
        return resp

    def get_object(self, req, account=None, container=None, obj=None):
        resp = webob.Response(body='')
        resp.headers.update({
            'Content-Length': '0',
            'Content-Type': 'text/plain',
            'Accept-Ranges': 'bytes',
            'X-Timestamp': '1616116845'
        })
        return resp


def app_factory(global_config, **local_conf):
    return App()
