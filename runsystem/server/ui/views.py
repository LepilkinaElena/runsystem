import datetime
import os
import re
import tempfile
import time
import copy
import json
import itertools

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
connected_run = None
current_run = None
closest_runs = []
@frontend.route('/favicon.ico')
def favicon_ico():
    return redirect(url_for('.static', filename='favicon.ico'))

@frontend.route('/')
def index():
    db.init_database()
    runs = db.Run.search().execute()
    return render_template("index.html", runs=runs)

class CompareRequestInfo(object):
    def __init__(self, run):
        self.current_run = run
        self.connected_run = None
        self.compared_loop = None
        if self.current_run.connected_run_id:
            self.connected_run = db.Run.get(id=self.current_run.connected_run_id, ignore=404)
        # Find closest runs.
        s = db.Run.search().query('more_like_this', fields=['options'], 
                                  like=self.current_run.options, min_term_freq=1,
                                  min_doc_freq=1, max_query_terms=2)
        self.closest_runs = s.execute()
        self.closest_runs = self.closest_runs [0:3]
        self.compare_to = None
        compare_to_id = request.args.get('compare_to')
        if compare_to_id:
            self.compare_to = db.Run.get(id=compare_to_id)
        compared_loop = request.args.get('compared_loop')
        if compared_loop:
            self.compared_loop = db.Loop.get(id=compared_loop)

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

    request_info = CompareRequestInfo(run)
    compare_to_applications = {}
    if request_info.compare_to:
        s = db.ApplicationSearch(run_id=request_info.compare_to.meta.id)
        response = s.execute()
        for (application_name, _, _) in response.facets.tags:
            compare_to_applications[application_name] = []
            s = db.FilenameSearch(application=application_name)
            filenames_response = s.execute()
            for (filename, _, _) in filenames_response.facets.tags:
                compare_to_applications[application_name].append(filename)
    
    return render_template("run.html", run=run, applications=applications, 
                                       request_info=request_info,
                                       compare_to_applications=compare_to_applications)

@frontend.route("/program/<name>/<id>")
def program(name, id):
    run = db.Run.get(id=id)
    request_info = CompareRequestInfo(run)
    s = db.Function.search().query('match', run_id=id).query('match', application=name)
    s = s[0:10000]
    functions = s.execute()
    compare_to_functions = []
    if request_info.compare_to:
        s = db.Function.search().\
                               query('match', run_id=request_info.compare_to.meta.id).\
                               query('match', application=name).source(['function_name'])
        s = s[0:10000]
        compared_functions = s.execute()
        compare_to_functions = [o.function_name for o in compared_functions]
    
    return render_template("program.html", program=name, functions=functions,
                                           request_info=request_info, 
                                           compare_to_functions=compare_to_functions)

def get_compare_to_loops(request_info, function):
    compare_to_loops = {}
    if request_info.compare_to:
        s = db.Function.search().\
                               query('match', run_id=request_info.compare_to.meta.id).\
                               query('match', function_name=function.function_name).\
                               query('match', application=function.application).\
                               query('match', filename=function.filename)
        response = s.execute()
        if response.success() and len(response):
            compare_to_function = response[0]
            s = db.Loop.search().query('match', function_id=compare_to_function.meta.id)
            s = s[0:10000]
            response_loops = s.execute()
            for loop in response_loops:
                compare_to_loops[loop.loop_id] = loop 
    return compare_to_loops

@frontend.route("/function/<id>")
def function(id):
    function = db.Function.get(id=id)
    s = db.Loop.search().query('match', function_id=id)
    s = s[0:10000]
    loops = s.execute()

    run = db.Run.get(id=function.run_id)
    request_info = CompareRequestInfo(run)

    compare_to_loops = get_compare_to_loops(request_info, function)
    return render_template("function.html", function=function, loops=loops,
                                            request_info=request_info, 
                                            compare_to_loops=compare_to_loops)

def get_loop_features_set(loop):
    # Find loop features.
    s = db.LoopFeatures.search().query('match', block_id=loop.meta.id).sort('order')
    s = s[0:10000]
    loop_features = s.execute()

    features_sets = {}
    features_sets['Before'] = []
    features_sets['After'] = []
    previous_place = 'After'
    for features in loop_features:
        features_set = db.Features.get(id=features.features_id, ignore=404)
        if features_set:
            if features_set.place == previous_place:
                del features_sets[features_set.place][-1]
            features_sets[features_set.place].append(features_set)
            previous_place = features_set.place
    result_features = zip(features_sets['Before'], features_sets['After'])
    return result_features

@frontend.route("/loop/<id>")
def loop(id):
    loop = db.Loop.get(id=id)
    function = db.Function.get(id=loop.function_id)
    run = db.Run.get(id=function.run_id)
    request_info = CompareRequestInfo(run)
    runs_features_sets = []
    # Find loop features.
    result_features = get_loop_features_set(loop)
   
    if request_info.compare_to:
        if not request_info.compared_loop:
            # Find same loop.
            
            s = db.Function.search().\
                                   query('match', run_id=request_info.compare_to.meta.id).\
                                   query('match', function_name=function.function_name).\
                                   query('match', application=function.application).\
                                   query('match', filename=function.filename)
            response = s.execute()
            if response.success() and len(response):
                compare_to_function = response[0]
                s = db.Loop.search().query('match', function_id=compare_to_function.meta.id).\
                                     query('match', loop_id=loop.loop_id)
                                                    
                response_loops = s.execute()
                if len(response_loops) == 1:
                    request_info.compared_loop = response_loops[0]
        compared_loop_features = get_loop_features_set(request_info.compared_loop)
        runs_features_sets = itertools.izip_longest(result_features, compared_loop_features)
    return render_template("loop.html", loop=loop, 
                           features_sets=result_features,
                           request_info=request_info,
                           runs_features_sets=runs_features_sets)

@frontend.route("/graph/<loop_id>/<run_id>")
def graph(loop_id, run_id):
    loop = db.Loop.get(id=loop_id)
    return render_template("graph.html", loop=loop)

@frontend.route("/loop_graph/<function_id>")
def loop_graph(function_id):
    function = db.Function.get(id=function_id)
    s = db.Loop.search().query('match', function_id=function_id)
    s = s[0:10000]
    loops = s.execute()

    run = db.Run.get(id=function.run_id)
    request_info = CompareRequestInfo(run)

    compare_to_loops = get_compare_to_loops(request_info, function)

    codesize_data = []
    exec_data = []
    llc_misses_data = []

    compare_codesize_data = []
    compare_exec_data = []
    compare_llc_misses_data = []

    loop_names = []
    for x, cur_loop in zip(range(0, len(loops)), loops):
        codesize_data.append((x, cur_loop.code_size))
        exec_data.append((x, cur_loop.exec_time))
        llc_misses_data.append((x, cur_loop.llc_misses))
        loop_names.append([x, cur_loop.loop_id])
        if cur_loop.loop_id in compare_to_loops:
            compare_codesize_data.append((x, compare_to_loops[cur_loop.loop_id].code_size))
            compare_exec_data.append((x, compare_to_loops[cur_loop.loop_id].exec_time))
            compare_llc_misses_data.append((x, compare_to_loops[cur_loop.loop_id].llc_misses))
    codesize_results = [{'label':run.options, 'data':codesize_data}]
    exec_time_results = [{'label':run.options, 'data':exec_data}]
    llc_misses_results = [{'label':run.options, 'data':llc_misses_data}]
    if request_info.compare_to:
        codesize_results.append({'label':request_info.compare_to.options, 'data':compare_codesize_data})
        exec_time_results.append({'label':request_info.compare_to.options, 'data':compare_exec_data})
        llc_misses_results.append({'label':request_info.compare_to.options, 'data':compare_llc_misses_data})
    return render_template("graph.html", codesize_results=codesize_results, loop_names=loop_names,
                            exec_time_results=exec_time_results, llc_misses_results=llc_misses_results,
                            function=function)