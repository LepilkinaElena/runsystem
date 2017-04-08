import os
import re
import subprocess
from runsystem.testrunner.testrunner import Profiler
from optparse import OptionParser, OptionGroup

class Oprofile(Profiler):

    def _count_instruction_offset_and_time(self, line, prev_address):
        time = 0
        offset = 0

        code_line = re.match(r'\s*(\d+)?\s+(\d+\.\d+.*)?\s*:\s*([0-9a-fA-F]+):\s*(\w+)',
                             line)
        if not code_line:
            print(prev_address)
            print(line)
            raise SystemExit("wrong format for profiler file")
        if code_line.group(1):
            time = int(code_line.group(1))
        cur_address = int(code_line.group(3), 16)
        instr_size = int(code_line.group(3), 16) - prev_address
        # FIX ME: check nop.
        if code_line.group(4).startswith("nop"):
            offset = 0
        else:
            offset = 1
        return (cur_address, offset, time, instr_size)

    def _get_metrics_for_block(self, assembly_lines, function_name, offset_start, offset_end):
        start_address = None
        is_block_start_found = False
        time_value = 0
        code_size_value = 0
        cur_instr_num = 0
        for assembly_line in assembly_lines:
            if not start_address:
                function_header = re.match(r'([0-9a-fA-F]+)\s*<' + 
                                           re.escape(function_name) + r'>',
                                           assembly_line)
                if function_header:
                    start_address = function_header.group(1)
                    prev_address = int(start_address, 16)
                    cur_instr_num = 0
            else:
                # Find start of block.
                prev_address, cur_offset, time, prev_instr_size = self._count_instruction_offset_and_time(assembly_line, prev_address)
                if not is_block_start_found:
                    if cur_instr_num == offset_start:
                        is_block_start_found = True
                        time_value = time
                else:
                    if cur_instr_num < offset_end:
                        time_value = time_value + time
                    code_size_value = code_size_value + prev_instr_size
                    if cur_instr_num == offset_end:
                        return (time_value, code_size_value)
                cur_instr_num = cur_instr_num + cur_offset

    def _count(self, offset_files):
        results = {}
        # Open file with disassembler.
        with open(self._log) as assembly_file:
            assembly_lines = assembly_file.readlines()
            for offset_filename in offset_files:
                filename = os.path.basename(offset_filename)
                base_filename = filename.partition(".")[0]

                with open(offset_filename) as offset_file:
                    current_function = None
                    for line in offset_file.readlines():
                        offset = re.match(r'\[(\d+)\s*,\s*(\d+)\]\s*-\s*(\d+)', line)
                        if offset:
                            offset_value = int(offset.group(2)) - int(offset.group(1))
                            full_id = ".".join((self._application, base_filename, 
                                                "llvm.loop.id" + " " + offset.group(3)))
                            # Find the same part in disassembler.
                            metrics = self._get_metrics_for_block(assembly_lines, current_function, int(offset.group(1)), int(offset.group(2)))
                            if metrics:
                                time, code_size = metrics
                                if full_id in results:
                                    results[full_id] = (current_function, results[full_id][1] + time,
                                                        results[full_id][2] + code_size)
                                else:
                                    results[full_id] = (current_function, time, code_size)
                        else:
                            # Function name.
                            current_function = line.rstrip()
        return results

    def run(self, args, offset_files):
        parser = OptionParser("operf [options] ")
        group = OptionGroup(parser, "Oprofile options")
        group.add_option("", "--oprof-counter", dest="counter",
                         help="Counter which should be used for profiling",
                         type=str, default="CPU_CLK_UNHALTED")
        group.add_option("", "--oprof-count-num", dest="count_num",
                         help="Counter number which should be used for profiling",
                         type=int, default=100000)
        parser.add_option_group(group)

        (opts, args) = parser.parse_args(args)

        operf_command = "operf"
        opannotate_command = "opannotate"

        # Get full path if commands aren't in PATH.
        if not self._path:
            operf_command = os.path.join(self._path, operf_command)
            opannotate_command = os.path.join(self._path, opannotate_command)

        # operf -e CPU_CLK_UNHALTED:100000:0:0:1 --callgraph [run_line]
        cmd = [operf_command, '-e', 
               ":".join((opts.counter, str(opts.count_num), "0:0:1"))]
        cmd.extend(self._run_line.split())
        subprocess.check_call(cmd)

        # opannotate --source --assembly [run_line]
        cmd = [opannotate_command, '--source', '--assembly']
        cmd.extend(self._run_line.split())
        with open(self._log, 'w+') as assembly_file:
            subprocess.check_call(cmd, stdout=assembly_file)

        return self._count(offset_files)


profiler_class = Oprofile