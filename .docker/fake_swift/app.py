from flask import Flask, jsonify, make_response


def create_app():

    app = Flask(__name__)

    @app.route('/info')
    def info():
        resp = make_response(jsonify({
            'fake_swift': {
                'version': '0.0.1'
            }
        }))

        return resp

    @app.route('/v1/<account>')
    def get_account(account):
        resp = make_response(jsonify([]))

        resp.headers.update({
            'X-Account-Bytes-Used': 0,
            'X-Account-Container-Count': 0,
            'X-Account-Object-Count': 0,
            'Accept-Ranges': 'bytes',
            'X-Timestamp': '1616116845',
            'X-Account-Meta-Cloud': 'gcp',
            'X-Account-Meta-Temp-Url-Key': 'secret'
        })

        return resp

    @app.route('/v1/<account>', methods=['POST'])
    def post_account(account):
        resp = make_response()
        resp.status_code = 204
        resp.headers.update({
            'Content-Type': 'text/html; charset=utf-8',
            'X-Timestamp': '1616116845'
        })

        return resp

    @app.route('/v1/<account>/<container>')
    def get_container(account, container):
        resp = make_response(jsonify([]))

        resp.headers.update({
            'X-Container-Bytes-Used': 0,
            'X-Container-Object-Count': 0,
            'Accept-Ranges': 'bytes',
            'X-Timestamp': '1616116845'
        })

        return resp

    @app.route('/v1/<account>/<container>/<obj>')
    def get_object(account, container, obj):
        resp = make_response('')

        resp.headers.update({
            'Content-Length': 0,
            'Content-Type': 'text/plain',
            'Accept-Ranges': 'bytes',
            'X-Timestamp': '1616116845'
        })

        return resp

    return app


def app_factory(global_config, **local_conf):
    return create_app()
