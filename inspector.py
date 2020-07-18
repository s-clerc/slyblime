from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, sexpdata, sly
from .util import *
from .html_dsl.elements import *
from . import custom_elements as X
import logging
import functools
import concurrent.futures
import uuid
import html
import re
from datetime import datetime

from . import ui_view as ui
from . import pydispatch


async def async_run(session, window, **kwargs):
    not_open = kwargs["not_open"] if "not_open" in kwargs else False
    switch = kwargs["switch"] if "switch" in kwargs else False
    try:
        expression = await show_input_panel(
            session.loop, window,
            "Evaluee for inspection:",
            "")
        recent_inspectors = sorted(
            session.inspectors.values(),
            key=lambda i: i.last_modified,
            reverse=True)
        done = False
        for i, inspector in enumerate(recent_inspectors):
            if not_open and inspector.is_open:
                continue
            if not inspector.is_open:
                inspector.reöpen(window)
            if switch:
                window.focus_sheet(inspector.sheet)
            done = True
            await inspector.inspect(expression)
        # No closed inspector is avaliable in pool
        if not done:
            Inspector(session, window, expression)

    except Exception as e:
        print(f"InspectCommandException {e}")


class InspectCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        session = sly.sessions.get_by_window(self.window)
        if session is None: return
        asyncio.run_coroutine_threadsafe(
            async_run(session, self.window, **kwargs), 
            sly.loop)


SPACES_3 = re.compile(r" {3,}")
SPACES_2 = re.compile(r" {2,}")

def escape(string, setting=None):
    escaped = html.escape(string)
    setting = setting or sly.settings().get("inspector")["fixed_spacing"]
    # The simple case
    if setting not in [1, 2]:
        if setting == 0:
            replacement = " "
        elif setting == 3:
            replacement = "&nbsp;"
        else:
            replacement = setting
        return escaped.replace(" ", replacement)
    elif setting == 1:
        matches = SPACES_3.finditer(escaped)
    elif setting == 2:
        matches = SPACES_2.finditer(escaped)
    escaped = list(escaped)
    for match in matches:
        start, end = match.span()
        length = end - start
        escaped[start:end+1] = ["&nbsp;"] * length
    return "".join(escaped)


def url(id, mode, index=None):
    # The use of double curlies must be a joke
    return ui.url(id, {"mode": mode, "index": index})


def linewise(content):
    line = []
    lines = []
    for element in content:
        if element == "\n":
            lines.append(line)
            line = []
        else:
            line.append(element)
    # Watch out for remainder
    if len(line) > 0: 
        lines.append(line)
    return lines

INDICATOR_REGEX = re.compile(r"@\d+(?==)")

def structure_content(id, content):
    # Split content into lines
    lines = linewise(content)
    def present_element(line):
        if type(line) == str:
            return escape(line)
        line_mode = line.type.lower()
        precomputed_url = url(id, line_mode, line.index)
        if line_mode == "value":
            if match := INDICATOR_REGEX.match(line.content):
                indicator = SPAN(_class="sly subscript")[
                    ui.to_subscript_unicode(match.group(0)[1:])
                ]
                start = match.span()[1]+1
            else:
                indicator = ""
                start = 0
            return A(
                _class=f"sly-inspector-link {line_mode}",
                href=precomputed_url)[
                    escape(line.content[start:]),
                    indicator
                ]
        elif line_mode == "action":
            if line.content in ["[ ]", "[X]"]:
                return X.CHECKBOX(checked=line.content == "[X]",
                                  href=precomputed_url)
            else:
                return X.BUTTON(href=precomputed_url)[
                    escape(line.content.strip())[1:-1]
                ]
    return [
        DIV(_class="sly-inspector-field")[
            [SPAN(_class="sly-inspector-label")[
                    present_element(line[0]),
                ], ": ",
                [present_element(element) for element in line[2:]]
            ] if len(line) > 2 and line[1] == ": " 
              else [present_element(element) for element in line],
            BR
        ]
    for line in lines]


def design(id, inspection):
    return HTML[BODY(id="sly-inspector", _class="sly sly-inspector")[
        STYLE[
            load_resource("stylesheet.css")
        ],
        NAV[
            A(_class="browser-button", href=url(id, "browser", "previous"))["←"],
            A(_class="browser-button", href=url(id, "browser", "next"))["→"],
            A(_class="browser-button", href=url(id, "browser", "refresh"))["⟲"],
            A(id="browser-input", href=url(id, "browser", "input"))[escape(inspection.title)]
        ], BR,
        DIV[
            structure_content(id, inspection.content)
        ]
    ]]

def parse_inspector(id, target_inspector):
    if type(target_inspector) == Inspector:
        return target_inspector.id
    elif target_inspector is None:
        return id

class Inspector(ui.UIView):
    def __init__ (self, session, window, query=None, package="COMMON-LISP-USER"):
        super().__init__(window, session)
        self.session.inspectors[self.id] = self
        if query:
            asyncio.run_coroutine_threadsafe(
                self.inspect(query, package), 
                sly.loop)
        self.name = "Sly: Inspector"

    # The main reason `self.html` is not a property is just in case
    # I want to incrementally edit the HTML DOM-style.
    def flip(self):
        self.session.nearest_inspector = self
        super().flip()

    async def inspect(self, query, package=None):
        self.html = design(
            self.id,
            await self.slynk.inspect(query, self.id, self.id, package))
        self.flip()

    async def call_action(self, index, target_inspector=None):
        html = design(
            self.id,
            await self.slynk.inspector_call_action(
                index, 
                self.id,
                (id := parse_inspector(self.id, target_inspector))))
        if id == self.id:
            self.html = html
            self.flip()
        else:
            inspectors[id].html = html
            inspectors[id].flip()

    async def inspect_part(self, index, target_inspector=None):
        html = design(
            self.id,
            await self.slynk.inspect_part(
                index, 
                self.id,
                (id := parse_inspector(self.id, target_inspector))))
        if id == self.id:
            self.html = html
            self.flip()
        else:
            inspectors[id].html = html
            inspectors[id].flip()

    async def previous(self):
        self.html = design(self.id, await self.slynk.inspector_previous(self.id))
        self.flip()

    async def next(self):
        self.html = design(self.id, await self.slynk.inspector_next(self.id))
        self.flip()

    async def reinspect(self):
        self.html = design(self.id, await self.slynk.reinspect(self.id))
        self.flip()

    async def toggle_verbose(self):
        self.html = design(
            self.id, 
            await self.slynk.toggle_verbose_inspection(self.id))
        self.flip()

    async def on_url_press(self, mode, index, **rest):
        if mode == "browser":
            if index == "previous":
                await self.previous()
            elif index == "next":
                await self.next()
            elif index == "refresh":
                await self.reinspect()
            elif index == "input":
                expression = await show_input_panel(
                    self.session.loop, self.window,
                    "Evaluee for inspection:",
                    "")
                await self.inspect(expression)
            else:
                print(f"inspector.py: Unknown query {mode}, {index}, {rest}")
        elif mode == "value":
            await self.inspect_part(int(index))
        elif mode == "action":
            await self.call_action(int(index))

    async def inspect_in_frame(self, frame_index, thread, expression_string=None):
      try:
        if not expression_string:
            self.html = "System ready...\nEnter evaluee for inspection..."
            expression_string = await show_input_panel(
                sly.loop, 
                self.window, 
                f"Evaluee for frame", 
                "")
        data = await self.slynk.inspect_in_frame(
            frame_index, 
            expression_string,
            thread=thread,
            current_inspector=self.id,
            target_inspector=self.id)
        print("REçU OK", data)
        self.html = design(self.id, data)
        self.flip()
      except Exception as e:
        print("InspectorInFrame", e)

    async def inspect_current_condition(self, thread):
      try:
        data = await self.slynk.inspect_current_condition(
            thread=thread,
            current_inspector=self.id,
            target_inspector=self.id)
        print("REçU OK", data)
        self.html = design(self.id, data)
        self.flip()
      except Exception as e:
        print("InspectorOfFrame", e)