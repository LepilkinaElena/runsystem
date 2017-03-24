import datetime
import os
import re
import tempfile
import time
import copy
import json

import flask
from flask import abort
from flask import current_app
from flask import g
from flask import make_response
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask import flash

from runsystem.server.ui.decorators import frontend
import runsystem.db.data as db

from flask_wtf import Form
from wtforms import SelectField

from collections import namedtuple, defaultdict

###
# Root-Only Routes

@frontend.route('/favicon.ico')
def favicon_ico():
    return redirect(url_for('.static', filename='favicon.ico'))

@frontend.route('/')
def index():
    db.init_database()
    runs = db.Run.search().execute()
    return render_template("index.html", runs=runs)

@frontend.route("/run/<id>")
def run(id):
    run = db.Run.get(id=id)
    s = db.ApplicationSearch(run_id=id)
    response = s.execute()
    applications = {}
    for (application_name, _, _) in response.facets.tags:
        applications[application_name] = []
        s = db.FilenameSearch(application=application_name)
        filenames_response = s.execute()
        for (filename, _, _) in filenames_response.facets.tags:
            applications[application_name].append(filename)
    return render_template("run.html", run=run, applications=applications)

@frontend.route("/program/<name>/<id>")
def program(name, id):
    s = db.Function.search().query('match', run_id=id).query('match', application=name)
    s = s[0:10000]
    functions = s.execute()
    return render_template("program.html", program=name, functions=functions)

@frontend.route("/function/<id>")
def function(id):
    function = db.Function.get(id=id)
    s = db.Loop.search().query('match', function_id=id)
    s = s[0:10000]
    loops = s.execute()
    return render_template("function.html", function=function, loops=loops)

@frontend.route("/loop/<id>")
def loop(id):
    loop = db.Loop.get(id=id)
    s = db.LoopFeatures.search().query('match', block_id=id)
    s = s[0:10000]
    loop_features = s.execute()
    features_sets = {}
    features_sets['Before'] = []
    features_sets['After'] = []
    for features in loop_features:
        features_set = db.Features.get(id=features.features_id, ignore=404)
        if features_set:
            features_sets[features_set.place].append(features_set)
    print(features_sets)
    return render_template("loop.html", loop=loop, 
                           features_sets=zip(features_sets['Before'], features_sets['After']))