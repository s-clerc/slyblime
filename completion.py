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

def determine_display(namespaces, classifier):
    for π in classifier.classifications:
        if not π.compiled_regex.match(namespaces[0]):
            continue
        # Following computations are used everywhere
        is_short = len(namespaces) < 2
        description = " ".join([flavor.capitalize() for flavor in namespaces])
        
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
    return CompletionItem(
        trigger=completion.name,
        completion=completion.name,
        completion_format=COMPLETION_FORMAT_TEXT,
        kind=kind,
        annotation=annotation,
        details=f"Match: {int(completion.probability*1000)} ‰")

def get_classifier(syntax):
    classifiers = sly.settings().get("completion")["classifiers"]
    for classifier in classifiers:
        print(classifier["syntax_regex"])
        if re.findall(classifier["syntax_regex"], syntax):
            return convert_classifier(classifier)

def convert_classifier(classifier):
    def prepare_classification(classification):
        classification = Classification(**classification)
        classification.compiled_regex = re.compile(classification.regex)
        return classification
    return Classifier(
        classifier["name"],
        classifier["syntax_regex"],
        [prepare_classification(c) for c in classifier["classifications"]],
        classifier["symbol_for_homonyms"])

class SlyCompletionListener(sublime_plugin.EventListener):
    def on_query_completions(self, view, pattern, locations):
        if not (classifier := get_classifier(view.settings().get("syntax"))):
            print(f"Cannot class {classifier}")
            return None
        session = sly.getSession(view.window().id())
        try:
            completions = asyncio.run_coroutine_threadsafe(
                session.slynk.completions(pattern), 
                session.loop).result(sly.settings().get("maximum_timeout"))
        except Exception as e:
            session.window.status_message("Failed to fetch completion")
            print(e)
            return
        return ([create_completion_item(completion, classifier) for completion in completions],
                INHIBIT_WORD_COMPLETIONS|INHIBIT_EXPLICIT_COMPLETIONS)

