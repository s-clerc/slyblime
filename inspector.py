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

from . import pydispatch

if "futures" not in globals():
    futures = {}
    inspectors = {}
    nearest_inspector = None


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
        print(recent_inspectors)
        print(session.inspectors)
        done = False
        for i, inspector in enumerate(recent_inspectors):
            if not_open and inspector.is_open:
                continue
            if not inspector.is_open:
                print("reöpening")
                inspector.reöpen(window)
            if switch:
                window.focus_sheet(inspector.sheet)
            done = True
            await inspector.inspect(expression)
        # No closed inspector is avaliable in pool
        if not done:
            Inspector(session, window, expression)

    except Exception as e:
        print(e)


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

INDICATOR_REGEX = re.compile(r"@\d+(?==)")

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
                    to_subscript_unicode(match.group(0)[1:])
                ]
                start = match.span()[1]+1
            else:
                indicator = ""
                start=0
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

class InspectorSheetUrlCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            sly.loop)

    async def async_run(self, **q):
      try:
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
                session = sly.sessions.get_by_window(self.window)
                if session is None: return
                expression = await show_input_panel(
                    session, self.window,
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
        self.slynk = session.slynk
        self.html = "System ready..."
        self.id = uuid.uuid4().hex
        self.last_modified = datetime.now()
        self.reöpen(window)
        inspectors[self.id] = self
        self.session.inspectors[self.id] = self
        if query:
            asyncio.run_coroutine_threadsafe(
                self.inspect(query, package), 
                sly.loop)

    # The main reason `self.html` is not a property is just in case
    # I want to incrementally edit the HTML DOM-style.
    def flip(self):
        global nearest_inspector
        self.sheet.set_contents(str(self.html))
        self.session.nearest_inspector = self
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

    def reöpen(self, window):
        self.sheet = window.new_html_sheet("inspection", "System ready...")

    @property
    def is_open(self):
        return self.sheet.window() is not None
    
    async def inspect(self, query, package=None):
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



