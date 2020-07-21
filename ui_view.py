import asyncio, uuid, json, math
from datetime import datetime

from sublime import *
import sublime_plugin

from .sly import *
from typing import *


if "VIEWS" not in globals():
    VIEWS = {}

class SlyUrlCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        print("HI")
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)

    async def async_run(self, **q):
      try:
        view = VIEWS[q["__id"]]
        await view.on_url_press(**q)
      except e as Exception:
        print(e)


class UIView:
    def __init__ (self, window, session):
      try:
        global VIEWS
        self.session = session
        self.slynk = session.slynk
        self.html = "System ready..."
        self.id = uuid.uuid4().hex
        print("hioeu")
        VIEWS[self.id] = self
        self.last_modified = datetime.now()
        self.reöpen(window)
      except Exception as e:
        print(f"ERorr: {e}")

    def flip(self):
        self.sheet.set_contents(str(self.html))
        self.last_modified = datetime.now()

    @property
    def window(self):
        return self.sheet.window()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.sheet.set_name(value)

    @name.deleter
    def name(self):
        del self._name

    def reöpen(self, window):
        self.sheet = window.new_html_sheet("UiView", str(self.html))

    @property
    def is_open(self):
        return self.sheet.window() is not None

    def url(self, parameters):
        parameters["__id"] = self.id
        return f"subl:sly_url {json.dumps(parameters)}"

    def destroy(self):
        del VIEWS[self.id]
        self.html = "[destroyed]"
        self.name = "[destroyed]"
        self.flip()

    def focus(self):
        self.window.focus_sheet(self.sheet)


# Sadly sublime text does support `<sub></sub>`
def to_subscript_unicode(string):
    map = {
        "0": "₀",
        "1": "₁",
        "2": "₂",
        "3": "₃",
        "4": "₄",
        "5": "₅",
        "6": "₆",
        "7": "₇",
        "8": "₈",
        "9": "₉",
    }
    output = ""
    for character in string:
        output += map[character] 
    return output


def url(id, parameters):
    parameters["__id"] = id
    return f"subl:sly_url {json.dumps(parameters)}"

"""
    Second type of UI below, the results panel.
    It works just like the Sublime `Find Results` view.
"""
def number_lines(text, prefix="", suffix=" "):
    lines = text.split("\n")
    width = math.ceil(math.log(len(lines)))
    offset = settings().get("line_offset")
    return "\n".join([prefix + str(n+offset).rjust(width, ' ') + suffix + line 
                      for n, line in enumerate(lines)])

def get_results_view(window):
    view = None
    for maybe_view in window.views():
        if maybe_view.name() == "Sly Output":
            view = maybe_view
            break
    if view and view.settings().get("is-sly-output-view"):
        return view
    session = sessions.get_by_window(window)
    if session is None: 
        print("Error session should exist but doesn't 1")
        raise Exception("Session should exist but doesn't 1")
    view = window.new_file()
    view.set_name("Sly Output")
    view.set_scratch(True)
    view.set_read_only(True)
    view.settings().set("is-sly-output-view", True)
    return view

def send_result_to_panel(window, text=None, result="[No result]", header="[Command_header]", file_name=None, should_fold=True):
    view = get_results_view(window)
    out = [header + "\n",
           number_lines(text, " ") if text else "",
           f"\nfrom: {file_name} is:\n" if file_name else "\n is:\n",
           number_lines(result, " "),
           "\n\n"]
    # We store the position just before the result so
    # we can navigate the user there as that's what they actually care about
    # we also fold the region of the original text
    origin = view.size()
    region = Region(origin+len(out[0]), origin+len(out[0])+len(out[1]))
    out = "".join(out)
    view.run_command("repl_insert_text",
        {"pos": view.size(),
         "text": out})
    window.focus_view(view)
    if text and should_fold:
        view.fold(region)
    view.show(Region(origin, origin+len(out)))  