"""Implement the command line 'runsystem' tool."""
import logging
import os
import sys
import tempfile
import json
from optparse import OptionParser, OptionGroup
import contextlib
import runsystem.util.multitool
from runsystem.testrunner.testrunner import TestRunner

def action_runtest(name, args):
    """run a builtin test application"""

    parser = OptionParser("%s [options]" % name)
    parser.disable_interspersed_args()
    parser.add_option("", "--submit", dest="submit", type=str, default=None)

    (deprecated_opts, args) = parser.parse_args(args)
    if len(args) < 1:
        parser.error("incorrect number of argments")

    # Rebuild the deprecated arguments.
    for key, val in vars(deprecated_opts).iteritems():
        if val is not None:
            if isinstance(val, str):
                args.insert(0, val)
            args.insert(0, "--" + key)

            warning("--{} should be passed directly to the"
                        " test suite.".format(key))

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    runner = TestRunner()
    server_results = runner.run_test('%s' % (name), args)
    if server_results.get('result_url'):
        print "Results available at:", server_results['result_url']
    else:
        print "Results available at: no URL available"

tool = runsystem.util.multitool.MultiTool(locals())

def main(*args, **kwargs):
    return tool.main(*args, **kwargs)

if __name__ == '__main__':
    main()