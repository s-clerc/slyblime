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
        self.slynk.bind(connect=self.on_connect,
                         disconnect=self.on_disconnect,
                         debug_setup=self.on_debug_setup,
                         debug_activate=self.on_debug_activate,
                         debug_return=self.on_debug_return,
                         __aio_loop__ = loop)

    async def connect(self):
        slynk = self.slynk
        print("Connect called")
        self.window.status_message(f"Attempting to connect to Slynk at {slynk.host}:{slynk.port} [≈ 1 min]")
        await slynk.connect(asyncio.get_event_loop())
        print("start pret")
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
        x = await debugger.show(self, debug_data)
        print("debugger terminated")
        #(action, index)

    def on_debug_activate(self, *args):
        print(f":activate {args}")

    def on_debug_return(self, *args):
        print(f":return {args}")

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

