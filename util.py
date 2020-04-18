import asyncio
from bisect import bisect_left
import re

from .sexpdata import loads, dumps

def get_if_in(dictionary, *items):
    return tuple(dictionary[item] if item in dictionary else None 
                                  for item in items)

async def show_input_panel(session, prompt, initial_value, on_change=None):
    future = session.loop.create_future()
    print("OK")
    def on_confirm(value):
        nonlocal future
        nonlocal session
        async def set_result(future, value):
            future.set_result(value)
        asyncio.run_coroutine_threadsafe(set_result(future, value), session.loop)
    def on_cancel():
        nonlocal future
        nonlocal session
        async def set_result(future):
            future.cancel()
        asyncio.run_coroutine_threadsafe(set_result(future), session.loop)
    session.window.show_input_panel(prompt, initial_value, on_confirm, on_change, on_cancel)
    await future
    return future.result()

async def show_quick_panel(session, items, flags, selected_index=0, on_highlighted=None):
    future = session.loop.create_future()
    print("OK")
    def on_done(index):
        nonlocal future
        nonlocal session
        async def set_result(future, index):
            future.set_result(index)
        asyncio.run_coroutine_threadsafe(set_result(future, index), session.loop)
    session.window.show_quick_panel(items, on_done, flags, selected_index, on_highlighted)
    await future
    return future.result()


def find_closest_before_point(view, point, regex):
    possibilities = view.find_all(regex)
    i = bisect_left(
        [possibility.begin() for possibility in possibilities], 
        point) - 1
    if i < 0:
        return None
    return possibilities[i]


PACKAGE_REGEX = r"(?i)^\((cl:|common-lisp:)?in-package\ +[ \t']*([^\)]+)[ \t]*\)"
IN_PACKAGE_REGEX = re.compile(r"(?i)(cl:|common-lisp:)?in-package\ +[ \t']*")

# Equivalent to SLY-CURRENT-PACKAGE in output.
def in_package_parameters_at_point(view, point, return_region=False):
    region = find_closest_before_point(view, point, PACKAGE_REGEX)
    # Remove the IN-PACKAGE symbol.
    if region is None: 
        if return_region: return None, None 
        return region

    info = IN_PACKAGE_REGEX.sub("", view.substr(region)[1:-1])

    if return_region:
        return info, region



