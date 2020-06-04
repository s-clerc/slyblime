from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, sexpdata, sly
from .util import *
from .html_dsl.elements import *
import logging
import functools
import concurrent.futures
import uuid
import html
from datetime import datetime

from . import pydispatch

if "futures" not in globals():
    futures = {}
    inspectors = {}
    nearest_inspector = None


async def async_run(session, window, **kwargs):
    new = kwargs["new"] if "new" in kwargs else False
    switch = kwargs["switch"] if "switch" in kwargs else False
    try:
        expression = await show_input_panel(
            session,
            "Evaluee for inspection:",
            "")
        if new or not nearest_inspector:
            Inspector(session, window, expression)
        else:
            if switch:
                window.focus_sheet(nearest_inspector.sheet)
            await nearest_inspector.inspect(expression)

    except Exception as e:
        print(e)


class InspectCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            async_run(sly.getSession(self.window.id()), self.window, **kwargs), 
            sly.loop)


SPACES_3 = re.compile(r" {3,}")
SPACES_2 = re.compile(r" {2,}")

def escape(string, setting=None):
    escaped = html.escape(string)
    setting = setting or settings().get("inspector")["fixed_spacing"]
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
    return f'subl:inspector_sheet_url {{"id":"{id}", "mode": "{mode}", "index": "{index}"}}'


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


def structure_content(id, content):
    # Split content into lines
    lines = linewise(content)
    def present_element(line):
        if type(line) == str:
            return escape(line)
        link_action = line.type.lower()
        return A(
            _class=f"sly-inspector-link {link_action}",
            href=url(id, link_action, line.index))[escape(line.content)]

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

class InspectorSheetUrlCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            sly.loop)

    async def async_run(self, **q):
      try:
        print(q)
        q = slynk.util.DictAsObject(q)
        inspector = inspectors[q.id]
        if q.mode == "browser":
            if q.index == "previous":
                await inspector.previous()
            elif q.index == "next":
                await inspector.next()
            elif q.index == "refresh":
                await inspector.reinspect()
            elif q.index == "input":
                expression = await show_input_panel(
                    sly.getSession(self.window.id()),
                    "Evaluee for inspection:",
                    "")
                await inspector.inspect(expression)
            else:
                print(f"Inspector.py: Unknown query {q}")
        elif q.mode == "value":
            await inspector.inspect_part(int(q.index))
        elif q.mode == "action":
            await inspector.call_action(int(q.index))
        else:
            print(f"Inspector.py: Unknown query {q}")
      except e as Exception:
        print(e)


def parse_inspector(id, target_inspector):
    if type(target_inspector) == Inspector:
        return target_inspector.id
    elif target_inspector is None:
        return id

class Inspector():
    def __init__ (self, session, window, query=None, package="COMMON-LISP-USER"):
        self.session = session
        self.window = window
        self.slynk = session.slynk
        self.html = "System ready..."
        self.sheet = self.window.new_html_sheet("inspection", self.html)
        self.id = uuid.uuid4().hex
        self.last_modified = datetime.now()
        inspectors[self.id] = self
        if query:
            asyncio.run_coroutine_threadsafe(
                self.inspect(query, package), 
                sly.loop)

    def flip(self):
        print(repr(self.html))
        global nearest_inspector
        self.sheet.set_contents(str(self.html))
        nearest_inspector = self
        self.last_modified = datetime.now()

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

    async def inspect(self, query, package=None):
        print("hi")
        try:
            self.html = design(
                self.id,
                await self.slynk.inspect(query, self.id, self.id, package))
        except Exception as e:
            print(e)
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



