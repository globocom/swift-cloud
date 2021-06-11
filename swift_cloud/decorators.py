import functools


def cors_validation(func):
    """
    Decorator to check if the request is a CORS request and if so, if it's
    valid.

    :param func: function to check
    """
    @functools.wraps(func)
    def wrapped(*a, **kw):
        controller = a[0]
        req = a[1]

        # The logic here was interpreted from
        #    http://www.w3.org/TR/cors/#resource-requests

        # Is this a CORS request?
        req_origin = req.headers.get('Origin', None)
        if req_origin:
            # Yes, this is a CORS request so test if the origin is allowed
            try:
                bucket = controller.client.get_bucket(controller.account)
            except Exception as err:
                return controller._error_response(err)

            blob = bucket.get_blob(controller.container + '/')

            if not blob:
                return controller._default_response('', 404)

            metadata = blob.metadata or {}
            allow_origin = metadata.get('meta-access-control-allow-origin') or ''
            cors_info = allow_origin.split(' ')

            # Call through to the decorated method
            new = a + (bucket, blob,)
            resp = func(*new, **kw)

            if '*' not in cors_info:
                if req_origin not in cors_info:
                    return resp

            # Expose,
            #  - simple response headers,
            #    http://www.w3.org/TR/cors/#simple-response-header
            #  - swift specific: etag, x-timestamp, x-trans-id
            #  - headers provided by the operator in cors_expose_headers
            #  - user metadata headers
            #  - headers provided by the user in
            #    x-container-meta-access-control-expose-headers
            if 'Access-Control-Expose-Headers' not in resp.headers:
                expose_headers = set([
                    'cache-control', 'content-language', 'content-type',
                    'expires', 'last-modified', 'pragma', 'etag',
                    'x-timestamp', 'x-trans-id', 'x-openstack-request-id'])

                for header in resp.headers:
                    if header.startswith('X-Container-Meta') or \
                            header.startswith('X-Object-Meta'):
                        expose_headers.add(header.lower())

                if req.headers.get('expose_headers'):
                    expose_headers = expose_headers.union(
                        [header_line.strip().lower()
                            for header_line in
                            cors_info['expose_headers'].split(' ')
                            if header_line.strip()])
                resp.headers['Access-Control-Expose-Headers'] = \
                    ', '.join(expose_headers)

            # The user agent won't process the response if the Allow-Origin
            # header isn't included
            if 'Access-Control-Allow-Origin' not in resp.headers:
                if '*' in cors_info:
                    resp.headers['Access-Control-Allow-Origin'] = '*'
                else:
                    resp.headers['Access-Control-Allow-Origin'] = req_origin

            return resp
        else:
            # Not a CORS request so make the call as normal
            return func(*a, **kw)

    return wrapped
