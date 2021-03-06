from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, util, sexpdata, sly
import logging
import functools
import concurrent.futures
import uuid
from html import escape

from . import pydispatch
from .html_dsl.elements import *
from . import custom_elements as X
from . import ui_view as ui
from . import output_commands
from .inspector import Inspector

class Debugger(ui.UIView):
    def __init__(self, window, session, thread):
        super().__init__(window, session)
        self.session.debuggers[thread] = self
        self.data = None
        self.current_locals = None

    def describe(self, index=None):
        return (f"Error: {self.data.title}\n"
                f"Type: {self.data.type}\n"
                f"Thread: {self.data.thread}\n"
                f"Level: {self.data.level}\n"
                f"Frame: {self.data.stack_frames[index].description if index is not None else 'unspecified here'}")

    def update(self, data):
        self.current_locals = None
        self.data = data
        affixes = sly.settings().get("debugger")["view_title_affixes"]
        self.name = affixes[0] + str(data.level) + affixes[1]
        affixes = sly.settings().get("debugger")["header_affixes"]

        self.html = HTML[BODY(_class="sly sly-debugger")[
            STYLE[util.load_resource("stylesheet.css")],
            H1[escape(affixes[0]+str(data.level)+affixes[1])],
            H2[escape(data.title)],
            H3[escape(data.type), " in thread ", escape(str(data.thread))],
            X.BUTTON(href=self.url({"action": "inspect-condition"}))["Inspect condition"], " ",
            X.BUTTON(href=self.url({"action": "copy-condition"}))["Copy condition"], " ",
            X.BUTTON(href=self.url({"action": "copy-all"}))["Copy all"], " ",
            H4["Restarts"],
            (restarts := OL(start="0")),
            H4["Backtrace"],
            (frames := OL(start="1"))
        ]]
        # Restarts
        for index, restart in enumerate(data.restarts):
            label = restart[0].lower().capitalize()
            if len(label) > 0 and label[0] == "*":
                is_preferred = True
                label = label[1:]
            else: 
                is_preferred = False
            restarts += [LI[
                SPAN(_class="sly button " + ("preferred" if is_preferred else ""))[
                    A(href=self.url({"action":"restart", "index":index}))[escape(label)],
                    " ",
                    escape(restart[1])
                ]]]
        #Stack frames:
        for frame in data.stack_frames:
            frames += [LI(value=index, id=f"frame-{frame.index}")[
                X.DETAILS[
                    X.SUMMARY[
                        A(href=self.url({"action":"frame", "index":frame.index}), 
                          _class="stack_frame")[
                            escape(frame.description)
                        ]
                    ]
                ]
            ]]
        self.flip()

    async def on_url_press(self, action, index=None, **rest):
      try:
        index = int(index) if index is not None else None
        action = action.lower()
        slynk = self.session.slynk
        if action == "frame":
            element = self.html.get_element_by_id(f"frame-{index}")[0]
            if "open" in element.attributes:
                del element.attributes["open"]
            elif "downloaded" in element.attributes:
                element.attributes["open"] = "open"
            else:
                await slynk.debug_stack_frame_details(
                    index,
                    self.data.stack_frames,
                    self.data.thread)
                element.attributes["open"] = "open"
                element.attributes["downloaded"] = "downloaded"
                element += [
                    H5["Local variables:"],
                    OL(id="locals")[
                        [LI(id=f"frame-{index}-local-{i}")[
                            escape(local.name), ": ", A(href=self.url({"action": "frame-describe", "index": i}))[escape(local.value)]
                            ] for i, local in enumerate(self.data.stack_frames[index].locals)]
                    ],
                    X.BUTTON(href=self.url({"action": "disassemble-frame", "index": index}))["Disassemble"], " ",
                    X.BUTTON(href=self.url({"action": "locate-frame", "index": index}))["Locate"], " ",
                    X.BUTTON(href=self.url({"action": "eval-frame", "index": index}))["Eval…"], " ",
                    X.BUTTON(href=self.url({"action": "inspect-frame", "index": index}))["Inspect…"], " ",
                    X.BUTTON(href=self.url({"action": "restart-frame", "index": index}))["Restart"], " ",
                    X.BUTTON(href=self.url({"action": "return-frame", "index": index}))["Return…"]
                ]
                self.current_locals = self.data.stack_frames[index].locals
            self.flip()
        elif action == "frame-describe":
            set_timeout(lambda: self.window.run_command("sly_describe",
                {"query": self.current_locals[index].value,
                 "input_source": "given"}), 10)
        elif action == "disassemble-frame":
            ui.send_result_to_panel(
                self.window,
                text=self.describe(index),
                header="Frame disassembly from debugger:",
                should_fold= True,
                result=await slynk.debug_disassemble_frame(
                    index,
                    self.data.thread
                ))
        elif action == "locate-frame":
            result = await slynk.debug_frame_source(index, self.data.thread)
            if result.file:
                print(result.position.offset)
                util.open_file_at(self.window, result.file, result.position.offset)
        elif "inspect" in action:
            maybe_inspector = None
            for maybe_inspector in self.session.inspectors.values():
                if maybe_inspector.window == self.window:
                    inspector = maybe_inspector
                    break
            inspector = Inspector(self.session, self.window)
            if action == "inspect-frame":
                await inspector.inspect_in_frame(
                    index,
                    self.data.thread)
            elif action == "inspect-condition":
                await inspector.inspect_current_condition(self.data.thread)
        elif action == "return-frame":
            try:
                await slynk.debug_return_from_frame(
                    index, 
                    await util.show_input_panel(
                        sly.loop, 
                        self.window, 
                        f"Return for frame", 
                        ""),
                    self.data.thread)
            except Exception as e:
                self.window.status_message(str(e))
        elif "copy" in action:
            set_clipboard(self.as_text(frames = "all" in action))
        else:
            if action == "eval-frame":
                result = await slynk.debug_eval_in_frame(
                    index, 
                    await util.show_input_panel(
                        sly.loop, 
                        self.window, 
                        f"Evaluee for frame", 
                        ""),
                    self.data.thread)
                header = "Interactive evaluation in frame from debugger"
            elif action == "restart":
                result = await slynk.debug_invoke_restart(self.data.level, index, self.data.thread)
                header = "Invokation of debugger restart"
            elif action == "restart-frame":
                result = await slynk.debug_restart_frame(index, self.data.thread)
                header = "Invokation of frame restart"
            else:
                result = "Error, URL command unknown"
            if "\n" in result:
                ui.send_result_to_panel(
                    self.window,
                    text=self.describe(index),
                    header=header,
                    should_fold=True,
                    result=result)
            else:
                self.window.status_message(result)
      except Exception as e:
        print("UrlError", e)

    def returned(self, data):
      try:
        self.html = HTML[BODY(_class="sly sly-debugger")[
            STYLE[util.load_resource("stylesheet.css")],
            f"Debugger for thread {data.thread}, no current condition being debugged."
        ]]
        self.flip()
        # We wait a small duration to see 
        # if there are still errors for the thread
        self.data = None
        set_timeout(lambda: (self.window.run_command("close") if self.data == None else None), 30)
      except Exception as e:
        print("return failure", e)

    def as_text(self, data=None, condition=True, restarts=True, frames=True):
        data = data or self.data
        result = ""
        if condition:
            result = f"{data.title}\n{data.type} in thread {data.thread}\n"
        if restarts:
            result += "Restarts:\n"
            for index, restart in enumerate(data.restarts):
                [label, description, *__] =  restart
                result += f"\t【{index}】{label}: {description}\n"
        if frames:
            result += "Backtrace\n:"
            for frame in data.stack_frames:
                result += f"\t【{frame.index}】{frame.description}\n"
        return result

