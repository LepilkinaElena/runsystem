import sys
import jinja2
import logging
import logging.handlers
from logging import Formatter
import os
import time
import StringIO
import traceback

import flask
from flask import current_app
from flask import request
from flask import g
from flask import url_for
from flask import Flask
from flask_restful import Resource, Api

import runsystem.server.instance
import runsystem.server.ui.views
from runsystem.server.ui.api import load_api_resources

class RootSlashPatchMiddleware(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'] == '':
            return flask.redirect(environ['SCRIPT_NAME'] + '/')(
                environ, start_response)
        return self.app(environ, start_response)

class Request(flask.Request):
    def __init__(self, *args, **kwargs):
        super(Request, self).__init__(*args, **kwargs)

        self.request_time = time.time()

    def elapsed_time(self):
        return time.time() - self.request_time

    def close(self):
        t = self.elapsed_time()
        if t > 10:
            warning("Request {} took {}s".format(self.url, t))
        db = getattr(self, 'db', None)
        if db is not None:
            db.close()
        return super(Request, self).close()


class ExceptionLoggerFlask(flask.Flask):
        def log_exception(self, exc_info):
            # We need to stringify the traceback, since logs are sent via
            # pickle.
            print("Exception: " + traceback.format_exc())
            

class App(ExceptionLoggerFlask):
    @staticmethod
    def create_with_instance(instance):
        # Construct the application.
        app = App(__name__)

        # Register additional filters.
        create_jinja_environment(app.jinja_env)

        # Set up strict undefined mode for templates.
        app.jinja_env.undefined = jinja2.StrictUndefined

        # Load the application configuration.
        app.load_config(instance)

        # Load the application routes.
        app.register_module(runsystem.server.ui.views.frontend)

        # Load the flaskRESTful API.
        app.api = Api(app)
        load_api_resources(app.api)

        return app

    @staticmethod
    def create_standalone(config_path):
        instance = runsystem.server.instance.Instance.frompath(config_path)
        app =  App.create_with_instance(instance)
        app.start_file_logging()
        return app
    
    def __init__(self, name):
        super(App, self).__init__(name)
        self.start_time = time.time()
        # Override the request class.
        self.request_class = Request

        # Store a few global things we want available to templates.
        self.version = runsystem.__version__

        # Inject a fix for missing slashes on the root URL (see Flask issue
        # #169).
        self.wsgi_app = RootSlashPatchMiddleware(self.wsgi_app)
        self.logger.setLevel(logging.DEBUG)

        
    def load_config(self, instance):
        self.instance = instance
        self.old_config = self.instance.config

        self.jinja_env.globals.update(
            app=current_app,
            old_config=self.old_config)

    def start_file_logging(self):
        """Start server production logging.  At this point flask already logs
        to stderr, so just log to a file as well.

        """
        # Print to screen.
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        self.logger.addHandler(ch)
        
        # Log to mem for the /log view.
        h = logging.handlers.MemoryHandler(1024 * 1024, flushLevel=logging.CRITICAL)
        h.setLevel(logging.DEBUG)
        self.logger.addHandler(h)
        # Also store the logger, so we can render the buffer in it.
        self.config['mem_logger'] = h
        
        if not self.debug:
            LOG_FILENAME = "runsystem.log"
            try:    
                rotating = logging.handlers.RotatingFileHandler(
                    LOG_FILENAME, maxBytes=1048576, backupCount=5)
                rotating.setFormatter(Formatter(
                    '%(asctime)s %(levelname)s: %(message)s '
                    '[in %(pathname)s:%(lineno)d]'
                ))
                rotating.setLevel(logging.DEBUG)
                self.logger.addHandler(rotating)                
            except (OSError, IOError) as e:
                print >> sys.stderr, "Error making log file", LOG_FILENAME, str(e)
                print >> sys.stderr, "Will not log to file."
            else:
                self.logger.info("Started file logging.")
                print "Logging to :", LOG_FILENAME
            

def create_jinja_environment(env=None):
    """
    create_jinja_environment([env]) -> jinja2.Environment

    Create (or modify) a new Jinja2 environment suitable for rendering the LNT
    templates.
    """

    if env is None:
        env = jinja2.Environment(loader=jinja2.PackageLoader(
                'runsystem.server.ui', 'templates'))

    return env
