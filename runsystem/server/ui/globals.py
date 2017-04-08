"""
Module for defining additional Jinja global functions.
"""

import flask
from werkzeug.urls import url_encode

def url_for(*args, **kwargs):
    """
    Like url_for, but handles automatically providing the db_name and
    testsuite_name arguments.
    """
    return flask.url_for(*args, **kwargs)

def add_compare_to(compare_to_id):
    args = flask.request.args.copy()
    args['compare_to'] = compare_to_id

    return '{}?{}'.format(flask.request.path, url_encode(args)) 

def register(env):
    # Add some normal Python builtins which can be useful in templates.
    env.globals.update(zip=zip)

    # Add our custom global functions.
    env.globals.update(
        add_compare_to=add_compare_to)