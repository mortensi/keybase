from flask import Blueprint
from flask import Blueprint, render_template, redirect, url_for
from flask import request
from flask import flash
from flask import current_app
import redis
from redis import RedisError
from . import config
import time
from flask_simplelogin import is_logged_in

auth = Blueprint('auth', __name__)

# Database Connection
host = config.REDIS_CFG["host"]
port = config.REDIS_CFG["port"]
pwd = config.REDIS_CFG["password"]
pool = redis.ConnectionPool(host=host, port=port, db=0, decode_responses=True)
conn = redis.Redis(connection_pool=pool)

@auth.route('/login')
def login():
    if is_logged_in():
        return redirect(url_for('app.browse'))
    else:
        return render_template('login.html')
    #return redirect(url_for('main.profile'))

@auth.route('/login', methods=['POST'])
def login_post():
    if is_logged_in():
        return redirect(url_for('app.browse'))

    username = request.form.get('username')
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    psw = conn.hget("keybase:user:{}".format(id), "password")

    if (psw == Null):
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login')) # if the user doesn't exist or password is wrong, reload the page
    elif (password != psw):
        flash('Please check your password.')
        return redirect(url_for('auth.login')) # if the user doesn't exist or password is wrong, reload the page

    # if the above check passes, then we know the user has the right credentials
    session['logged'] = true
    session['username'] = request.form.get('username')
    return redirect(url_for('main.profile'))

@auth.route('/signup')
def signup():
    if is_logged_in():
        return redirect(url_for('app.browse'))
    else:
        return render_template('signup.html')

@auth.route('/signup', methods=['POST'])
def signup_post():
    if is_logged_in():
        return redirect(url_for('app.browse'))

    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')

    # Check mail, username and password
    # ...

    # Check username does not exist
    user = conn.hgetall("keybase:user:{}".format(name))
    if (user):
        flash('Username already exists')
        return redirect(url_for('auth.signup'))

    # Check username does not exist
    mail = conn.zrank("mails", email)
    if (mail == 0):
        flash('Email already exists')
        return redirect(url_for('auth.signup'))

    # Now add the user, lowercase
    pipeline = conn.pipeline(True)
    pipeline.hmset("keybase:user:{}".format(name.lower()), {
        'mail': email,
        'password': password,
        'signup': time.time()})
    pipeline.zadd("mails", {email: 0})
    pipeline.execute()

    return redirect(url_for('auth.login'))

@auth.route('/logout')
def logout():
    return 'Logout'