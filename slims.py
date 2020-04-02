# TechSideOnline.com Webify Sublime Text 3 plugin example

import sublime, sublime_plugin, threading, asyncio  # import the required modules

from . import slynk
sessions = {}
loop = asyncio.new_event_loop()


def getSession(id):
    global sessions
    return sessions[id]

def addSession(id, session):
    global sessions
    sessions[id] = session

class SlynkSession:
    def __init__(self, host, port, window) -> None:
        super().__init__()
        self.slynk = slynk.SlynkClient(host, port)
        self.window = window
        self.slynk.bind(connect=self.on_connect,
                         disconnect=self.on_disconnect,
                         debug_setup=self.on_debug_setup,
                         debug_activate=self.on_debug_activate,
                         debug_return=self.on_debug_return)

    async def connect(self):
        slynk = self.slynk
        self.window.status_message(f"Attempting to connect to Slynk at {slynk.host}:{slynk.port} [≈ 1 min]")
        await slynk.connect(asyncio.get_event_loop())
        await slynk.prepare()
        await slynk.closed()

    def on_connect(self, *args):
        self.window.status_message("SLYNK connexion established")
        print("SLYNK connexion established")

    def on_disconnect(self, *args):
        self.window.status_message("SLYNK connexion lost")
        print("SLYNK connexion lost")

    def on_debug_setup(self, *args):
        pass

    def on_debug_activate(self, *args):
        pass

    def on_debug_return(self, *args):
        pass

class ConnectSlynkCommand(sublime_plugin.WindowCommand):
    def run(self, port=4005):  # implement run method
        global loop
        session = SlynkSession("localhost", port, self.window)
        loop.create_task(session.connect())
        if not loop.is_running():
            threading.Thread(target=loop.run_forever).start()
        addSession(self.window.id(), session)
