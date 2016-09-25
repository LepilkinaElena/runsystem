import subprocess
import tempfile
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

from optparse import OptionParser, OptionGroup

class TestRunner(object):

    def describe(self):
        return "LLVM test-suite"

    def run_test(self, name, args):
        parser = OptionParser("%s [options] test-suite" % name)