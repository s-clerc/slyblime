from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter

from . import slynk, util, sexpdata
from .sly import *
import logging
import functools
import concurrent.futures

from SublimeREPL import sublimerepl
from SublimeREPL.repls import repl
from . import pydispatch

class ReplWrapper(repl.Repl):
    def __init__(self, slynk_repl):
        super().__init__("utf-8")
        self.slynk_repl = slynk_repl
        self._killed = False
    # Sublime REPL specific
    def read_bytes(self):
        return None
        
    def write(self, to_write):
        print(to_write)
        self.slynk_repl.process(to_write[:-1])

class EventBasedReplView(sublimerepl.ReplView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("Before init ok")
        self.repl.slynk_repl.bind(write_string=self.on_print,
                                  write_values=self.on_write_values,
                                  prompt=self.on_prompt)
        self.repl.slynk_repl.play_events()
        #print(self.repl.slynk_repl.queue.get())
        print("ALL DONE")


    def update_view_loop(self):
        return True
    # This is a placeholder so super.update_view_loop
    # can be called to close the REPL if needed.
    def handle_repl_output(self):
        return False

    def on_print(self, message, *args):
        print(f"write: {message}")
        self.write(str(message) + "\n")

    def on_write_values(self, values, *args):
        for value in values:
            self.write("⟹ " + str(value[0]) + "\n")

    def on_prompt(self, package, prompt, error_level, *args):
        if error_level == 0:
            prompt = f"{prompt}〉"
        else:
            prompt = f"{prompt} ｢{error_level}｣〉"
        # Write-prompt makes it glitch out for some reason idky
        self.write(prompt)

async def create_main_repl(session):
    window = session.window
    slynk = session.slynk
    # Mostly copy and pasted from sublimeREPL.sublimerepl.ReplManager
    try:
        global rv
        repl = await slynk.create_repl()
        found = None
        for view in window.views():
            break # I don't know what to do here so break
            if view.id() == "something":
                found = view
                break
        view = found or window.new_file()
        try:
            rv = EventBasedReplView(view, ReplWrapper(repl), "Packages/Lisp/Lisp.tmLanguage", None)
        except Exception as e:
            self.window.status_message(f"REPL-spawning failure {str(e)}")
        #rv.call_on_close.append(self._delete_repl)
        session.repl_views.append(rv)
        sublimerepl.manager.repl_views[rv.repl.id] = rv
        view.set_scratch(True)
        view.set_name(f"🖵 sly {repl.channel.id}")
        return rv
    except Exception as e:
        traceback.print_exc()
        sublime.error_message(repr(e))

class CreateReplCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        global loop
        session = getSession(self.window.id())
        asyncio.run_coroutine_threadsafe(create_main_repl(session), loop)

