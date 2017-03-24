#!/home/elena/mysandbox1/bin/python
# -*- Python -*-

import runsystem.server.ui.app

application = lnt.server.ui.app.App.create_standalone(
  'runsystem.cfg')

if __name__ == "__main__":
    import werkzeug
    werkzeug.run_simple('runsystem', 8000, application)
