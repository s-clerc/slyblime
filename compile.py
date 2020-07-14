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

class SlyCompileSelectionCommand(sublime_plugin.TextCommand):
    def run(self, edit, event=None, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = sessions.get_by_window(window)
        if session is None: return
        
        if event:
            selections = [
                util.nearest_region_to_point(
                    util.event_to_point(view, event), 
                    view.sel())]
            if selections[0] is None:
                view.window().status_message("No selection found")
                return
        else:
            selections = view.sel()

        for selection in selections:
            compile_region(view, window, session, selection)

    def want_event(self):
        return True

class SlyCompileTopLevelCommand(sublime_plugin.TextCommand):
    def run(self, edit, event=None, **kwargs):
        global loop
        view = self.view
        window = view.window()
        session = sessions.get_by_window(window)
        if session is None: return
        if event:
            point = util.event_to_point(view, event)
        try:
            region = util.find_form_region(
                self.view, 
                point if event else None, # Default start poirnt
                max_iterations=settings().get("compilation")['max_search_iterations'])
        except RuntimeWarning:
            window.status_message("Failed to find top-level form within alloted search time")
        
        if region is not None:
            compile_region(view, window, session, region)
        else:
            window.status_message("Failed to find nearby top-level form.")

    def want_event(self):
        return True

class SlyCompileFileCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        load = kwargs.get("load", False)
        print("hello")
        session = sessions.get_by_window(self.window)
        if session is None: 
            return
        path = self.window.active_view().file_name()
        erase_notes(self.window.active_view())
        asyncio.run_coroutine_threadsafe(
            compile_file(self.window, session, path, basename(path), load),
            loop)

async def compile_file(window, session, path, name, load):
    result = await session.slynk.compile_file(path, load)
    if type(result) != list:
        compilation_results[str(path)] = result
        try:
            if not result.success:
                if load == True: 
                    window.status_message("Loading cancelled due to unsuccessful compilation")
                elif load == False:
                    window.status_message("Compilation encountered at least one error")
                if settings().get("compilation")["notes_view"]["prefer_integrated_notes"]:
                    show_notes_as_regions(window, path, result)
                else: 
                    show_notes_view(window, path, name, result)
            elif len(result.notes) and settings().get("compilation")["notes_view"]["prefer_integrated_notes"]:
                show_notes_as_regions(window, path, result)
        except Exception as e:
            print(result)
            print(f"Compilation Error Unknown {e}")


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
        for index, note in enumerate(result.notes):
            location = note.location
            path = escape(location["file"])
            position = escape(str(location["position"]))
            severity = escape(str(note.severity)[1:].capitalize())
            html += (f'<h2>{severity}: {escape(note.message)} </h2>'
                     f'<blockquote> {escape(location["snippet"])} </blockquote><br>'
                     # We're using json.dumps because lazy
                     f'<a href=\'subl:sly_compilation_error_url {{"index": {index}, "path": "{path}"}}\'>{path} at {position}</a>')
        html += "</body></html>"
        affixes = settings().get("compilation")["notes_view"]["view_title_affixes"]
        title = affixes[0] + name + affixes[1]
        window.new_html_sheet(title, html)

    except Exception as e:
        window.status_message("Failed to open compilation notes view")
        print(f"Exception while rendering notes view: {e} ")


class SlyCompilationErrorUrlCommand(sublime_plugin.WindowCommand):
    def run(self, index=None, path=""):
        try:
            config = settings().get("compilation")["notes_view"]

            result = compilation_results[path]
            location = result.notes[int(index)].location
            point = location["position"]
            path = location["file"]
            view = self.window.find_open_file(path)
            if view is None or config["always_reopen_file"]:
                view = self.window.open_file(path, sublime.TRANSIENT)

            view.show_at_center(point)
            snippet_region = find_snippet_region(view, location["snippet"], point)
            util.highlight_region(
                view,
                snippet_region,
                settings().get("highlighting"),
                None,
                config["note_regions"]["highlight_scope"])
            self.window.focus_view(view)
        except Exception as e:
            self.window.status_message("Failed to process URL")
            print(f"SlyCompilationErrorUrlCommandException: {e}")


def show_notes_as_regions(window, path, result: slynk.structs.CompilationResult):
    config = settings().get("compilation")
    always_reopen = config["notes_view"]["always_reopen_file"]
    regional_settings = config["notes_view"]["note_regions"]
    show_annotations = config["notes_view"]["annotations"]
    annotation_groups = config["annotation_groups"]
    view = window.find_open_file(path)
    if view is None or always_reopen:
        view = self.window.open_file(path, sublime.TRANSIENT)
    groups: List[Tuple[List[Regions], List[str]]] = []
    for i in range(0, len(annotation_groups)):
        groups.append(([], [])) # Create new tuples for each
    regions = []
    are_visible = []
    for i, note in enumerate(result.notes):
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
        joined_string = "\u001E".join([
            str(note.severity), str(note.message), str(note.source_context),
            str(note.location), str(note.references)])
        regions.append(region)
        are_visible.append(False)
        for j, group in enumerate(annotation_groups):
            prefix = group['prefix'] if "prefix" in group else ""
            if re.match(group["matches"], joined_string):
                groups[j][0].append(region)
                groups[j][1].append(f"{prefix}{note.severity[1:].capitalize()}: {note.message}")  
                are_visible[i] = True
                break          
    # Because compilation_results is dictionary which may accept tuples:
    compilation_results[(path, "regions")] = (regions, are_visible)
    view.settings().set("path-for-sly-compilation-notes", path)
    view.settings().set("sly-visible-compilation-notes", sum([1 if el else 0 for el in are_visible]))
    view.settings().set("number-sly-compilation-notes", len(annotation_groups))
    for i, (regions, annotations) in enumerate(groups):
        info = annotation_groups[i]
        scope = info["highlight_scope"] if "highlight_scope" in info else regional_settings["highlight_scope"]
        data = {
            "key":f"sly-compilation-notes-{i}", 
            "regions":regions, 
            "scope": scope, 
            "icon": info["icon"] if "icon" in info else "", 
            "flags": DRAW_EMPTY
        }
        if show_annotations:
            data["annotations"] = annotations
        if "annotation_color" in info:
            data["annotation_color"] = info["annotation_color"]
        view.add_regions(**data)


class SlyRegionalNotesEventListener(sublime_plugin.EventListener):
    def on_hover(self, view, point, zone):
        config = settings().get("compilation")["notes_view"]["note_regions"]
        visible = view.settings().get("sly-visible-compilation-notes")
        if not all([config["enable_hover"],
                    zone == HOVER_TEXT,
                    visible and visible > 0,
                    path := view.settings().get("path-for-sly-compilation-notes")]): 
            return

        dimensions = config["dimensions"]
        result = compilation_results[path]
        regions, are_visible = compilation_results[(path, "regions")]

        # Linear search since the regions are unsorted :()
        hover_region_size = 100000
        hover_region_index = -1
        for i, region in enumerate(regions):
            if (are_visible[i] and region.contains(point) 
                and (hover_region_index == -1 or region.size() < hover_region_size)):
                hover_region_size = region.size()
                hover_region_index = i
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
        erase_notes(self.window.active_view())

    def is_visible(self, **kwargs):
        visible = self.window.active_view().settings().get("sly-visible-compilation-notes")
        return (visible and visible > 0) == True

def erase_notes(view):
    settings = view.settings()
    visible = visible = settings.get("sly-visible-compilation-notes")
    if not (visible and visible > 0):
        return
    for i in range(0, settings.get("number-sly-compilation-notes")):
        view.erase_regions(f"sly-compilation-notes-{i}")
    settings.set("sly-visible-compilation-notes", 0)



