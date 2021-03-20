from sublime import *
import sublime_plugin, asyncio
from .sly import *
from . import util

def prepare_preview(session, show_repls=True):
    slynk = session.slynk
    lisp = slynk.connexion_info.lisp_implementation

    try: lisp_info = f"{lisp.name} {lisp.version}"
    except: lisp_info = "Error determining name"

    try: port_info = f"{slynk.host}:{slynk.port} on {slynk.connexion_info.machine.instance}"
    except: port_info = "Error determining connexion information"
    # We want to hide this for orphaned processes
    if show_repls:
        try: repl_info = f"{len(session.repl_views)} REPLs opened"
        except: repl_info = "Unknown number of open REPLs"

        return [lisp_info, port_info, repl_info]
    return [lisp_info, port_info]


async def session_choice(loop, window):
    if len(sessions.list) == 0:
        window.status_message("No active Slynk connexions")
        return
    try:
        default_session_index = 0 
        default_session_id = sessions.get_by_window(window, False, False).id
        for i, session in enumerate(sessions.list):
            if session.id == default_session_id:
                default_session_index = i
                break
    except Exception as e:
        print(f"Exception while trying to establish default_session {e}")
        default_session_index = 0
    choice = await util.show_quick_panel(
        loop,
        window,
        [prepare_preview(session) for session in sessions.list],
        0,
        default_session_index)
    return sessions.list[choice].id if choice != -1 else None


class SelectSessionCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        if not loop.is_running():
            self.window.status_message("Connect to a Lisp instance first!")
            return
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)
        set_status(self.window.active_view())

    async def async_run(self, **kwargs):
        choice = await session_choice(loop, self.window)
        if choice is None: return
        sessions.set_by_window(self.window, sessions.list[choice])


class CloseSessionCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        if not loop.is_running():
            self.window.status_message("Connect to a Lisp instance first!")
            return
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

class SlyCloseProcessCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        if not loop.is_running():
            self.window.status_message("Connect to a Lisp instance first!")
            return
        asyncio.run_coroutine_threadsafe(
            self.async_run(**kwargs),
            loop)
        set_status(self.window.active_view())

    async def async_run(self, current=False):
        orphaned_lisps = sessions.orphaned_inferior_lisps
        if not len(orphaned_lisps):
            self.window.status_message("No orphaned inferior lisps processes")
            return

        choice = await util.show_quick_panel(
            loop, self.window,
            [prepare_preview(session, False) 
                for session in orphaned_lisps],
            0, 0)
        if choice is None:
            return
            
        try:
            orphaned_lisps[choice].process.terminate()
            self.window.status_message("Process terminated")
            del orphaned_lisps[choice]
        except Exception as e:
            self.window.status_message(f"Failed to terminate process: {e}")

