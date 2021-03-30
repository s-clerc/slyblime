import asyncio
from bisect import bisect_left
import re
from math import inf

# Needed because we shadow one thing from the default ST stuff
import sublime
from sublime import *
from typing import *

from .sexpdata import loads, dumps

import uuid

def get_if_in(dictionary, *items):
    return tuple(dictionary[item] if item in dictionary else None 
                                  for item in items)

async def show_input_panel(loop, window, prompt, initial_value, on_change=None):
    future = loop.create_future()
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
    if settings.get("is-sly-repl") and (package := settings.get("package")):
        if return_region:
            return package, Region(settings.get("prompt-region")[0], settings.get("prompt-region")[1])
        return package
    else:
        if not point:
            point = view.sel()[0].begin()
        region = find_closest_before_point(view, point, PACKAGE_REGEX)
        # Remove the IN-PACKAGE symbol.
        if region is None: 
            if return_region: 
                return None, None 
            return None

        info = IN_PACKAGE_REGEX.sub("", view.substr(region)[1:-1])

        if return_region:
            return info, region
        return info


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


def set_status(view, session):
    if session:
        slynk = session.slynk
        message = [
            "[",
            slynk.connexion_info.lisp_implementation.name,
            "] ",
            slynk.host, 
            ":",
            str(slynk.port)]
    else:
        message = []
    view.set_status("slynk", "".join(message))



def in_lisp_file(view, settings: Callable):
    matches = re.findall(
        settings().get("compilation")["syntax_regex"], 
        view.settings().get("syntax"))
    return len(matches) > 0


"""
    Below we have two functions which determine the form.
    While `find_containing_form` could do both, the algorithm in
    `find_toplevel_form` is far more efficent because it uses
    expand_scope and so it skips much of the text.
    
    In addition `find_containing_form is vulnerable to escaped brackets if the
    sublime-syntax doesn't distinguish them from delimiting brackets.
"""
SCOPE_REGEX = re.compile(r"(meta.(parens|section))")

def get_scopes(view, point):
    return view.scope_name(point).strip().split(" ")
    
def determine_depth(scopes):
    depth = 0
    for scope in scopes:
        # TODO: replace with customisable regex
        if SCOPE_REGEX.match(scope):
            depth += 1
    return depth

def find_toplevel_form(view, point: int=None, max_iterations=100) -> Optional[Region]:
    point = point or view.sel()[0].begin()
    region = view.extract_scope(point)
    # It only has the scope of the file, so its outside
    # a toplevel form, we need to find one.
    if len(get_scopes(view, point)) == 1:
        region = find_closest_before_point(view, point, r"\S")
        distance_to_first = point - region.end() 
        region1 = view.find(r"\S", point) # finds closest after point
        if (point - region.end()) >= (region1.begin() - point):
            region = region1
    """
     This algorithm will go through a form, going to the start
     of every scope and checking if it is of form 
     ["source.lisp", "meta.parens.lisp"] or something*
     at which point it'll return the region. Otherwise, it
     keeps on expanding the scope
    
     *deliberately vague in the while statement to allow for different
     syntax scoping (e.g. "source.cl" or "source.scm").
    """
    point: int = region.begin()
    scopes: str = get_scopes(view, point)
    depth: int = determine_depth(scopes)
    previous_region = Region(-1, -1)
    iterations = 0
    forward = True
    def should_continue():
        return ((depth > 1 or len(scopes) > 2)
                  and iterations < max_iterations)
    while should_continue():
        if previous_region != region:
            point = region.begin() if forward else region.end()
        else:
            point += -1 if forward else +1

        scopes = get_scopes(view, point)
        depth = determine_depth(scopes)
        previous_region = region
        region = view.extract_scope(point)
        iterations += 1
        # We check if we reached the "(" of a top-level form
        # and if we did we go the opposite way until we find
        # a scope where the extract_scope is the top-level form
        if len(scopes) == 3 and "begin" in scopes[2]:
            forward = False
    if depth == 1:
        return region
    elif iterations >= max_iterations:
        raise RuntimeWarning("Search iterations exceeded")
    else:
        return None

def find_containing_form(view, point: int=None, max_iterations=1000) -> Optional[Region]:
    point = point or view.sel()[0].begin()
    def find_extremity(point:int, direction: int, enter_scope: str, exit_scope: str):
        unclosed_meta_scopes = 0
        for i in range(0, max_iterations):
            region = view.word(point)
            word = view.substr(region)
            if not ("(" in word or ")" in word):
                if direction > 0:
                    point = region.end()
                elif direction < 0:
                    point = region.begin()
            *__, scope = get_scopes(view, point)
            if enter_scope in scope:
                unclosed_meta_scopes += 1
            elif exit_scope in scope:
                if unclosed_meta_scopes == 0:
                    return point
                unclosed_meta_scopes -= 1
            point += direction
        return None
    start = find_extremity(point, -1, "parens.end", "parens.begin")
    end = find_extremity(point, 1, "parens.begin", "parens.end")
    # Plus one because regions are [x .. y) intervals
    return Region(start, end+1) if start and end else None


def event_to_point(view, event: Dict[str, int]) -> Tuple[int]:
    return view.window_to_text((event["x"], event["y"]))

def nearest_region_to_point (point: int, regions: Iterable[Region]) -> Optional[Region]:
    if len(regions) == 0:
        return None
    minimal_distance = inf
    for region in regions:
        distance = min(
            abs(region.begin() - point), 
            abs(region.end() - point))
        if distance < minimal_distance:
            result = region
            if result.contains(point):
                break
    return result

def open_file_at(window, path, point, always_reopen=False):
    view = window.find_open_file(path)
    if view is None or always_reopen:
        view = window.open_file(path)
    window.focus_view(view)
    # To deal with weird thread stuff, we call it back.
    set_timeout(
        lambda: view.show_at_center(point),
        10)
    return view

SYMBOL_ENDING_CHARACTERS = re.compile(r"""([ ()"']|\\)""")

"""
Once I get around to rewriting the grammar this can be replaced by a simple
extract scope as all symbols (even non-enclosed) will be scoped properly.

This is technically imperfect as when we have something like `test\⁁'test`
it will return ["", ""] but this is good enough in my opinion. (⁁ is the 
point).
"""
def symbol_at_point(view, point:int=None, seperated=False) -> Union[List[str], str]:
    if point is None:
        point = view.sel()[0].begin()
    scope_name = view.scope_name(point)

    if "symbol.enclosed" in scope_name:
        print("enclosed")
        if "end" in scope_name:
            point -= 1
        scope = view.extract_scope(point)
        left_side = view.substr(Region(scope.begin(), point))
        right_side = view.substr(Region(point, scope.end()))
        if right_side[-1:] == "\n":
            right_side = right_side[-1]

        if seperated:
            return [left_side, right_side]
        return left_side + right_side

    is_left_at_end = False
    left_position = point
    left_needs_escape = False
    is_right_at_end = False
    right_position = point-1
    right_can_escape = False

    left_side = ""
    right_side = ""
    size = view.size()

    for __ in range(50):
        if not is_left_at_end:
            if left_position == 0: 
                is_left_at_end = True

            word_region = Region(view.word(left_position).begin(), left_position)
            if not left_needs_escape and len(word_region) > 1:
                left_side = view.substr(word_region) + left_side
                left_position = word_region.begin()
            else:
                left_position -= 1
                left = view.substr(left_position)
                is_symbol_ending = SYMBOL_ENDING_CHARACTERS.match(left)
                if left_needs_escape:
                    if left == "\\":
                        left_needs_escape = False
                        left_side = left + left_side
                    else:
                        left_side = left_side[1:]
                        is_left_at_end = True
                elif is_symbol_ending and left_position != 0:
                    left_needs_escape = True
                    left_side = left + left_side
                else:
                    left_side = left + left_side

        if not is_right_at_end:
            if right_position+1 == size:
                is_right_at_end = True
            word_region = Region(right_position+1, view.word(right_position).end())
            if not right_can_escape and len(word_region) > 1:
                right_side += view.substr(word_region)
                right_position = word_region.end()-1
            else:
                right_position += 1
                right = view.substr(right_position)
    
                is_symbol_ending = SYMBOL_ENDING_CHARACTERS.match(right)
                if is_symbol_ending:
                    if right_can_escape:
                        right_side += right
                        right_can_escape = False
                    elif right == "\\":
                        right_side += right
                        right_can_escape = True
                    else:
                        is_right_at_end = True
                else:
                    right_side += right
                    right_can_escape = False
    
        if is_left_at_end and is_right_at_end:
            print(__)
            if seperated:
                return [left_side, right_side]
            return left_side+right_side
    return None





