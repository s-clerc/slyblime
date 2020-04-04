from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, util, sexpdata
from .slims import *
import logging
import functools
import concurrent.futures

class AproposCommand(sublime_plugin.WindowCommand):

    def run(self, external_only=True):
        try:
            session = getSession(self.window.id())
        except:
            self.window.status_message("Slynk not connected")
            global sessions
            print(window.id, sessions)
        print(external_only)
        self.window.show_input_panel(f"À propos for {'external' if external_only else 'all'} symbols", "", functools.partial(self.confirm, external_only), None, None)

    def confirm(self, external_only, pattern):
        global loop
        if pattern is None:
            return
        asyncio.run_coroutine_threadsafe(self.async_confirm(pattern, external_only), loop)

    async def async_confirm(self, pattern, external_only=True):
        print(f"ext {external_only}")
        session = getSession(self.window.id())
        apropos = await session.slynk.apropos(pattern, external_only)
        self.window.status_message(f"Apropos retrieved: {len(apropos)} matching symbols")
        previews = generate_previews(apropos)
        self.window.status_message(f"Apropos previews processed")
        self.window.show_quick_panel(
            previews,
            self.run_inspector,
            0b01)
        return 

    def run_inspector(self, choice):
        self.window.status_message(f"Run inspector is not yet implemented: {choice}")

class AproposAllCommand(AproposCommand):
    # Because window.run_commad wasn't passing arguments at the time of
    # coding.
    def run(self):
        super().run(False)

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
        if len(entry[len(entry)-1]) + len(label) > 60:
            entry.append(label)
        else:
            entry[len(entry)-1] += f" {label}"
    return entry





