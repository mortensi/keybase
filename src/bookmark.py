from flask import Blueprint, render_template, redirect, url_for
from flask import request
from flask import flash, session
from flask import current_app
import redis
from redis import RedisError
from . import config
from datetime import datetime
import time
import hashlib
import json
from flask import Flask, Blueprint, render_template, redirect, url_for, request, jsonify, session
from flask_login import (LoginManager,current_user,login_required,login_user,logout_user,)
from user import requires_access_level, Role
from config import get_db
from utils import pretty_title

bookmrk = Blueprint('bookmrk', __name__)

@bookmrk.route('/bookmark', methods=['POST'])
@login_required
def bookmark():
    #TODO check that the document exists
    bookmarked = get_db().hexists("keybase:bookmark:{}".format(current_user.id), request.form['docid'])
    if (not bookmarked):
        get_db().hmset("keybase:bookmark:{}".format(current_user.id), {request.form['docid'] : ""})
        return jsonify(message="Bookmark created", hasbookmark=1)
    else:
        get_db().hdel("keybase:bookmark:{}".format(current_user.id), request.form['docid'])
        return jsonify(message="Bookmark removed", hasbookmark=0)


@bookmrk.route('/bookmarks')
@login_required
def bookmarks():
    docs = []
    names = []
    creations = []
    pretty = []
    bookmarks = None
    cursor=0

    while True:
        cursor, keys  = get_db().hscan("keybase:bookmark:{}".format(current_user.id), cursor, count=20)
        for key in keys:
            hash = get_db().hmget("keybase:kb:{}".format(key), ['name', 'creation'])
            docs.append(key)
            names.append(hash[0])
            pretty.append(pretty_title(hash[0]))
            creations.append(datetime.utcfromtimestamp(int(hash[1])).strftime('%Y-%m-%d %H:%M:%S'))
        if (cursor==0):
            break
    
    if len(docs):
        bookmarks=zip(docs,names,pretty,creations)
    return render_template("bookmark.html", bookmarks=bookmarks)