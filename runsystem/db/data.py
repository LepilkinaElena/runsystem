import runsystem
import json

from datetime import datetime
from elasticsearch_dsl import DocType, Integer, Keyword, Text, InnerObjectWrapper, Nested, Boolean
from elasticsearch_dsl.connections import connections

class FeaturesFactory(object):
    """Class for creating features from llvm description."""
    @staticmethod
    def createFeatures(description):
        features_desc = json.loads(description)
        features_classes = {
            'loop' :'LoopFeatures'
        }
        if features_desc['type'] in features_classes:
            typed_features = globals()[features_classes[features_desc['type']]]()
            features = Features()
            setattr(typed_features, "block_id", features_desc['id'])
            pass_string_list = features_desc['pass_place'].split(' ')
            features.place = pass_string_list.pop(0)
            features.pass_name = ' '.join(pass_string_list)
            features.features_set = features_desc['features']
        return (features, typed_features)

class FeaturesSet(InnerObjectWrapper):
    """ Inner entity for set of features."""
    def has_feature(self, feature_name):
        return hasattr(self, feature_name)

    def get_feature(self, feature_name):
        if self.has_feature(feature_name):
            return getattr(self, feature_name)
        return None

class Features(DocType):
    """ Database entity for static features."""
    pass_name = Keyword()
    place = Keyword()
    features_set = Nested(
        doc_class = FeaturesSet,
        properties = {
            'numIVUsers': Integer(),
            'isLoopSimplifyForm': Boolean(),
            'isEmpty': Boolean(),
            'numIntToFloatCast': Integer(),
            'hasLoopPreheader': Boolean(),
            'numTermBrBlocks': Integer(),
            'latchBlockTermOpcode': Integer()
        }
    )

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Features, self).save(** kwargs)

class LoopFeatures(DocType):
    """ Database entity for loop static features."""
    block_id = Keyword()
    features_id = Keyword()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(LoopFeatures, self).save(** kwargs)

class Function(DocType):
    """ Database entity for function."""
    application = Keyword()
    filename = Keyword()
    function_name = Keyword()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Function, self).save(** kwargs)

class Run(DocType):
    """Database entity for run of system."""
    options = Text()
    date_time = Text()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Run, self).save(** kwargs)

class Loop(DocType):
    """Database entity for loop."""
    loop_id = Keyword()
    run_id = Keyword()
    exec_time = Integer()
    code_size = Integer()
    function_id = Keyword()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Loop, self).save(** kwargs)


def init_database():
    # Define a default Elasticsearch client
    connections.create_connection(hosts=['localhost'])
    # Create the mappings in Elasticsearch
    Run.init()
