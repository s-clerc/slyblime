import asyncio
from bisect import bisect_left
import re

import sublime
from sublime import *

from .sexpdata import loads, dumps

import uuid

def get_if_in(dictionary, *items):
    return tuple(dictionary[item] if item in dictionary else None 
                                  for item in items)

async def show_input_panel(loop, window, prompt, initial_value, on_change=None):
    future = loop.create_future()
    print("OK")
    def on_confirm(value):
        nonlocal future
        async def set_result(future, value):
            future.set_result(value)
        asyncio.run_coroutine_threadsafe(set_result(future, value), loop)
    def on_cancel():
        nonlocal future
        async def set_result(future):
            future.cancel()
        asyncio.run_coroutine_threadsafe(set_result(future), loop)
    window.show_input_panel(prompt, initial_value, on_confirm, on_change, on_cancel)
    await future
    return future.result()

async def show_quick_panel(loop, window, items, flags, selected_index=0, on_highlighted=None):
    future = loop.create_future()
    def on_done(index):
        nonlocal future
        async def set_result(future, index):
            future.set_result(index)
        asyncio.run_coroutine_threadsafe(set_result(future, index), loop)
    window.show_quick_panel(items, on_done, flags, selected_index, on_highlighted)
    await future
    return future.result()


def find_closest_before_point(view, point, regex):
    possibilities = view.find_all(regex)
    if len(possibilities) == 0: 
        return None
    i = bisect_left(
        [possibility.begin() for possibility in possibilities], 
        point) - 1
    if i < 0:
        return None
    return possibilities[i]


# Prefer before is used to determine which value to send in the event of
# two regions equidistant from the point
def find_closest(view, point, regex, prefer_before=True):
    possibilities = view.find_all(regex)
    if len(possibilities) == 0: 
        return None
    i = bisect_left(
        [possibility.begin() for possibility in possibilities], 
        point)
    if i < -1:
        return None
    elif i == 0:
        return possibilities[i]
    elif i >= len(possibilities):
        return possibilities[i-1]

    before_point = possibilities[i-1]
    after_point = possibilities[i]
    distance = point - before_point.end()
    distance1 = after_point.begin() - point

    if distance < distance1:
        return before_point
    elif distance1 < distance:
        return after_point
    elif prefer_before:
        return before_point
    else:
        return after_point

PACKAGE_REGEX = r"(?i)^\((cl:|common-lisp:)?in-package\ +[ \t']*([^\)]+)[ \t]*\)"
IN_PACKAGE_REGEX = re.compile(r"(?i)(cl:|common-lisp:)?in-package\ +[ \t']*")


# Equivalent to Sly Current Package
def current_package(view, point=None, return_region=False):
    settings = view.settings()
    if settings.get("sly-repl") and (package := settings.get("package")):
        if return_region:
            # TODO: Find a way to get the region before the prompt and indicate as package
            return package, Region(settings.get("prompt-region")[0], settings.get("prompt-region")[1])
        return package
    else:
        if not point:
            point = view.sel()[0].begin()
        region = find_closest_before_point(view, point, PACKAGE_REGEX)
        # Remove the IN-PACKAGE symbol.
        if region is None: 
            if return_region: return None, None 
            return None

        info = IN_PACKAGE_REGEX.sub("", view.substr(region)[1:-1])

        if return_region:
            return info, region


def compute_flags(flags):
    computed_flags = 0
    for flag in flags:
        computed_flags = computed_flags | globals()[flag.upper()]
    return computed_flags


def safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return None


def load_resource(path):
    return sublime.load_resource(f"Packages/{__name__.split('.')[0]}/{path}")


def add_regions_temporarily(view, regions, duration, *args):
    id = uuid.uuid4().hex
    view.add_regions(id, regions, *args)
    set_timeout_async(lambda: view.erase_regions(id), duration)


def highlight_region (view, region, config, duration=None, *args):
    if not duration:
       duration = config['duration'] * 1000
    add_regions_temporarily(view, [region], duration, *args)