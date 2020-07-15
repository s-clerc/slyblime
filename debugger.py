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

if "futures" not in globals():
    futures = {}

def design(debug_data, future_id):
  try:
    def url(prefix, index):
        # The use of double curlies must be a joke
        return f'subl:debugger_sheet_url {{"url": "{prefix}-{index}", "future_id": "{future_id}"}}'
        
    affixes = sly.settings().get("debugger")["header_affixes"]
    html = HTML[BODY(_class="sly sly-debugger")[
        STYLE[util.load_resource("stylesheet.css")],
        H1[escape(affixes[0]+str(debug_data.level)+affixes[1])],
        H2[escape(debug_data.title)],
        H3[escape(debug_data.type)],
        H4["Restarts"],
        (restarts := OL(start="0")),
        H4["Backtrace"],
        (frames := OL(start="1"))
    ]]

    # Restarts
    for index, restart in enumerate(debug_data.restarts):
        label = restart[0].lower().capitalize()
        if len(label) > 0 and label[0] == "*":
            is_preferred = True
            label = label[1:]
        else: 
            is_preferred = False
        restarts += [LI[
            SPAN(_class="sly button " + ("preferred" if is_preferred else ""))[
                A(href=url("restart", index))[escape(label)],
                escape(restart[1])
            ]]]

    #Stack frames:
    for index, frame_title, restartable in debug_data.stack_frames:
        frames += [LI(value=index)[
            A(href=url("frame", index), _class="stack_frame")[
                escape(frame_title)
            ]]]
    print(html)
    return html
  except Exception as e:
    print(e)

async def show(session, debug_data):
    global futures
    affixes = sly.settings().get("debugger")["view_title_affixes"]
    title = affixes[0] + str(debug_data.level) + affixes[1]
    future_id = uuid.uuid4().hex
    html = design(debug_data, future_id)
    future = session.loop.create_future()
    futures[future_id] = future
    sheet = session.window.new_html_sheet(title, str(html), 0)
    await future
    session.window.run_command("close")
    return future.result()

class DebuggerSheetUrlCommand(sublime_plugin.ApplicationCommand):
    def run(self, **kwargs):
        # We need to set the future result in the same
        # thread as the loop
        asyncio.run_coroutine_threadsafe(
            async_run(**kwargs), 
            sly.loop)
        
async def async_run(**kwargs):
    print(kwargs)
    url = kwargs["url"]
    future_id = kwargs["future_id"]
    [action, index] = url.split("-")
    index = int(index)
    futures[future_id].set_result((action, index))



