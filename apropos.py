from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, util, sexpdata
from .sly import *
import logging
import functools
import concurrent.futures

class AproposCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        session = sessions.get_by_window(self.window)
        if session is None: return
        external_only = True if "external_only" not in kwargs else kwargs["external_only"]
        self.window.show_input_panel(
            f"À propos for {'external' if external_only else 'all'} symbols", 
            "", functools.partial(self.confirm, external_only), None, None)

    def confirm(self, external_only, pattern):
        global loop
        if pattern is None:
            return
        asyncio.run_coroutine_threadsafe(self.async_confirm(pattern, external_only), loop)

    async def async_confirm(self, pattern, external_only=True):
        # Maybe this change will result in weird behaviour, idk
        # since the session has already been checked above
        session = sessions.get_by_window(self.window)
        if session is None: 
            print("Unexpected instance of session not existing after apropos return")
            return
        apropos = await session.slynk.apropos(pattern, external_only)
        self.window.status_message(f"Apropos retrieved: {len(apropos)} matching symbols")
        previews = generate_previews(apropos)
        self.window.status_message(f"Apropos previews processed")
        def callback(choice):
            pass
        self.window.show_quick_panel(
            previews,
            functools.partial(self.callback, apropos),
            0b01)
        return 

    def callback(self, apropos, choice):
        designator = apropos[choice]["designator"]
        self.window.active_view().run_command("sly_describe",
            {
                "mode": "symbol",
                "input_source": "given",
                "query": designator[1] + (":" if designator[2] else "::") + designator[0]
            }) 
        

def process_doc(field):
    return "[Undocumented]" if type(field) == sexpdata.Symbol else str(field)

def process_label(label):
    return f"[{str(label).capitalize()}]"

def generate_entry_panel(apropos):
    preselection = ["designator", "bounds", "arglist"]
    designator, bounds, arglist = util.get_if_in(apropos, *preselection)
    entry = [designator[1] + (":" if designator[2] else "::") + designator[0]]
    for label, doc in apropos.items():
        if label in preselection:
            continue
        entry.append(f"{process_label(label)} {process_doc(doc)}")
        if label == "function":
            # So that function and arguments are together
            entry.append(f"[Arguments] {process_doc(arglist)}")
    return entry

def documentation_defined(label, apropos):
    if label not in apropos:
        return False
    doc = apropos[label]
    ## We're assuming that if it's a symbol it's :NOT-DOCUMENTED
    return type(doc) != sexpdata.Symbol

def process_arguments(arglist):
    arguments = sexpdata.loads(arglist)
    result = [0, 0, 0]
    current_section = 0
    for symbol in arguments:
        symbol = str(symbol).lower()
        if symbol == "&optional":
            current_section = 1
        elif symbol == "&key":
            current_section == 2
        else:
            result[current_section] += 1
    return result

def generate_previews(apropos):
    content = [["Open as view", f"Not yet implemented {len(apropos)} symbols."]]
    max_lines = 1
    for apropo in apropos:
        entry = generate_preview(apropo)
        if len(entry) > max_lines:
            max_lines = len(entry)
        content.append(entry)
    for i in range(len(content)):
        entry = content[i]
        if len(entry) < max_lines:
            for j in range(max_lines - len(entry)):
                entry.append("")
    return content

def generate_preview(apropos):
    preselection = ["designator", "bounds"]
    designator, bounds = util.get_if_in(apropos, *preselection)
    entry = [designator[1] + (":" if designator[2] else "::") + designator[0]]
    if documentation_defined("type", apropos):
        entry.append(f"[Type] {process_doc(apropos['type'])}")
        preselection.append("type")
    elif documentation_defined("function", apropos):
        if "arglist" in apropos:
            arguments = process_arguments(apropos["arglist"])
            arguments_string = f"{arguments[0]}·{arguments[1]}·{arguments[2]}"
        else:
            arguments_string = "0"
        entry.append(f"[Function {arguments_string}] {process_doc(apropos['function'])}")
        preselection.append("function")
        preselection.append("arglist")
    elif documentation_defined("arglist", apropos):
        entry.append(f"[Function Argslist] {process_doc(apropos['arglist'])}")
        preselection.append("function")
        preselection.append("arglist")
    elif documentation_defined("variable", apropos):
        entry.append(f"[Variable] {process_doc(apropos['variable'])}")
        preselection.append("variable")
    entry.append("")
    for label, doc in apropos.items():
        if label in preselection:
            continue
        label = process_label(label)
        if len(entry[len(entry)-1]) + len(label) > settings().get("apropos")["max_width"]:
            entry.append(label)
        else:
            entry[len(entry)-1] += f" {label}"
    return entry





