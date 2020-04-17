import uuid

from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from SublimeREPL import sublimerepl
from SublimeREPL.repls import repl

from . import pydispatch
from . import slynk, util, sexpdata
from .sly import *


def highlight_region (view, region, duration=None):
    config = settings().get("compilation")
    if not duration:
       duration = config['highlight_duration'] * 1000
    id = uuid.uuid4().hex
    view.add_regions(id, [region], config["highlight_form_scope"], "")
    set_timeout_async(lambda: view.erase_regions(id), duration)


def compile_region(view, window, session, region):
    if region.size() == 0: return
    # we can't do regular destructuring because for some dumb reason emacs has
    # line numbers in N* but column numbers in N (wtaf)
    row, col = view.rowcol(region.begin()) 
    package_information = util.in_package_parameters_at_point(view, region.begin())
    window.status_message(f"Package information: {package_information}")
    highlight_region(view, region)
    parameters = { 
        "string": view.substr(region),
        "buffer_name": view.name(),
        "file_name": view.file_name(),
        "position": (region.begin(), row+1, col),
    }
    if package_information: 
        parameters["package"] = package_information

    asyncio.run_coroutine_threadsafe(
        session.slynk.compile_string(**parameters),
        loop)

class SlyCompileSelection(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = getSession(window.id())

        selections = view.sel()
        for selection in selections:
            compile_region(view, window, session, selection)



