import runsystem
import json

from datetime import datetime
from elasticsearch_dsl import DocType, Integer, Keyword, Text, Long
from elasticsearch_dsl import InnerObjectWrapper, Nested, Boolean
from elasticsearch_dsl import FacetedSearch, TermsFacet
from elasticsearch_dsl.connections import connections

class FeaturesFactory(object):
    """Class for creating features from llvm description."""
    @staticmethod
    def createFeatures(description, order = 0):
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
            typed_features.order = order
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
            'latchBlockTermOpcode': Long(),
            'numCalls': Integer(),
            'notDuplicatable': Boolean(),
            'convergent': Boolean(),
            'loopSize': Integer(),
            'tripCount': Integer(),
            'tripMultiply': Long(),
            'termByCondBr': Boolean(),
            'headerAddressTaken': Boolean(),
            'PHINodesInExitBlocks': Boolean()
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
    order = Long()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(LoopFeatures, self).save(** kwargs)

class Function(DocType):
    """ Database entity for function."""
    application = Keyword()
    filename = Keyword()
    function_name = Keyword(store=True)
    run_id = Keyword()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Function, self).save(** kwargs)

    @staticmethod
    def get_ot_create_function(application, run_id, filename, function_name):
        search = Function.search().query('match', run_id=run_id).\
                                   query('match', application=application).\
                                   query('match', filename=filename).\
                                   query('match', function_name=function_name)

        response = search.execute()
        if response.success() and len(response):
            return response[0]
        function = Function(application = application,
                            run_id = run_id, 
                            filename = filename, 
                            function_name = function_name)
        function.save()
        return function

class Run(DocType):
    """Database entity for run of system."""
    options = Text()
    date_time = Text()
    connected_run_id = Keyword()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Run, self).save(** kwargs)

class Loop(DocType):
    """Database entity for loop."""
    loop_id = Keyword()
    exec_time = Long()
    code_size = Long()
    llc_misses = Long()
    function_id = Keyword()

    class Meta:
        index = 'runsystemdb'

    def save(self, ** kwargs):
        return super(Loop, self).save(** kwargs)

class ApplicationSearch(FacetedSearch):
    index = 'runsystemdb'
    doc_types = [Function, ]
    fields = ['application', 'filename', 'function_name']

    facets = {
        'tags': TermsFacet(field='application')
    }

    def __init__(self, run_id):
        self.run_id = run_id
        super(ApplicationSearch, self).__init__()
        

    def search(self):
        s = super(ApplicationSearch, self).search()
        return s.query("match", run_id=self.run_id)

class FilenameSearch(FacetedSearch):
    index = 'runsystemdb'
    doc_types = [Function, ]
    fields = ['application', 'filename', 'function_name']

    facets = {
        'tags': TermsFacet(field='filename')
    }

    def __init__(self, application):
        self.application = application
        super(FilenameSearch, self).__init__()
        

    def search(self):
        s = super(FilenameSearch, self).search()
        return s.query("match", application=self.application)


def init_database():
    # Define a default Elasticsearch client
    connections.create_connection(hosts=['localhost'])
    # Create the mappings in Elasticsearch
    Run.init()
    Function.init()
    Features.init()
    Loop.init()
    LoopFeatures.init()
