from flask import Flask


def create_app():

    app = Flask(__name__)

    @app.route('/v1/AUTH_<project_id>')
    def account(project_id):
        return { 'id': project_id }

    return app


def app_factory(global_config, **local_conf):
    return create_app()
