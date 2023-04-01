import hashlib
import secrets
import requests
import base64
import flask
from flask import flash, Blueprint, render_template, redirect, request, session, url_for
import flask_login
from flask_login import (LoginManager, current_user, logout_user,)
import json
from flask import current_app

from src.okta.user import OktaUser
from src.common.config import okta
from src.common.utils import get_db

okta_bp = Blueprint('okta_bp', __name__,
                    template_folder='./templates')

login_manager = LoginManager()

# With this, manual redirect if not authenticated should be removed, in theory
# login_manager.login_view = "okta_bp.login"


@okta_bp.record_once
def on_load(state):
    login_manager.init_app(state.app)


@login_manager.user_loader
def load_user(user_id):
    return OktaUser.get(user_id)


@login_manager.unauthorized_handler
def unauthorized_callback():
    if not current_user.is_authenticated:
        if request.endpoint == "public_bp.kb" and not current_user.is_authenticated:
            print("post-login doc is " + request.path)
            flash(request.path, 'wanted')
        return render_template('index.html', next=request.endpoint), 401


@okta_bp.before_request
def check_valid_login():
    # save wanted url if not authenticated
    if request.endpoint == "public_bp.kb" and not current_user.is_authenticated:
        print("post-login doc is " + request.path)
        flash(request.path, 'wanted')

    # endpoints used for authentication
    endpoint_group = ('static', 'okta_bp.login', 'okta_bp.callback')
    if request.endpoint not in endpoint_group and not current_user.is_authenticated:
        return render_template('index.html', next=request.endpoint)


@okta_bp.route("/login")
def login():
    # store app state and code verifier in session
    session['app_state'] = secrets.token_urlsafe(64)
    session['code_verifier'] = secrets.token_urlsafe(64)
    session.permanent = True

    # calculate code challenge
    hashed = hashlib.sha256(session['code_verifier'].encode('ascii')).digest()
    encoded = base64.urlsafe_b64encode(hashed)
    code_challenge = encoded.decode('ascii').strip('=')

    # get request params
    query_params = {'client_id': okta["client_id"],
                    'redirect_uri': okta["redirect_uri"],
                    'scope': "openid email profile",
                    'state': session['app_state'],
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'S256',
                    'response_type': 'code',
                    'response_mode': 'query'}

    # build request_uri
    request_uri = "{base_url}?{query_params}".format(
        base_url=okta["auth_uri"],
        query_params=requests.compat.urlencode(query_params)
    )

    return redirect(request_uri)


@okta_bp.errorhandler(404)
def page_not_found(error):
    return redirect(url_for('main_bp.index'))


@okta_bp.route("/authorization-code/callback")
def callback():
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    code = request.args.get("code")
    app_state = request.args.get("state")

    print("Session token has been read")

    try:
        if app_state != session['app_state']:
            return "The app state does not match"
        if not code:
            return "The code was not returned or is not accessible", 403
    except KeyError:
        print("KeyError error: app_state missing")
        return redirect(url_for('main_bp.index'))

    query_params = {'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': okta["redirect_uri"],
                    'code_verifier': session['code_verifier'],
                    }
    query_params = requests.compat.urlencode(query_params)
    exchange = requests.post(
        okta["token_uri"],
        headers=headers,
        data=query_params,
        auth=(okta["client_id"], okta["client_secret"]),
    ).json()

    # Get tokens and validate
    if not exchange.get("token_type"):
        current_app.logger.error('Unsupported token type, exchange is ' + json.dumps(exchange))
        return "Unsupported token type. Should be 'Bearer'.", 403
    access_token = exchange["access_token"]

    # Authorization flow successful, get userinfo and login user
    userinfo_response = requests.get(okta["userinfo_uri"],
                                     headers={'Authorization': f'Bearer {access_token}'}).json()

    unique_id = userinfo_response["sub"]
    user_email = userinfo_response["email"]
    user_given_name = userinfo_response["given_name"]
    user_name = userinfo_response["name"]

    user = None
    if not OktaUser.exists(unique_id):
        # default user is a viewer
        user = OktaUser.create(unique_id, user_given_name, user_name, user_email)
    else:
        user = OktaUser.update(unique_id, user_given_name, user_name, user_email)

    # Now create the session
    flask_login.login_user(user)

    # Log the event
    current_app.logger.info('User logged in successfully: {}'.format(current_user.id))

    # Store authentications in a time series
    get_db().ts().add("keybase:authentications", "*", 1, duplicate_policy='first')

    # Check desired url
    wanted = flask.get_flashed_messages(category_filter=["wanted"])
    if len(wanted):
        return redirect(wanted[0])

    return redirect(url_for("document_bp.browse"))


@okta_bp.route("/logout", methods=["GET", "POST"])
def logout():
    current_app.logger.info('User logged out: {}'.format(current_user.id))
    logout_user()
    return redirect(url_for('public_bp.landing'))


def getusergroups(unique_id):
    # Get groups
    # https://developer.okta.com/docs/guides/create-an-api-token/main/
    # Tokens are valid for 30 days from creation or last use
    api_token = okta["api_token"]
    usergroups_response = requests.get(okta["groups_uri"].format(unique_id),
                                       headers={'Accept': 'application/json',
                                                'Content-Type': 'application/json',
                                                'Authorization': f'SSWS {api_token}'}).json()

    print(usergroups_response)
