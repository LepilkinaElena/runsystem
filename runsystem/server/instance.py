import os
import shutil
import tempfile

import runsystem.server.config

class Instance(object):
    """
    Wrapper object for representing an instance.
    """

    @staticmethod
    def frompath(path):
        """
        frompath(path) -> Insance
        """

        # Accept paths to config files, or to directories containing 'runsystem.cfg'.
        tmpdir = None
        if os.path.isdir(path):
            config_path = os.path.join(path, 'runsystem.cfg')
        else:
            config_path = path

        if not config_path or not os.path.exists(config_path):
            fatal("invalid config: %r" % config_path)

        config_data = {}
        exec open(config_path) in config_data
        config = runsystem.server.config.Config.fromData(config_path, config_data)

        return Instance(config_path, config)

    def __init__(self, config_path, config):
        self.config_path = config_path
        self.config = config

    def get_database(self, *args, **kwargs):
        return self.config.get_database(*args, **kwargs)
