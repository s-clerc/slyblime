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

if "futures" not in globals():
    futures = {}

async def show(session, debug_data):
    global futures
    future_id = uuid.uuid4().hex
    future = session.loop.create_future()
    futures[future_id] = future
    view = Debugger(session.window, session, debug_data, future_id)
    await future
    session.window.run_command("close")
    return future.result()

class Debugger(ui.UIView):
    def __init__(self, window, session, data, future_id):
        super().__init__(window, session)
        self.data = data
        self.future_id = future_id
        self.design(data)
        self.flip()
        self.current_locals = None

    def design(self, data):
        affixes = sly.settings().get("debugger")["view_title_affixes"]
        self.name = affixes[0] + str(data.level) + affixes[1]
        affixes = sly.settings().get("debugger")["header_affixes"]
        self.html = HTML[BODY(_class="sly sly-debugger")[
            STYLE[util.load_resource("stylesheet.css")],
            H1[escape(affixes[0]+str(data.level)+affixes[1])],
            H2[escape(data.title)],
            H3[escape(data.type)],
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

    async def on_url_press(self, action, index, **rest):
        index = int(index)
        if action == "frame":
          try:
            element = self.html.get_element_by_id(f"frame-{index}")[0]
            if "open" in element.attributes:
                del element.attributes["open"]
            elif "downloaded" in element.attributes:
                element.attributes["open"] = "open"
            else:
                await self.session.slynk.debug_stack_frame_details(
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
                    ]
                ]
                self.current_locals = self.data.stack_frames[index].locals
            self.flip()
          except Exception as e:
                print("AU", e)
        elif action == "frame-describe":
            self.window.run_command("sly_describe",
                {"query": self.current_locals[index].value,
                 "input_source": "given"})
        else:
            futures[self.future_id].set_result((action, index))



