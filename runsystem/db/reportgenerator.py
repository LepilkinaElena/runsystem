import runsystem.db.data as db
import xlsxwriter

class ExcelReportGenerator(object):
    """Class for generating excel report."""
    def _inner_table(self, features_set, i):
        for features in features_set:
            self.loop_features_worksheet.merge_range(i, 0, i+1, 0, features[0].pass_name)
            for irange in [0, 1]:
                self.loop_features_worksheet.write(i, 1, features[irange].place)
                self.loop_features_worksheet.write(i, 2, features[irange].features_set.numIVUsers)
                self.loop_features_worksheet.write(i, 3, str(features[irange].features_set.isLoopSimplifyForm))
                self.loop_features_worksheet.write(i, 4, str(features[irange].features_set.isEmpty))
                self.loop_features_worksheet.write(i, 5, features[irange].features_set.numIntToFloatCast)
                self.loop_features_worksheet.write(i, 6, str(features[irange].features_set.hasLoopPreheader))
                self.loop_features_worksheet.write(i, 7, features[irange].features_set.numTermBrBlocks)
                self.loop_features_worksheet.write(i, 8, features[irange].features_set.latchBlockTermOpcode)
                i += 1
        return i

    def get_report(self, output):
        db.init_database()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('loops')
        bold = workbook.add_format({'bold': True})
        table_titles = ['Loop', 'Code size', 'Execution time']
        j = 0
        for title in table_titles:
            worksheet.write(0, j, title, bold)
            j +=1
        j = 0
        i = 1
        s = db.Loop.search()
        s = s[0:10000]
        loops = s.execute()
        for loop in loops:
            function = db.Function.get(id=loop.function_id)
            worksheet.write(i, 0, ".".join((function.application, function.filename, loop.loop_id)))
            worksheet.write(i, 1, loop.code_size)
            worksheet.write(i, 2, loop.exec_time)
            i +=1
        loop_features_worksheet = workbook.add_worksheet('loop_features')
        table_titles = ['Pass', 'Place', 'numIVUsers', 'isLoopSimplifyForm', 'isEmpty', 'numIntToFloatCast', 'hasLoopPreheader', 'numTermBrBlocks', 'latchBlockTermOpcode']
        j = 0
        for title in table_titles:
            loop_features_worksheet.write(0, j, title, bold)
            j +=1
        i = 1
        self.workbook = workbook
        self.loop_features_worksheet = loop_features_worksheet
        for loop in loops:
            features_sets = {}
            function = db.Function.get(id=loop.function_id)
            loop_features_worksheet.merge_range(i, 0, i, len(table_titles) - 1,
                ".".join((function.application, function.filename, loop.loop_id)), bold)
            i+=1
            s = db.LoopFeatures.search().query('match', block_id=loop.meta.id)
            s = s[0:10000]
            loop_features = s.execute()
            features_sets = {}
            features_sets['Before'] = []
            features_sets['After'] = []
            for features in loop_features:
                features_set = db.Features.get(id=features.features_id, ignore=404)
                if features_set:
                    features_sets[features_set.place].append(features_set)
            i = self._inner_table(zip(features_sets['Before'], features_sets['After']), i)
        workbook.close()