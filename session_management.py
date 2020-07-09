from sublime import *
import sublime_plugin, asyncio
from .sly import *
from . import util


def prepare_preview(session):
    print("prep")
    slynk = session.slynk
    lisp = slynk.connexion_info.lisp_implementation

    try: lisp_info = lisp.name + " " + lisp.version
    except e: lisp_info = "Error determining name"

    try: port_info = slynk.host + ":" + slynk.port + " on " + slynk.connexion_info.machine.instance
    except e: port_info = "Error determining connexion information"

    try: repl_info = str(len(session.repl_views)) + " REPLs opened"
    except e: repl_info = "Unknown number of open REPLs"

    return [lisp_info, port_info, repl_info]


async def session_choice(loop, window):
    try:
        default_session = sessions.sessions.index(sessions.get_by_window(window, False, False))
    except e:
        default_session = 0
    print("OEUA")
    print([prepare_preview(session) for session in sessions.sessions])
    choice = await util.show_quick_panel(
        loop,
        window,
        [prepare_preview(session) for session in sessions.sessions],
        0,
        default_session)
    return choice if choice != -1 else None


class SelectSessionCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)
        set_status(self.window.active_view())

    async def async_run(self, **kwargs):
        choice = await session_choice(loop, self.window)
        if choice is None: return
        sessions.set_by_window(self.window, sessions.sessions[choice])


class CloseSessionCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)
        set_status(self.window.active_view())

    async def async_run(self, current=False):
        if current:
            session = sessions.get_by_window(self.window)
        else:
            choice = await session_choice(loop, self.window)
            if choice is None: return
            session = sessions.sessions[choice]
        session.slynk.disconnect()
        sessions.remove(session)



class SessionStatusIndicator(sublime_plugin.ViewEventListener):
    def on_activated_async(self):
        set_status(self.view)


def set_status(view):
    if util.in_lisp_file(view, settings):
        util.set_status(
            view, 
            sessions.get_by_window(view.window(), indicate_failure=False))


