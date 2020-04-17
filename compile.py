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


def get_scopes(view, point):
    return view.scope_name(point).strip().split(" ")

def determine_depth(scopes):
    depth = 0
    for scope in scopes:
        # TODO: replace with customisable regex
        if ("meta.parens" or "meta.section") in scope:
            depth += 1
    return depth


class SlyCompileTopLevel(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = getSession(window.id())
        MAX_SEARCH_ITERATIONS = \
            settings().get("compilation")['max_search_iterations']

        point = view.sel()[0].begin()
        region = view.extract_scope(point)
        # It only has the scope of the file, so its outside
        # a toplevel form, we need to find one.
        if len(get_scopes(view, point)) == 1:
            region = util.find_closest_before_point(view, point, r"\S")
            distance_to_first = point - region.end() 
            region1 = view.find(r"\S", point) # finds closest after point
            if (point - region.end()) >= (region1.begin() - point):
                region = region1
        
        # This algorithm will go through a form, going to the start
        # of every scope and checking if it is of form 
        # ["source.lisp", "meta.parens.lisp"] or something*
        # at which point it'll expand the scope and compile the selection
        # *deliberately vague in the while statement to allow for different
        # syntax scoping (e.g. "source.cl" or "source.scm").
        point = region.begin()
        scopes = get_scopes(view, point)
        depth = determine_depth(scopes)
        previous_region = Region(-1, -1)
        iterations = 0
        forward = True
        while ((depth > 1 or len(scopes) > 2) 
                and iterations < MAX_SEARCH_ITERATIONS):
            if previous_region != region:
                point = region.begin() if forward else region.end()
            else:
                point += -1 if forward else +1

            scopes = get_scopes(view, point)
            depth = determine_depth(scopes)
            previous_region = region
            region = view.extract_scope(point)
            iterations += 1
            # We check if we reached the "(" of a top-level form
            # and if we did we go the opposite way until we find
            # a scope where the extract_scope is the top-level form
            if len(scopes) == 3 and "begin" in scopes[2]:
                forward = False

        if depth == 1:
            compile_region(view, window, session, region)
        elif iterations >= MAX_SEARCH_ITERATIONS:
            window.status_message("Failed to find top-level form within alloted search time")
        else:
            window.status_message("Failed to find nearby top-level form.")

