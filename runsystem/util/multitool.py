import os
import sys

class MultiTool(object):

    def __init__(self, locals):

        # Create the list of commands.
        self.commands = dict((name[7:].replace('_','-'), f)
                             for name,f in locals.items()
                             if name.startswith('action_'))

    def usage(self, name):
        print >>sys.stderr, "Usage: %s <command> [options] ... arguments ..." %(
            os.path.basename(name),)
        print >>sys.stderr
        print >>sys.stderr, """\
Use ``%s <command> --help`` for more information on a specific command.\n""" % (
            os.path.basename(name),)
        print >>sys.stderr, "Available commands:"
        cmds_width = max(map(len, self.commands))
        for name,func in sorted(self.commands.items()):
            if name.endswith("-debug"):
                continue

            print >>sys.stderr, "  %-*s - %s" % (cmds_width, name, func.__doc__)
        sys.exit(1)

    def main(self, args=None):
        if args is None:
            args = sys.argv

        progname = os.path.basename(args.pop(0))

        # Parse immediate command line options.
        while args and args[0].startswith("-"):
            option = args.pop(0)
            if option in ("-h", "--help"):
                self.usage(progname)
            else:
                print >>sys.stderr, "error: invalid option %r\n" % (option,)
                self.usage(progname)

        if not args:
            self.usage(progname)

        cmd = args.pop(0)
        if cmd not in self.commands:
            print >>sys.stderr,"error: invalid command %r\n" % cmd
            self.usage(progname)

        self.commands[cmd]('%s %s' % (progname, cmd), args)
