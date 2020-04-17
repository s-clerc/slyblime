from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from . import slynk, util, sexpdata
from .sly import *

from SublimeREPL import sublimerepl
from SublimeREPL.repls import repl
from . import pydispatch

class SlyCompileSelection(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = getSession(window.id())

        selections = view.sel()
        for selection in selections:
            compile_selection(view, window, session, selection)


def compile_selection(view, window, session, selection):
    if selection.size() == 0: return
    # we can't do regular destructuring because for some dumb reason emacs has
    # line numbers in N* but column numbers in N (wtaf)
    row, col = view.rowcol(selection.begin()) 
    package_information = util.in_package_parameters_at_point(view, selection.begin())
    window.status_message(f"Package information: {package_information}")

    parameters = {
        "string": view.substr(selection),
        "buffer_name": view.name(),
        "file_name": view.file_name(),
        "position": (selection.begin(), row+1, col),
    }
    if package_information: 
        parameters["package"] = package_information

    asyncio.run_coroutine_threadsafe(
        session.slynk.compile_string(**parameters),
        loop)


