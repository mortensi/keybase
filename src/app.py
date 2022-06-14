from redis.commands.search.field import VectorField
from redis.commands.search.query import Query
from redis import RedisError
import numpy as np
import uuid
import urllib.parse
from datetime import datetime
import time
from . import config
import threading
import flask
from flask import Response, stream_with_context
from flask import Flask, Blueprint, render_template, redirect, url_for, request, jsonify, session
from flask_login import (LoginManager,current_user,login_required,login_user,logout_user,)
from sentence_transformers import SentenceTransformer
from user import requires_access_level, Role
from config import get_db


app = Blueprint('app', __name__)

# Helpers
def isempty(input):
	result = False

	# An argument is considered to be empty if any of the following condition matches
	if str(input) == "None":
		result = True
	
	if str(input) == "":
		result = True
	
	return result

@app.route('/autocomplete', methods=['GET'])
@login_required
def autocomplete():
    rs = get_db().ft("document_idx").search(Query(urllib.parse.unquote(request.args.get('q'))).return_field("name").sort_by("creation", asc=False).paging(0, 10))
    results = []

    for doc in rs.docs:
        results.append({'value': urllib.parse.unquote(doc.name),
                        'label': urllib.parse.unquote(doc.name), 
                        'id': doc.id.split(':')[-1]})

    return jsonify(matching_results=results)


def bg_embedding_vector(key):
    content = get_db().hget("keybase:kb:{}".format(key), "content")
    print("Computing vector embedding for " + key)
    model = SentenceTransformer('sentence-transformers/all-distilroberta-v1')
    embedding = model.encode(content).astype(np.float32).tobytes()
    get_db().hset("keybase:kb:{}".format(key), "content_embedding", embedding)
    print("Done vector embedding for " + key)


@app.route('/browse', methods=['GET'])
@login_required
def browse():
    TITLE="List documents"
    DESC="Listing documents"
    keys = []
    names = []
    creations = []
    keydocument = None

    # Clear all the flashed messages
    flask.get_flashed_messages()

    try:
        if (request.args.get('q')):
            rs = get_db().ft("document_idx").search(Query(request.args.get('q')).return_field("name").return_field("creation").sort_by("creation", asc=False).paging(0, 10))
        else:
            rs = get_db().ft("document_idx").search(Query("*").return_field("name").return_field("creation").sort_by("creation", asc=False).paging(0, 10))
        
        if len(rs.docs): 
            for key in rs.docs:
                keys.append(key.id.split(':')[-1])
                names.append(urllib.parse.unquote(key.name))
                creations.append(datetime.utcfromtimestamp(int(key.creation)).strftime('%Y-%m-%d %H:%M:%S'))
            keydocument=zip(keys,names,creations)
        return render_template('browse.html', title=TITLE, desc=DESC, keydocument=keydocument)
    except RedisError as err:
        print(err)
        return render_template('browse.html', title=TITLE, desc=DESC, error=err)

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return render_template('index.html')
    else:
        return redirect(url_for('app.browse'))


@app.route('/save', methods=['POST'])
@login_required
@requires_access_level(Role.EDITOR)
def save():
    TITLE="Read Document"
    DESC="Read Document"
    id = uuid.uuid1()
    unixtime = int(time.time())
    timestring = datetime.utcnow().strftime("%m/%d/%Y, %H:%M:%S")

    doc = {"content":urllib.parse.unquote(request.form['content']), 
            "name":urllib.parse.unquote(request.form['name']),
            "creation":unixtime,
            "processable":1,
            "update":unixtime}
    get_db().hmset("keybase:kb:{}".format(id), doc)

    # Update the vector embedding in the background
    #sscanThread = threading.Thread(target=bg_embedding_vector, args=(str(id),)) 
    #sscanThread.daemon = True
    #sscanThread.start()

    return jsonify(message="Document created", id=id)
    
@app.route('/bookmark', methods=['POST'])
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


@app.route('/bookmarks')
@login_required
def bookmarks():
    docs = []
    names = []
    creations = []
    bookmarks = None
    cursor=0

    while True:
        cursor, keys  = get_db().hscan("keybase:bookmark:{}".format(current_user.id), cursor, count=20)
        for key in keys:
            hash = get_db().hmget("keybase:kb:{}".format(key), ['name', 'creation'])
            docs.append(key)
            names.append(hash[0])
            creations.append(datetime.utcfromtimestamp(int(hash[1])).strftime('%Y-%m-%d %H:%M:%S'))
        if (cursor==0):
            break
    
    if len(docs):
        bookmarks=zip(docs,names,creations)
    return render_template("bookmark.html", bookmarks=bookmarks)


@app.route('/update', methods=['POST'])
@login_required
@requires_access_level(Role.EDITOR)
def update():
    # Make sure the request.args.get('id') exists, otherwise do not update
    unixtime = int(time.time())

    doc = { "content":urllib.parse.unquote(request.form['content']),
            "name":urllib.parse.unquote(request.form['name']),
            "processable":1,
            "update": unixtime}
    get_db().hmset("keybase:kb:{}".format(request.form['id']), doc)

    # Update the vector embedding in the background
    #sscanThread = threading.Thread(target=bg_embedding_vector, args=(request.args.get('id'),)) 
    #sscanThread.daemon = True
    #sscanThread.start()

    return jsonify(message="Document updated")

@app.route('/about', methods=['GET'])
@login_required
def about():
    TITLE="About keybase"
    DESC="About keybase"
    return render_template('about.html', title=TITLE, desc=DESC)

@app.route('/edit', methods=['GET'])
@login_required
@requires_access_level(Role.EDITOR)
def edit():
    id = request.args.get('id')
    TITLE="Read Document"
    DESC="Read Document"
    #if id is None:
    document = get_db().hmget("keybase:kb:{}".format(id), ['name', 'content'])
    document[0] = urllib.parse.quote(document[0])
    document[1] = urllib.parse.quote(document[1])
    return render_template('edit.html', title=TITLE, desc=DESC, id=id, name=document[0], content=document[1])

@app.route('/delete', methods=['GET'])
@login_required
@requires_access_level(Role.EDITOR)
def delete():
    id = request.args.get('id')
    get_db().delete("keybase:kb:{}".format(id))
    return redirect(url_for('app.browse'))

@app.route('/view', methods=['GET'])
@login_required
def view():
    id = request.args.get('id')
    TITLE="Read Document"
    DESC="Read Document"
    keys = []
    names = []
    suggestlist = None
    #if id is None:

    bookmarked = get_db().hexists("keybase:bookmark:{}".format(current_user.id), id)

    document = get_db().hmget("keybase:kb:{}".format(request.args.get('id')), ['name', 'content'])
    
    if document[0] == None:
        return redirect(url_for('app.browse'))
        
    document[0] = urllib.parse.quote(document[0])
    document[1] = urllib.parse.quote(document[1])

    # Fetch recommendations using LUA and avoid sending vector embeddings back an forth
    #luascript = conn.register_script("local vector = redis.call('hmget',KEYS[1], 'content_embedding') local searchres = redis.call('FT.SEARCH','document_idx','*=>[KNN 6 @content_embedding $B AS score]','PARAMS','2','B',vector[1], 'SORTBY', 'score', 'ASC', 'LIMIT', 1, 6,'RETURN',2,'score','name','DIALECT',2) return searchres")
    #pipe = conn.pipeline()
    #luascript(keys=["keybase:kb:{}".format(request.args.get('id'))], client=pipe)
    #r = pipe.execute()

    # The first element in the returned list is the number of keys returned, start iterator from [1:]
    # Then, iterate the results in pairs, because they key name is alternated with the returned fields
    #it = iter(r[0][1:])
    #for x in it:
    #    keys.append(str(x.split(':')[-1]))
    #    names.append(str(next(it)[3]))
        #print (x.split(':')[-1], next(it)[3])
    #suggestlist=zip(keys, names)

    # Fetch recommendations using LUA and avoid sending vector embeddings back an forth
    # The first element in the returned list is the number of keys returned, start iterator from [1:]
    # Then, iterate the results in pairs, because they key name is alternated with the returned fields

    if get_db().hexists("keybase:kb:{}".format(request.args.get('id')), 'content_embedding'):
        keys_and_args = ["keybase:kb:{}".format(request.args.get('id'))]
        res = get_db().eval("local vector = redis.call('hmget',KEYS[1], 'content_embedding') local searchres = redis.call('FT.SEARCH','document_idx','*=>[KNN 6 @content_embedding $B AS score]','PARAMS','2','B',vector[1], 'SORTBY', 'score', 'ASC', 'LIMIT', 1, 6,'RETURN',2,'score','name','DIALECT',2) return searchres", 1, *keys_and_args)
        it = iter(res[1:])
        for x in it:
            keys.append(str(x.split(':')[-1]))
            names.append(str(next(it)[3]))
            #print (x.split(':')[-1], next(it)[3])
        suggestlist=zip(keys, names)


    """
    # Fetching suggestions only if the vector embedding is available
    if (document[2] != None):
        q = Query("*=>[KNN 6 @content_embedding $vec]").sort_by("__content_embedding_score")
        res = conn.ft("document_idx").search(q, query_params={"vec": document[2]})
        for doc in res.docs:
            if (doc.id.split(':')[-1] == request.args.get('id')):
                continue
            suggestionid = doc.id.split(':')[-1]
            suggest = conn.hmget("keybase:kb:{}".format(suggestionid), ['name'])
            keys.append(suggestionid)
            names.append(suggest[0].decode('utf-8'))
        suggestlist=zip(keys, names)
    """
    return render_template('view.html', title=TITLE,id=request.args.get('id'), desc=DESC, docid=id, bookmarked=bookmarked, document=document, suggestlist=suggestlist)

@app.route('/new')
@login_required
@requires_access_level(Role.EDITOR)
def new():
    TITLE="New Document"
    DESC="New Document"
    return render_template('new.html', title=TITLE, desc=DESC)