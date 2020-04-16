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

PACKAGE_REGEX = r"(?i)^\((cl:|common-lisp:)?in-package\ +[ \t']*([^\)]+)[ \t]*\)"
IN_PACKAGE_REGEX = re.compile(r"(?i)(cl:|common-lisp:)?in-package\ +[ \t']*")

# I misunderstood what SLY-CURRENT-PACKAGE did and wrote this
# but use the one below this one as this one is not tested.
def determine_package_at_point(view, slynk, point):
    possibilities = view.find_all(PACKAGE_REGEX)
    i = bisect_left(
        [possibility[1] for possibility in possibilities], 
        point) - 1
    if i < 0:
        return None
    # Ignore the IN-PACKAGE symbol.
    statement = loads(view.substr(possibilities[i]))[1:]
    lisp = slynk.connexion_info.lisp_implementation.name
    
    ignore_next = False
    for symbol in statement:
        prefix = (symbol := str(symbol))[0:2]

        if ignore_next: 
            ignore_next = False
        elif symbol == f"#-{lisp}":
            ignore_next = True
        elif prefix == "#+" and symbol != f"#+{lisp}":
            ignore_next = True
        else:
            return symbol

# Equivalent to SLY-CURRENT-PACKAGE in output.
def in_package_parameters_at_point(view, point):
    possibilities = view.find_all(PACKAGE_REGEX)
    i = bisect_left(
        [possibility.begin() for possibility in possibilities], 
        point) - 1
    if i < 0:
        return None
    # Remove the IN-PACKAGE symbol.
    return IN_PACKAGE_REGEX.sub("", view.substr(possibilities[i])[1:-1])



