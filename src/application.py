import secrets

from flask import Flask, render_template
from flask_cors import CORS
from datetime import datetime
from flask_breadcrumbs import Breadcrumbs
from werkzeug.exceptions import HTTPException
import redis
import logging
from src.common.utils import track_errors


def create_app():
    app = Flask(__name__, template_folder="templates")
    Breadcrumbs(app=app)
    app.config["SESSION_TYPE"] = "filesystem"
    app.config.update({'SECRET_KEY': secrets.token_hex(64)})
    app.url_map.strict_slashes = False
    CORS(app)

    @app.template_filter('ctime')
    def timectime(s):
        date_time = datetime.fromtimestamp(s)
        return date_time.strftime("%B %d %Y, %H:%M")

    from .main import main_bp
    app.register_blueprint(main_bp)

    from .api.routes import api_bp
    app.register_blueprint(api_bp)

    from .bookmarks.routes import bookmarks_bp
    app.register_blueprint(bookmarks_bp)

    from .drafts.routes import drafts_bp
    app.register_blueprint(drafts_bp)

    from .analytics.routes import analytics_bp
    app.register_blueprint(analytics_bp)

    from .admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    from .document.routes import document_bp
    app.register_blueprint(document_bp)

    from .version.routes import version_bp
    app.register_blueprint(version_bp)

    from .feedback.routes import feedback_bp
    app.register_blueprint(feedback_bp)

    from .public.routes import public_bp
    app.register_blueprint(public_bp)

    from .okta.routes import okta_bp
    app.register_blueprint(okta_bp)

    # from .auth.routes import auth_bp
    # app.register_blueprint(auth_bp)

    gunicorn_error_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers.extend(gunicorn_error_logger.handlers)
    app.logger.setLevel(logging.INFO)

    @app.errorhandler(Exception)
    def handle_exception(e):
        # database error
        if isinstance(e, redis.exceptions.ConnectionError):
            return render_template('61.html'), 500

        track_errors(e)
        # pass through HTTP errors
        if isinstance(e, HTTPException):
            return render_template('404.html'), 404

        # now you're handling non-HTTP exceptions only
        return render_template('500.html'), 500

    app.logger.info('Redis Knowledge Base started!')
    return app





