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
import traceback
import datetime

import runsystem.db.data as data

from optparse import OptionParser, OptionGroup

class Profiler(object):
    """
    Base class for changable profiler modules.
    """

    def __init__(self):
        self._log = None
        self._run_line = None
        self._path = None
        self._application = None

    def run(self, args):
        raise RuntimeError("Abstract Method.")

    def _run(self, log, run_line, profiler_path, application,
             offset_files, args):
        self._log = log
        self._run_line = run_line
        self._path = profiler_path
        self._application = application
        try:
            return self.run(args, offset_files)
        finally:
            self._log = None
            self._run_line = None
            self._path = None
            self._application = None

    def call(self, args, **kwargs):
        if kwargs.get('shell', False):
            cmdstr = args
        else:
            cmdstr = ' '.join(args)

        if 'cwd' in kwargs:
            print >>self._log, "# In working dir: " + kwargs['cwd']
        print >>self.log, cmdstr

        self._log.flush()
        p = subprocess.Popen(args, stdout=self._log, stderr=self._log, **kwargs)
        return p.wait()

    @property
    def log(self):
        """Get the test log output stream."""
        if self._log is None:
            raise ValueError("log() unavailable outside test execution")
        return self._log

class CodeSizeCounter(object):
    """
    Base class for different classes for collecting code size.
    """

    def run(self):
        raise RuntimeError("Abstract Method.")

class LoopCodeSizeCounter(CodeSizeCounter):

    def run(self, code_size_filenames, application_name):
        results = {}
        for code_size_filename in code_size_filenames:
            filename = os.path.basename(code_size_filename)
            base_filename = filename.partition(".")[0]

            with open(code_size_filename) as code_size_file:
                for line in code_size_file.readlines():
                    offset = re.match(r'\[(\d+)\s*,\s*(\d+)\]\s*-\s*(\d+)', line)
                    if offset:
                        value = int(offset.group(2)) - int(offset.group(1))
                        full_id = ".".join((application_name, base_filename,
                                            "llvm.loop.id" + " " + offset.group(3)))
                        if full_id in results:
                            results[full_id] = results[full_id] + value
                        else:
                            results[full_id] = value
        return results



LOGGER_NAME = "runsystem.server.ui.app"

def getLogger():
    logger = logging.getLogger(LOGGER_NAME)
    return logger

def fatal(message):
    getLogger().critical(message)
    sys.exit(1)

note = lambda message: getLogger().info(message)
warning = lambda message: getLogger().warning(message)
error = lambda message: getLogger().error(message)

data.init_database()

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
        group.add_option("", "--cppflags", type=str, action="append",
                         dest="cppflags", default=[],
                         help="Extra flags to pass the compiler in C or C++ mode. "
                              "Can be given multiple times")
        group.add_option("", "--cflags", type=str, action="append",
                         dest="cflags", default=[],
                         help="Extra CFLAGS to pass to the compiler. Can be "
                              "given multiple times")
        group.add_option("", "--cxxflags", type=str, action="append",
                         dest="cxxflags", default=[],
                         help="Extra CXXFLAGS to pass to the compiler. Can be "
                              "given multiple times")
        parser.add_option_group(group)

        group = OptionGroup(parser, "Test selection")
        group.add_option("", "--test-size", type='choice', dest="test_size",
                         choices=['small', 'regular', 'large'], default='regular',
                         help="The size of test inputs to use")
        group.add_option("", "--only-test", dest="only_test", metavar="PATH",
                         type=str, default=None,
                         help="Only run tests under PATH")

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
        group.add_option("", "--use-make", dest="make", metavar="PATH",
                         type=str, default="make",
                         help="Path to Make [make]")
        group.add_option("", "--use-profiler", dest="profiler",
                         type=str, default="oprofile",
                         help="Module with profiler run to get data")
        group.add_option("", "--profiler-path", dest="profiler_path", metavar="PATH",
                         type=str, default="",
                         help="Path to used profiler")
        parser.add_option_group(group)

        (opts, args) = parser.parse_args(args)
        self.opts = opts
        self.args = args

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
        profilers_modules = list(self._scan_for_profilers())
        if opts.profiler not in profilers_modules:
            parser.error("Module for profiler %s not found" % opts.profiler)
        if opts.profiler_path:
            opts.profiler_path = resolve_command_path(opts.profiler_path)
            if not isexecfile(opts.profiler_path):
                parser.error("Profiler tool not found (looked for %s)" % opts.profiler_path)

        if opts.only_test:
            # --only-test can either point to a particular test or a directory.
            # Therefore, test_suite_root + opts.only_test or
            # test_suite_root + dirname(opts.only_test) must be a directory.
            path = os.path.join(self.opts.test_suite_root, opts.only_test)
            parent_path = os.path.dirname(path)
            
            if os.path.isdir(path):
                opts.only_test = (opts.only_test, None)
            elif os.path.isdir(parent_path):
                opts.only_test = (os.path.dirname(opts.only_test),
                                  os.path.basename(opts.only_test))
            else:
                parser.error("--only-test argument not understood (must be a " +
                             " test or directory name)")

        opts.cppflags = ' '.join(opts.cppflags)
        opts.cflags = ' '.join(opts.cflags)
        opts.cxxflags = ' '.join(opts.cxxflags)

        self.start_time = timestamp()
        self.ts = self.start_time.replace(' ', '_').replace(':', '-')
        build_dir_name = "run-%s" % self.ts

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
            path_mlopt = os.path.join(path, self.opts.mloptions)
            mkdir_p(path_mlopt)
            self.run(path_default, option)
            #self.run(path_mlopt, option, self.opts.mloptions)

    def run(self, path, opt_option, mloptions = ""):
        self._configure(path, opt_option, mloptions)
        self._clean(path)
        self._make(path)
        self._run_tests(path, ' '.join((opt_option, mloptions)).rstrip())

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
        if self.opts.only_test:
            components = [path] + [self.opts.only_test[0]]
            subdir = os.path.join(*components)
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
                    " -mllvm -features-file=features.output"
        all_cflags = all_flags
        all_cxx_flags = all_flags
        if self.opts.cppflags or self.opts.cflags:
            all_cflags = all_flags + ' ' + ' '.join([self.opts.cppflags, self.opts.cflags])
        defs['CMAKE_C_FLAGS'] = self._unix_quote_args(all_cflags)
        
        if self.opts.cppflags or self.opts.cxxflags:
            all_cxx_flags = all_flags + ' ' + ' '.join([self.opts.cppflags, self.opts.cxxflags])
        defs['CMAKE_CXX_FLAGS'] = self._unix_quote_args(all_cxx_flags)
            
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
        if self.opts.only_test:
            components = [path] + [self.opts.only_test[0]]
            if self.opts.only_test[1]:
                target = self.opts.only_test[1]
            subdir = os.path.join(*components)
        note('Building...')

        args = ["-i", "VERBOSE=1", target]
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

    def _scan_for_profilers(self):
        base_profiler_modules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../profilers')

        # We follow links here because we want to support the ability for having
        # various "suites" of LNTBased tests in separate repositories, and allowing
        # users to just checkout them out elsewhere and link them into their LLVM
        # test-suite source tree.
        profilers = []
        for dirpath,dirnames,filenames in os.walk(base_profiler_modules_path,
                                                  followlinks = True):
            # Check if this directory defines a test module.
            if 'profiler.py' not in filenames:
                continue

            # If so, don't traverse any lower.
            del dirnames[:]

            # Add to the list of test modules.
            assert dirpath.startswith(base_profiler_modules_path + '/')
            yield dirpath[len(base_profiler_modules_path) + 1:]

    def _extract_run_line(self, test_file):
        """ Get run line from test file generated by cmake """
        if os.path.isfile(test_file):
            with open(test_file) as parsed_file:
                for line in parsed_file.readlines():
                    run_line = re.match(r'RUN:\s*(.+)', line)
                    return run_line.group(1)

    def _run_tests(self, path, options):
        run = data.Run(date_time=self.ts, options=options)
        run.save()
        for dirpath,dirnames,filenames in os.walk(path,
                                                  followlinks = True):
            if 'CMakeFiles' in dirnames:
                dirnames.remove('CMakeFiles')
            # Check if directory has executables:
            for filename in filenames:
                if isexecfile(os.path.join(dirpath, filename)):
                    offset_file = os.path.join(dirpath, filename + ".functions.offset")
                    features_output_file = os.path.join(dirpath, filename + ".features.output")
                    offset_files = []
                    features_output_files = []
                    # Single source.
                    if os.path.isfile(offset_file):
                        offset_files.append(offset_file)
                    if os.path.isfile(features_output_file):
                        features_output_files.append(features_output_file)
                    # Multi sources.
                    else:
                        # All offset files are connected with application.
                        for inner_file in filenames:
                            if inner_file.endswith(".functions.offset"):
                                offset_files.append(os.path.join(dirpath, inner_file))
                            if inner_file.endswith(".features.output"):
                                features_output_files.append(os.path.join(dirpath, inner_file))

                    test_file = os.path.join(dirpath, filename + ".test")
                    run_line = self._extract_run_line(test_file)
                    if run_line:
                        #code_size_results = LoopCodeSizeCounter().run(offset_files, filename)
                        #print(code_size_results)
                        log_file = os.path.join(dirpath, filename + ".asm.oprof")
                        time_results = self._profile(log_file, run_line, filename, offset_files)
                        #print(time_results)
                        features = self._parse_features_output(features_output_files)
                        self.save_results(run, features, time_results)


    def _parse_features_output(self, output_files):
        result = []
        cur_json_string = ""
        for output_filename in output_files:
            with open(output_filename) as output:
                for line in output.readlines():
                    cur_json_string = cur_json_string + line.rstrip()
                    if line.startswith("}"):
                        result.append(cur_json_string)
                        cur_json_string = ""
        return result

    def save_results(self, run, features, time_results):
        typed_features = {}
        # Save static features.
        for features_set in features:
            features_instance, typed_instance = data.FeaturesFactory.createFeatures(features_set)
            features_instance.save()
            typed_instance.features_id = features_instance.meta.id
            if not typed_instance.block_id in typed_features:
                typed_features[typed_instance.block_id] = []
            typed_features[typed_instance.block_id].append(typed_instance)
        for key, value in time_results.iteritems():
            keys_parts = key.split('.')
            function = data.Function(application = keys_parts.pop(0),
                                     run_id = run.meta.id, 
                                     filename = keys_parts.pop(0), 
                                     function_name = value[0])
            function.save()
            block_id = '.'.join(keys_parts)
            block = data.Loop(loop_id = block_id, 
                              exec_time = value[1],
                              code_size = value[2],
                              function_id = function.meta.id)
            #print("%s, %s, %s" % (key, value[1], value[2]))
            block.save()
            for cur_feature in typed_features[block_id]:
                cur_feature.block_id = block.meta.id
                cur_feature.save()

    def _profile(self, log_file, run_line, application, offset_files):
        locals = globals = {}
        base_profiler_modules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 '../profilers')
        module_path = os.path.join(base_profiler_modules_path, 
                                   self.opts.profiler, 
                                   'profiler.py')
        module_file = open(module_path)
        try:
            exec module_file in locals, globals
        except:
            info = traceback.format_exc()
            fatal("unable to import test module: %r\n%s" % (
                    module_path, info))

        profiler_class = globals.get('profiler_class')
        if profiler_class is None:
            fatal("no 'profiler_class' global in import profiler module: %r" % (
                    module_path,))
        try:
            profiler_instance = profiler_class()
        except:
            info = traceback.format_exc()
            fatal("unable to instantiate profiler class for: %r\n%s" % (
                    module_path, info))

        if not isinstance(profiler_instance, Profiler):
            fatal("invalid test class (expected runsystem.testrunner.Profiler "
                  "subclass) for: %r" % module_path)

        try:
            results = profiler_instance._run(log_file, run_line, self.opts.profiler_path, 
                                    application, offset_files, self.args)
        except:
            info = traceback.format_exc()
            fatal("exception executing profiling for: %r\n%s" % (
                    module_path, info))

        return results

def create_instance():
    return TestRunner()

__all__ = ['create_instance']