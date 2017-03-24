"""Implement the command line 'runsystem' tool."""
import logging
import os
import sys
import tempfile
import json
from optparse import OptionParser, OptionGroup
import contextlib
import runsystem.util.multitool
from runsystem.testrunner.testrunner import TestRunner, LOGGER_NAME
from runsystem.db.reportgenerator import ExcelReportGenerator

def action_runserver(name, args):
    """start a new development server"""

    parser = OptionParser("""\
%s [options] <instance path>""" % name)
    parser.add_option("", "--hostname", dest="hostname", type=str,
                      help="host interface to use [%default]",
                      default='localhost')
    parser.add_option("", "--port", dest="port", type=int, metavar="N",
                      help="local port to use [%default]", default=8000)
    parser.add_option("", "--reloader", dest="reloader", default=False,
                      action="store_true", help="use WSGI reload monitor")
    parser.add_option("", "--debugger", dest="debugger", default=False,
                      action="store_true", help="use WSGI debugger")
    parser.add_option("", "--profiler-file", dest="profiler_file",
                      help="file to dump profile info to [%default]",
                      default="profiler.log")
    parser.add_option("", "--profiler-dir", dest="profiler_dir",
                      help="pstat.Stats files are saved to this directory " \
                          +"[%default]",
                      default=None)
    parser.add_option("", "--profiler", dest="profiler", default=False,
                      action="store_true", help="enable WSGI profiler")
    parser.add_option("", "--threaded", dest="threaded", default=False,
                      action="store_true", help="use a threaded server")

    (opts, args) = parser.parse_args(args)
    if len(args) != 1:
        parser.error("invalid number of arguments")

    input_path, = args

    logger = logging.getLogger(LOGGER_NAME)
    if opts.debugger:
        logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)

    import runsystem.server.ui.app
    app = runsystem.server.ui.app.App.create_standalone(input_path,)
    if opts.debugger:
        app.debug = True
    if opts.profiler:
        if opts.profiler_dir:
            if not os.path.isdir(opts.profiler_dir):
                os.mkdir(opts.profiler_dir)
        app.wsgi_app = werkzeug.contrib.profiler.ProfilerMiddleware(
            app.wsgi_app, stream = open(opts.profiler_file, 'w'),
            profile_dir = opts.profiler_dir)
    app.run(opts.hostname, opts.port,
            use_reloader = opts.reloader,
            use_debugger = opts.debugger,
            threaded = opts.threaded)

def action_runtest(name, args):
    """run a builtin test application"""

    parser = OptionParser("%s [options]" % name)
    parser.disable_interspersed_args()
    parser.add_option("", "--submit", dest="submit", type=str, default=None)

    print args

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    runner = TestRunner()

def action_get_excel_report(name, args):
    parser = OptionParser("%s [options]" % name)
    parser.add_option("-o", "--output", dest="output", type=str, default=None)
    (opts, args) = parser.parse_args(args)
    if len(args) != 0:
        parser.error("invalid number of arguments")
    if not opts.output:
        parser.error("output file is nessecary")
    ExcelReportGenerator().get_report(opts.output)

tool = runsystem.util.multitool.MultiTool(locals())

def main(*args, **kwargs):
    return tool.main(*args, **kwargs)

if __name__ == '__main__':
    main()