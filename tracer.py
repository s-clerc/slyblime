from sublime import *
import sublime_plugin, asyncio 

from dataclasses import dataclass
from typing import *
from math import log, ceil, inf

from . import ui_view as ui
from .sexpdata import *
from .sly import *
from . import slynk, sexpdata
from .util import *
from .html_dsl.elements import *
from . import custom_elements as X
from html import escape

# To enable passing strings by reference
@dataclass
class Reference:
    value: str
    def __str__(self):
        return self.value

SP = "&nbsp;"
NL = "<br>"


def render_as_tree(data):
    # To number each call
    width = ceil(log(data[-1].id, 10)) + 2
    prefixes = [SP * width]
    previous_ids = []
    result: List[List[str]] = []

    for vertex in data:
        for previous_id in reversed(previous_ids):
            if previous_id != vertex.parent_id:
                previous_ids.pop()
                prefixes.pop()
            else:
                break
        result.append(
            [str(vertex.id).rjust(width).replace(" ", SP), 
             *prefixes[1:-1], 
             SP + SP + "├─ ", 
             SPAN(_class="function-name")[escape(vertex.spec[0])]])
        if len(prefixes) > 1:
            prefixes[-1].value = 2 * SP + "│" + SP
            prefixes[-1] = Reference(4 * SP)
        prefixes += [Reference(2 * SP + "┃" + SP)]
        inputs = [[*prefixes, "🠆 ", escape(input)] for input in vertex.arguments]
        outputs = [[*prefixes, "⤆ ", escape(output)] for output in vertex.return_list]
        result += inputs + outputs
        prefixes[-1] = Reference(SP * 4)
        previous_ids.append(vertex.id)

    return NL.join(["".join([str(reference) for reference in resultee]) 
                                     for resultee in result])

class SlyOpenTracerCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)

    async def async_run(self, **q):
      try:
        session = sessions.get_by_window(self.window)
        if session is None: return
        if not (tracer := session.tracer):
            session.tracer = Tracer(self.window, session)
        elif tracer.is_open:
            window = tracer.sheet.window()
            window.focus_sheet(tracer)
            window.bring_to_front()
        else:
            tracer.reöpen(self.window)
      except Exception as e:
        print(e, "nay")

class SlyTraceCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)

    async def async_run(self, mode="toggle", query=None):
        session = sessions.get_by_window(self.window)
        if session is None: return
        if query is None:
            query = await show_input_panel(loop, self.window, "(Un)Trace", "")
        if query is None:
            return
        self.window.status_message(await session.slynk.tracer_toggle(query))

class Tracer(ui.UIView):
    def __init__(self, *args):
      try:
        super().__init__(*args)
        self.tracees = []
        self.tracees_element = None
        self.output_element = None
        self.total_element = None
        self.traces = []
        self.total_traces = 0
        self.name = "Sly: Tracer"

        asyncio.run_coroutine_threadsafe(self.design(), loop)
      except Exception as e:
        print(f"aouaoeu {e}")


    async def design(self):
        self.html = HTML[BODY(_class="sly", id="sly-tracer")[
            STYLE[load_resource("stylesheet.css")],
            DIV(_class="toolbar")[SPAN(_class="title")["Tracees"], " ",
                 X.BUTTON(href=self.url({"action": "untrace-all"}))["Untrace all"], " ",
                 X.BUTTON(href=self.url({"action": "refresh-tracees"}))["Refresh"], " ",
                 X.BUTTON(href=self.url({"action": "add-new"}))["Trace new..."]], " ",
           BR,
            (tracees := DIV(id="tracees")[" "]), " ",
            DIV(_class="toolbar")[SPAN(_class="title")["Tracer Output"], " ", (total := SPAN(_class="total")["0/0"]), " ",
                 X.BUTTON(href=self.url({"action": "refresh-output"}))["Refresh"], " ",
                 X.BUTTON(href=self.url({"action": "delete-output"}))["Clear all"], " ",
                 X.BUTTON(href=self.url({"action": "fetch-next"}))["Fetch next batch"], " ", 
                 X.BUTTON(href=self.url({"action": "fetch-all"}))["Fetch all"]], " ",
            BR,
            (output := DIV(id="output")[" "]),
        ]]
        self.tracees_element = tracees
        self.output_element = output 
        self.total_element = total

        await self.refresh_tracees()
        await self.on_url_press("refresh-output")

    async def refresh_tracees(self):
        try:
            self.tracees = await self.slynk.tracer_report_specs()
            print("OK REP")
        except Exception as e:
            print("repspcEx", e)
        self.tracees_element.clear()
        self.tracees_element += [
            DIV(_class="list-element")[
                [A(_class="icon-button", href=self.url({"action": f"untrace", "index": index}))["×"], 
                f" {tracee[0]}"], BR] for index, tracee in enumerate(self.tracees)]

    async def untrace_tracee(self, index):
        await self.slynk.tracer_untrace(self.tracees[index][1])
        await self.refresh_tracees()

    async def untrace_tracees(self):
        await self.slynk.tracer_untrace_all(self.tracees[index][1])
        await self.refresh_tracees()

    async def fetch(self, mode="next"):
        remainder = inf
        while remainder == inf or (mode == "all" and remainder > 0):
            traces, remainder, __ = await self.slynk.tracer_report_partial_tree(
                f"sublime-sly-tracer-{self.id}")
            self.traces += traces
            print(traces)
            self.output_element[0] += render_as_tree(traces)

    async def erase_output(self):
        self.output_element[0] = " "

    async def on_url_press(self, action, index=None, **rest):
      print("HI37")
      print(action)
      try:
        if "untrace" in action or action in ["refresh-tracees", "add-new"]:
            if action == "add-new":
                self.window.status_message(
                    await self.slynk.tracer_trace(
                        await show_input_panel(loop, self.window, "Function for tracing", "")))
            elif "all" in action:
                await self.slynk.tracer_untrace_all(self.tracees[index][1])
            elif index:
                await self.slynk.tracer_untrace(self.tracees[index][1])
            await self.refresh_tracees()
        elif action == "delete-output":
            await self.slynk.tracer_clear()
            self.output_element[0] = " "
            self.traces = []
        elif action == "fetch-all":
            print("fetch-all")
            await self.fetch("all")
        elif action == "fetch-next":
            await self.fetch()
        #TEMP REMOVE BELOW WHEN POSSIBLE
        elif action == "refresh-output" and len(self.traces) > 0:
            self.output_element[0] = render_as_tree(self.traces)
            
        if action in ["refresh-output", "fetch-all", "fetch-next", "delete-output"]:
            self.total_traces = await self.slynk.tracer_report_total()
            self.total_element[0] = f"{len(self.traces)}/{self.total_traces}"
        self.flip()
      except Exception as e:
        print("OUPE", e)