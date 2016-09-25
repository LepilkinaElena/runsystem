import subprocess
import tempfile
import logging
import json
import os
import shlex
import platform
import pipes
import sys
import shutil
import glob
import re
import multiprocessing
import getpass
import datetime

from optparse import OptionParser, OptionGroup

LOGGER_NAME = "runsystem.server.ui.app"

def getLogger():
    logger = logging.getLogger(LOGGER_NAME)
    return logger

note = lambda message: getLogger().info(message)
warning = lambda message: getLogger().warning(message)
error = lambda message: getLogger().error(message)

def resolve_command_path(name):
    """Try to make the name/path given into an absolute path to an
    executable.

    """
    # If the given name exists (or is a path), make it absolute.
    if os.path.exists(name):
        return os.path.abspath(name)

    # Otherwise we most likely have a command name, try to look it up.
    path = which(name)
    if path is not None:
        note("resolved command %r to path %r" % (name, path))
        return path

    # If that failed just return the original name.
    return name

def isexecfile(path):
    """Does this path point to a valid executable?

    """
    return os.path.isfile(path) and os.access(path, os.X_OK)

def timestamp():
    return datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

def mkdir_p(path):
    """mkdir_p(path) - Make the "path" directory, if it does not exist; this
    will also make directories for any missing parent directories."""
    import errno

    try:
        os.makedirs(path)
    except OSError as e:
        # Ignore EEXIST, which may occur during a race condition.        
        if e.errno != errno.EEXIST:
            raise

class TestRunner(object):

    def describe(self):
        return "LLVM test-suite"

    def run_test(self, name, args):
        parser = OptionParser("%s [options] test-suite" % name)
        group = OptionGroup(parser, "Sandbox options")
        group.add_option("-S", "--sandbox", dest="sandbox_path",
                         help="Parent directory to build and run tests in",
                         type=str, default=None, metavar="PATH")
        parser.add_option_group(group)
        
        group = OptionGroup(parser, "Inputs")
        group.add_option("", "--test-suite", dest="test_suite_root",
                         type=str, metavar="PATH", default=None,
                         help="Path to the LLVM test-suite sources")
        parser.add_option_group(group)

        group = OptionGroup(parser, "Test compiler")
        group.add_option("", "--cc", dest="cc", metavar="CC",
                         type=str, default=None,
                         help="Path to the C compiler to test")
        group.add_option("", "--cxx", dest="cxx", metavar="CXX",
                         type=str, default=None,
                         help="Path to the C++ compiler to test (inferred from"
                              " --cc where possible")
        parser.add_option_group(group)

        group = OptionGroup(parser, "Test Execution")
        group.add_option("-j", "--threads", dest="threads",
                         help="Number of testing (and optionally build) "
                         "threads", type=int, default=1, metavar="N")
        parser.add_option_group(group)
        group = OptionGroup(parser, "Output Options")
        group.add_option("", "--submit", dest="submit_url", metavar="URLORPATH",
                         help=("autosubmit the test result to the given server"
                               " (or local instance) [%default]"),
                         type=str, default=None)
        group.add_option("", "--runs", dest="runs", type=str, metavar="[Optimization Options]",
                         default = "-O0 -O1 -O2 -O3 -Ofast -Os -Oz",
                         help="Optimization options for run tests")
        group.add_option("", "--ml-options", dest="mloptions", 
                         type=str, metavar="[ML Options]", default=None,
                         help="Combinations of options to turn on/off")
        parser.add_option_group(group)

        group = OptionGroup(parser, "Test tools")
        group.add_option("", "--use-cmake", dest="cmake", metavar="PATH",
                         type=str, default="cmake",
                         help="Path to CMake [cmake]")
        group.add_option("", "--use-lit", dest="lit", metavar="PATH",
                         type=str, default="llvm-lit",
                         help="Path to the LIT test runner [llvm-lit]")
        parser.add_option_group(group)

        (opts, args) = parser.parse_args(args)
        self.opts = opts

        if self.opts.sandbox_path is None:
            parser.error('--sandbox is required')

        if self.opts.cc is None:
            parser.error('--cc is required')

        # Option validation.
        opts.cc = resolve_command_path(opts.cc)

        # If there was no --cxx given, attempt to infer it from the --cc.
        if opts.cxx is not None:
            opts.cxx = resolve_command_path(opts.cxx)
                
        if not os.path.exists(opts.cxx):
            parser.error("invalid --cxx argument %r, does not exist" % (opts.cxx))

        if opts.test_suite_root is None:
            parser.error('--test-suite is required')
        if not os.path.exists(opts.test_suite_root):
            parser.error("invalid --test-suite argument, does not exist: %r" % (
                opts.test_suite_root))

        opts.cmake = resolve_command_path(opts.cmake)
        if not isexecfile(opts.cmake):
            parser.error("CMake tool not found (looked for %s)" % opts.cmake)

        opts.lit = resolve_command_path(opts.lit)
        if not isexecfile(opts.lit):
            parser.error("LIT tool not found (looked for %s)" % opts.lit)

        self.start_time = timestamp()
        ts = self.start_time.replace(' ', '_').replace(':', '-')
        build_dir_name = "run-%s" % ts

        basedir = os.path.join(self.opts.sandbox_path, build_dir_name)

        self._base_path = basedir

        self.run_in_dirs()

    def run_in_dirs(self):
        path = self._base_path
        
        if not os.path.exists(path):
            mkdir_p(path)

        opt_run_options = self.opts.runs.split(" ")
        # Create folder for each run optimize option.
        for option in opt_run_options:
            path = os.path.join(self._base_path, option)
            mkdir_p(path)
            path_default = os.path.join(path, "default")
            mkdir_p(path_default)
            self.run(path_default, option, self.opts.mloptions)
            path_mlopt = os.path.join(path, self.opts.mloptions)
            mkdir_p(path_mlopt)
            self.run(path_mlopt)

    def run(self, path, opt_option, mloptions):
        self._configure(path, opt_option, mloptions)
        self._clean(path)
        self._make(path)
        data = self._lit(path, test)

    def _unix_quote_args(self, s):
        return ' '.join(map(pipes.quote, shlex.split(s)))

    def _check_call(self, *args, **kwargs):
        note('Execute: %s' % ' '.join(args[0]))
        if 'cwd' in kwargs:
            note('          (In %s)' % kwargs['cwd'])
        return subprocess.check_call(*args, **kwargs)

    def _clean(self, path):
        make_cmd = "make"
        subdir = path
        self._check_call([make_cmd, 'clean'],
                         cwd=subdir)

    def _configure(self, path, opt_option, mloptions):
        cmake_cmd = self.opts.cmake

        defs = {
            'CMAKE_C_COMPILER': self.opts.cc,
            'CMAKE_CXX_COMPILER': self.opts.cxx,
        }
        all_flags = opt_option + " " + mloptions + " -mllvm -print-features-before-all" + \
                    " -mllvm -print-features-after-all" + \
                    " -mllvm -features-file features.output"
        defs['CMAKE_C_FLAGS'] = self._unix_quote_args(all_flags)
        
        defs['CMAKE_CXX_FLAGS'] = self._unix_quote_args(all_flags)
            
        lines = ['Configuring with {']
        for k, v in sorted(defs.items()):
            lines.append("  %s: '%s'" % (k, v))
        lines.append('}')

        for l in lines:
            note(l)

        cmake_cmd = [cmake_cmd] + [self.opts.test_suite_root] + \
                    ['-D%s=%s' % (k, v) for k, v in defs.items()]

        self._check_call(cmake_cmd, cwd=path)

        return cmake_cmd

    def _make(self, path):
        make_cmd = "make"
        
        subdir = path
        target = 'all'
        note('Building...')
        args = ["VERBOSE=1", target]
        self._check_call([make_cmd,
                          '-j', str(self.opts.threads)] + args,
                         cwd=subdir)

    def _lit(self, path, test):
        lit_cmd = self.opts.lit

        output_json_path = tempfile.NamedTemporaryFile(prefix='output',
                                                       suffix='.json',
                                                       dir=path,
                                                       delete=False)
        output_json_path.close()
        
        subdir = path
            
        note('Testing...')
        try:
            self._check_call([lit_cmd,
                              '-v',
                              '-j', str(self.self.opts.threads),
                              subdir,
                              '-o', output_json_path.name])
        except subprocess.CalledProcessError:
            # LIT is expected to exit with code 1 if there were test
            # failures!
            pass
        return json.loads(open(output_json_path.name).read())