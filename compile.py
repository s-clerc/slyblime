import uuid
from html import escape, unescape
import json
from os.path import basename
import re
from bisect import bisect_left

from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from SublimeREPL import sublimerepl
from SublimeREPL.repls import repl

from . import pydispatch
from .sly import *
from . import slynk, util, sexpdata


def compile_region(view, window, session, region):
    if region.size() == 0: return
    config = settings().get("compilation")
    highlighting = settings().get("highlighting")
    # we can't do regular destructuring because for some dumb reason emacs has
    # line numbers in N* but column numbers in N (wtaf)
    row, col = view.rowcol(region.begin()) 
    package_info = util.current_package(view, region.begin(), True)
    window.status_message(f"Package information: {package_info[0]}")
    util.highlight_region(view, region, highlighting, None, highlighting["form_scope"])
    parameters = { 
        "string": view.substr(region),
        "buffer_name": view.name(),
        "file_name": view.file_name(),
        "position": (region.begin(), row+1, col),
    }
    if package_info[0]: 
        parameters["package"] = package_info[0]
        util.highlight_region(view, package_info[1], highlighting, None, highlighting["package_scope"])

    asyncio.run_coroutine_threadsafe(
        session.slynk.compile_string(**parameters),
        loop)

class SlyCompileSelection(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = sessions.get_by_window(window)
        if session is None: return

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
        session = sessions.get_by_window(window)
        if session is None: return
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

class SlyCompileFile(sublime_plugin.WindowCommand):
    def run(self, load=False):
        session = sessions.get_by_window(self.window)
        if session is None: return
        path = self.window.active_view().file_name()
        if path is None:
            self.window.status_message(
                "File does not have path and cannot be compiled")
            return
        self.window.active_view().erase_regions("sly-compilation-notes")
        asyncio.run_coroutine_threadsafe(
            compile_file(self.window, session, path, basename(path), load),
            loop)

    def is_visible(self, **kwargs):
        view = self.window.active_view()
        matches = re.findall(
            settings().get("compilation")["syntax_regex"], 
            view.settings().get("syntax"))
        return len(matches) > 0


async def compile_file(window, session, path, name, load):
    result = await session.slynk.compile_file(path, load)
    print(result)
    if type(result) != list:
        compilation_results[str(path)] = result
        if not result.success:
            try:
                if load == True: 
                    window.status_message("Loading cancelled due to unsuccessful compilation")
                elif load == False:
                    window.status_message("Compilation encountered at least one error")
                if settings().get("compilation")["notes_view"]["prefer_integrated_notes"]:
                    show_notes_as_regions(window, path, result)
                else: 
                    show_notes_view(window, path, name, result)
            except Exception as e:
                print(f"fail {e}")


if "compilation_results" not in globals():
    compilation_results = {}


def find_snippet_region(view, snippet, point):
    adjustment = settings().get("compilation")["notes_view"]["snippet_location_adjust"]
    region = view.find(re.escape(snippet), point + adjustment)
    if region.begin() == region.end() == -1:
        return None
    return region


def show_notes_view(window, path, name, result):
    global compilation_notes
    try:
        affixes = settings().get("compilation")["notes_view"]["header_affixes"]
        html = ('<html> <body id="sly-compilation-error-view">'
                f'<h1>{escape(affixes[0] + str(name) + affixes[1])}</h1>')
        index = 0
        for note in result.notes:
            location = note.location
            path = escape(location["file"])
            position = escape(str(location["position"]))
            severity = escape(str(note.severity)[1:].capitalize())
            html += (f'<h2>{severity}: {escape(note.message)} </h2>'
                     f'<blockquote> {escape(location["snippet"])} </blockquote><br>'
                     # We're using json.dumps because lazy
                     f'<a href="{index}">{path} at {position}</a>')
            index += 1
        html += "</body></html>"
        affixes = settings().get("compilation")["notes_view"]["view_title_affixes"]
        title = affixes[0] + name + affixes[1]
        window.new_html_sheet(title, html, "sly_compilation_error_url", {"path": str(path)})

    except Exception as e:
        window.status_message("Failed to open compilation notes view")
        print(f"Exception while rendering notes view: {e} ")


class SlyCompilationErrorUrlCommand(sublime_plugin.WindowCommand):
    def run(self, url=None, path=""):
        try:
            config = settings().get("compilation")["notes_view"]

            result = compilation_results[path]
            location = result.notes[int(url)].location
            point = location["position"]
            path = location["file"]
            view = self.window.find_open_file(path)
            if view is None or config["always_reopen_file"]:
                view = self.window.open_file(path, sublime.TRANSIENT)

            view.show_at_center(point)
            snippet_region = find_snippet_region(view, location["snippet"], point)
            highlight_region(
                view,
                snippet_region,
                settings().get("highlighting"),
                None,
                config["note_regions"]["highlight_scope"])
            self.window.focus_view(view)
        except Exception as e:
            self.window.status_message("Failed to process URL")
            print(f"SlyCompilationErrorUrlCommandException: {e}")


def show_notes_as_regions(window, path, result):
    always_reopen = settings().get("compilation")["notes_view"]["always_reopen_file"]
    regional_settings = settings().get("compilation")["notes_view"]["note_regions"]
    view = window.find_open_file(path)
    if view is None or always_reopen:
        view = self.window.open_file(path, sublime.TRANSIENT)
    print(result.notes)
    regions = []
    for note in result.notes:
        point = note.location["position"]
        snippet = note.location["snippet"]
        # Not a raw string intentionally VVVV
        if regional_settings["ignore_snippet_after_\n"]:
            snippet = snippet.split("\n", 1)[0] 
        if regional_settings["strip_regions"]:
            snippet = snippet.strip()
        region = find_snippet_region(view, snippet, point)
        if region == None:
            region = Region(point, point)
        regions.append(region)
    # Because compilation_results is dictionary which may accept tuples:
    compilation_results[(path, "regions")] = regions
    view.add_regions("sly-compilation-notes", regions, regional_settings["highlight_scope"], "", DRAW_EMPTY)
    view.settings().set("path-for-sly-compilation-notes", path)

class SlyRegionalNotesEventListener(sublime_plugin.EventListener):
    def on_hover(self, view, point, zone):
        if zone != HOVER_TEXT: return
        path = view.settings().get("path-for-sly-compilation-notes")
        if not path: return

        dimensions = settings().get("compilation")["notes_view"]["note_regions"]["dimensions"]
        result = compilation_results[path]
        regions = compilation_results[(path, "regions")]

        # Linear search since the regions are unsorted
        hover_region_size = 100000
        hover_region_index = -1
        index = 0
        for region in regions:
            if (region.contains(point) 
                and (hover_region_index == -1 or region.size() < hover_region_size)):
                hover_region_size = region.size()
                hover_region_index = index
            index += 1
        if hover_region_index < 0: return

        note = result.notes[hover_region_index]
        html = f"{note.severity[1:].capitalize()}: {note.message}"
        view.show_popup(html, HIDE_ON_MOUSE_MOVE_AWAY, point, *dimensions)


class SlyShowNotesViewCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        session = sessions.get_by_window(self.window)
        if session is None: return
        path = self.window.active_view().file_name()
        show_notes_view(self.window, path, basename(path), compilation_results[str(path)])

    def is_visible(self, **kwargs):
        path = self.window.active_view().file_name()
        return path in compilation_results


class SlyLoadFileCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        session = sessions.get_by_window(self.window)
        if session is None: return
        path = self.window.active_view().file_name()
        if path not in compilation_results: 
            self.window.status_message("Path to compiled file not found")
            return
        result = compilation_results[path]
        asyncio.run_coroutine_threadsafe(session.slynk.load_file(path), loop)

    def is_visible(self, **kwargs):
        path = self.window.active_view().file_name()
        return path in compilation_results

class SlyRemoveNoteHighlighting(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        session = sessions.get_by_window(self.window)
        if session is None: return
        self.window.active_view().erase_regions("sly-compilation-notes")

    def is_visible(self, **kwargs):
        return len(self.window.active_view().get_regions("sly-compilation-notes")) > 0




