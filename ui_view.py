import asyncio
from sublime import *
import sublime_plugin
from .html_dsl.elements import *
from . import custom_elements as X
import uuid
from datetime import datetime
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
        print(q)
        print(VIEWS)
        view = VIEWS[q["id"]]
        print(view)
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
        self.sheet = window.new_html_sheet("UiView", self.html)

    @property
    def is_open(self):
        return self.sheet.window() is not None


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