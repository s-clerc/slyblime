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


class SlyCompileTopLevel(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = sessions.get_by_window(window)
        if session is None: return
        try:
            region = util.find_toplevel_form(
                self.view, 
                None, # Default start poirnt
                settings().get("compilation")['max_search_iterations'])
        except RuntimeWarning:
            window.status_message("Failed to find top-level form within alloted search time")
        
        if region is not None:
            compile_region(view, window, session, region)
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
        return util.in_lisp_file(self.window.active_view(), settings)


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
    config = settings().get("compilation")
    always_reopen = config["notes_view"]["always_reopen_file"]
    regional_settings = config["notes_view"]["note_regions"]
    show_annotations = config["notes_view"]["annotations"]
    view = window.find_open_file(path)
    if view is None or always_reopen:
        view = self.window.open_file(path, sublime.TRANSIENT)
    print(result.notes)
    regions = []
    annotations = []
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
        annotations.append(f"{note.severity[1:].capitalize()}: {note.message}")
    # Because compilation_results is dictionary which may accept tuples:
    compilation_results[(path, "regions")] = regions
    view.settings().set("path-for-sly-compilation-notes", path)
    view.settings().set("fresh-sly-compilation-notes", True)
    data = {
        "key":"sly-compilation-notes", 
        "regions":regions, 
        "scope":regional_settings["highlight_scope"], 
        "icon":"", 
        "flags":DRAW_EMPTY
    }
    if show_annotations:
        data["annotations"] = annotations
    view.add_regions(**data)


class SlyRegionalNotesEventListener(sublime_plugin.EventListener):
    def on_hover(self, view, point, zone):
        if not all([zone == HOVER_TEXT,
                    is_fresh := view.settings().get("fresh-sly-compilation-notes"),
                    path := view.settings().get("path-for-sly-compilation-notes")]): 
            return

        dimensions = settings().get("compilation")["notes_view"]["note_regions"]["dimensions"]
        result = compilation_results[path]
        regions = compilation_results[(path, "regions")]

        # Linear search since the regions are unsorted :()
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
        view = self.window.active_view()
        view.erase_regions("sly-compilation-notes")
        view.settings().set("fresh-sly-compilation-notes", False)

    def is_visible(self, **kwargs):
        return len(self.window.active_view().get_regions("sly-compilation-notes")) > 0




