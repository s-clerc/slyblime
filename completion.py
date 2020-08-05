from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from typing import *

from . import slynk, util, sexpdata, sly
import logging
import functools
import uuid
from html import escape
import re
from . import pydispatch
from dataclasses import dataclass, make_dataclass

@dataclass
class Classification:
    regex: str
    kind: str = KIND_ID_AMBIGUOUS
    symbol: str = ""
    long_symbol: bool = False
    short_annotation: bool = False
    short_box: bool = False
    compiled_regex: re.Pattern = None

@dataclass
class Classifier:
    name: str
    syntax_regex: str
    classifications: List[Classification]
    symbol_for_homonyms: str = ""
    separator: str = ""

@dataclass
class DisplayCompletion:
    indicator: int = KIND_ID_AMBIGUOUS
    symbol: str = ""
    annotation: str = ""
    boxed_type: str = ""

def convert_display_completion(display_completion) -> Tuple[int, str, str, str]:
    return ((display_completion.indicator,
             display_completion.symbol,
             display_completion.boxed_type),
            display_completion.annotation)

def determine_display(namespaces, classifier) -> DisplayCompletion:
    for π in classifier.classifications:
        if not π.compiled_regex.match(namespaces[0]):
            continue
        # Following computations are used everywhere
        is_short = len(namespaces) < 2
        description = classifier.separator.join([flavor.capitalize() for flavor in namespaces])
        
        # We need to make sure that if there is no namespaces information
        # we shown "unknown" in the typebox.
        if len(namespaces[0]) == 0:
            # A zero-width space is used to avoid
            # overwriting the empty symbol
            boxed_type = "​Unknown"
        elif π.short_box or not is_short:
            boxed_type = description
        else:
            boxed_type = ""

        return DisplayCompletion(
            globals()[π.kind], 
            π.symbol if is_short or π.long_symbol else classifier.symbol_for_homonyms, 
            description if π.short_annotation or not is_short else "", 
            boxed_type)

def create_completion_item(completion, classifier):
    kind, annotation = convert_display_completion(determine_display(completion.namespaces, classifier))
    name = completion.name
    return CompletionItem(
        trigger=name,
        completion=name,
        completion_format=COMPLETION_FORMAT_TEXT,
        kind=kind,
        annotation=annotation,
        details=f'<a href=\'subl:sly_completion_info {{"completion": "{name}"}}\'> M</a>atch: {int(completion.probability*1000)} ‰')

def get_classifier(syntax: str) -> Classifier:
    classifiers = sly.settings().get("completion")["classifiers"]
    for classifier in classifiers:
        if re.findall(classifier["syntax_regex"], syntax):
            return convert_classifier(classifier)

def convert_classifier(classifier: Dict) -> Classifier:
    def prepare_classification(classification) -> Classification:
        classification = Classification(**classification)
        classification.compiled_regex = re.compile(classification.regex)
        return classification
    return Classifier(
        classifier["name"],
        classifier["syntax_regex"],
        [prepare_classification(c) for c in classifier["classifications"]],
        classifier["symbol_for_homonyms"],
        classifier["separator"])

class SlyCompletionListener(sublime_plugin.EventListener):
    def on_query_completions(self, view, pattern, locations) -> Tuple[List[CompletionItem], int]:
        if not (classifier := get_classifier(view.settings().get("syntax"))):
            return None
        # Failure will not be indicated because it would be incredibly annoying otherwise
        session = sly.sessions.get_by_window(view.window(), indicate_failure=False)
        if session is None: return

        try:
            completions = asyncio.run_coroutine_threadsafe(
                session.slynk.completions(
                    pattern,
                    util.current_package(view) or "COMMON-LISP-USER"), 
                session.loop).result(sly.settings().get("maximum_timeout"))
        except Exception as e:
            session.window.status_message(f"Failed to fetch completion for {pattern}")
            print(f"Completion fetch exception: {e}")
            return
        return ([create_completion_item(completion, classifier) for completion in completions],
                INHIBIT_WORD_COMPLETIONS|INHIBIT_EXPLICIT_COMPLETIONS|DYNAMIC_COMPLETIONS)


class SlyCompletionInfoCommand(sublime_plugin.TextCommand):
    def run(self, edit, completion):
        asyncio.run_coroutine_threadsafe(
            self.async_run(edit, completion), sly.loop)

    async def async_run(self, edit, completion):
        session = sly.sessions.get_by_window(self.view.window())
        if session is None: 
            return
        docs = await session.slynk.documentation_symbol(completion, util.current_package(self.view))
        docs = escape(docs).replace("\n", "<br>")
        self.view.show_popup(str(docs), COOPERATE_WITH_AUTO_COMPLETE)

