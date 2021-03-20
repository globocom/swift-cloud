from webob import Response
from google.cloud import storage


class SwiftGCPClient:

    def __init__(self, request):
        self.request = request

    def response(self):
        return Response(request=self.request,
                        body='SwiftGCPClient',
                        content_type='text/plain')
