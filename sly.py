from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import util, sexpdata, debugger

from .slynk import slynk

import logging
import functools

if "sessions" not in globals():
    print("Preparing stuff for SLY")
    sessions = {}
    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    logging.basicConfig(level=logging.DEBUG)

def getSession(id):
    global sessions
    return sessions[id]

def addSession(id, session):
    global sessions
    sessions[id] = session

class SlynkSession:
    def __init__(self, host, port, window, loop) -> None:
        super().__init__()
        self.slynk = slynk.SlynkClient(host, port)
        self.window = window
        self.repl_views = []
        self.loop = loop
        self.slynk.bind(__aio_loop__ = loop,
                        connect=self.on_connect,
                        disconnect=self.on_disconnect,
                        debug_setup=self.on_debug_setup,
                        debug_activate=self.on_debug_activate,
                        debug_return=self.on_debug_return,
                        read_from_minibuffer=self.on_read_from_minibuffer,
                        y_or_n_p=self.on_y_or_n)

    async def connect(self):
        slynk = self.slynk
        self.window.status_message(f"Attempting to connect to Slynk at {slynk.host}:{slynk.port} [≈ 1 min]")
        await slynk.connect(asyncio.get_event_loop())
        await slynk.prepare(f"{packages_path()}/Slims")
        #await slynk.closed()

    def on_connect(self, *args):
        self.window.status_message("SLYNK connexion established")
        print("SLYNK connexion established")

    def on_disconnect(self, *args):
        self.window.status_message("SLYNK connexion lost")
        print("SLYNK connexion lost")

    async def on_debug_setup(self, debug_data):
        print("run")
        (action, index) = await debugger.show(self, debug_data)
        if action == "restart": 
            await self.slynk.debug_invoke_restart(debug_data.level, index, debug_data.thread)
        elif action == "frame":
            await self.slynk.debug_restart_frame(index, debug_data.thread)
        #(action, index)

    def on_debug_activate(self, *args):
        print(f":activate {args}")

    def on_debug_return(self, *args):
        print(f":return {args}")

    async def on_read_from_minibuffer(self, prompt, initial_value, future):
        initial_value = initial_value if initial_value else ""
        output = await util.show_input_panel(self, prompt, initial_value)
        future.set_result(output)

    async def on_y_or_n(self, prompt, future):
        value = yes_no_cancel_dialog(prompt)
        if value == DIALOG_CANCEL:
            future.cancelled()
        else:
            future.set_result(True if value == DIALOG_YES else False)


class ConnectSlynkCommand(sublime_plugin.WindowCommand):
    def run(self, host="localhost", port=4005):  # implement run method
        global loop
        session = SlynkSession(host, port, self.window, loop)
        if not loop.is_running():
            threading.Thread(target=loop.run_forever).start()
        asyncio.run_coroutine_threadsafe(session.connect(), loop)
        addSession(self.window.id(), session)

class DisconnectSlynkCommand(sublime_plugin.WindowCommand):
    def run(self, port=4005):  # implement run method
        global loop
        session = getSession(self.window.id())
        session.slynk.disconnect()

