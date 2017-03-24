"""
Module for defining additional Jinja global functions.
"""

import flask

def url_for(*args, **kwargs):
    """
    Like url_for, but handles automatically providing the db_name and
    testsuite_name arguments.
    """
    return flask.url_for(*args, **kwargs)
