import os
import re
import tempfile


class Config:
    @staticmethod
    def fromData(path, data):
        # Paths are resolved relative to the absolute real path of the
        # config file.
        baseDir = os.path.dirname(os.path.abspath(path))
        dbDir = data.get('db_dir', '.')
        profileDir = data.get('profile_dir', 'data/profiles')
        
        # If the path does not contain database type, assume relative path.
        dbDirPath = dbDir

        return Config(data.get('name', 'Runsystem'), data['zorgURL'],
                      dbDir, os.path.join(baseDir, profileDir))
    
    @staticmethod
    def dummyInstance():
        baseDir = tempfile.mkdtemp()
        dbDir = 'localhost'
        profileDirPath = os.path.join(baseDir, 'profiles')
        
        return Config('Runsystem', 'http://localhost:8000', dbDir, profileDirPath)
    
    def __init__(self, name, zorgURL, dbDir, profileDir):
        self.name = name
        self.zorgURL = zorgURL
        self.dbDir = dbDir
        self.profileDir = profileDir
        while self.zorgURL.endswith('/'):
            self.zorgURL = zorgURL[:-1]

    def get_database(self, name, echo=False):
        """
        get_database(name, echo=False) -> db or None

        Return the appropriate instance of the database with the given name, or
        None if there is no database with that name."""

        # Get the database entry.
        db_entry = self.databases.get(name)
        if db_entry is None:
            return None

        # Instantiate the appropriate database version.
        if db_entry.db_version == '0.4':
            return lnt.server.db.v4db.V4DB(db_entry.path, self,
                                           db_entry.baseline_revision,
                                           echo)

        raise NotImplementedError,"unable to load version %r database" % (
            db_entry.db_version,)
