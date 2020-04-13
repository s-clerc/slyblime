from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, util, sexpdata, sly
import logging
import functools
import uuid
from html import escape

from . import pydispatch
from dataclasses import dataclass



@dataclass
class DisplayCompletion:
    indicator: int = KIND_ID_AMBIGUOUS
    symbol: str = ""
    annotation: str = ""
    boxed_type: str = ""

def convert_display_completion(display_completion):
    return ((display_completion.indicator,
             display_completion.symbol,
             display_completion.boxed_type),
            display_completion.annotation)

def determine_kind(kinds):
    type = kinds[0] if len(kinds) > 0 else None
    def kind(indicator, symbol, long_symbol=False, short_annotation=False, short_box=False):
        nonlocal kinds
        is_short = len(kinds) < 2
        description = " ".join([kind.capitalize() for kind in kinds])
        return DisplayCompletion(
                indicator, 
                symbol if is_short or long_symbol else "…", 
                description if short_annotation or not is_short else "",
                description if short_box or not is_short else "")

    result = None
    if type == "fn":
        result = kind(KIND_ID_FUNCTION, "")
    elif type == "generic-fn":
        result = kind(KIND_ID_FUNCTION, "g")
    elif type == "var":
        result = kind(KIND_ID_VARIABLE, "")
    elif type == "type": 
        result = kind(KIND_ID_TYPE, "")
    elif type == "pak":
        result = kind(KIND_ID_NAMESPACE, "")
    elif type == "cla":
        result = kind(KIND_ID_AMBIGUOUS, "C")
    elif type == "macro":
        result = kind(KIND_ID_AMBIGUOUS, "⎈", short_box=True)
    elif type == "constant":
        result = kind(KIND_ID_VARIABLE, "π", short_box=True)
    # It seems like most special operators are also functions os
    elif type == "special-op" and (len(kinds) < 2 or kinds[1] == "fn"):
        result = kind(KIND_ID_KEYWORD, "⎇", True)
    else:
        result = kind(KIND_ID_AMBIGUOUS, "", short_box=True)

    if len(kinds[0]) == 0:
         result.boxed_type = "​Unknown"
    return convert_display_completion(result)

def create_completion_item(completion):
    kind, annotation = determine_kind(completion.kind)
    return CompletionItem(
        trigger=completion.name,
        completion=completion.name,
        completion_format=COMPLETION_FORMAT_TEXT,
        kind=kind,
        annotation=annotation,
        details=f"Match: {int(completion.probability*1000)} ‰")

class SlyCompletionListener(sublime_plugin.EventListener):
    def should_complete(self, view):
        return "LISP" in view.settings().get("syntax").upper()

    def on_query_completions(self, view, pattern, locations):
        if not self.should_complete(view):
            return None
        session = sly.getSession(view.window().id())
        try:
            completions = asyncio.run_coroutine_threadsafe(
                session.slynk.completions(pattern), 
                session.loop).result(sly.settings.get("maximum_timeout"))
        except Exception as e:
            session.window.status_message("Failed to fetch completion")
            print(e)
            return
        return ([create_completion_item(completion) for completion in completions],
                INHIBIT_WORD_COMPLETIONS|INHIBIT_EXPLICIT_COMPLETIONS)

