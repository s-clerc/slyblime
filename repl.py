from sublime import *
import sublime_plugin, threading, asyncio  # import the required modules

from operator import itemgetter
import itertools

from . import slynk, util, sexpdata
from .sly import *
import logging
import functools
import concurrent.futures

from SublimeREPL import sublimerepl
from SublimeREPL.repls import repl
from . import pydispatch


def prepare_backtrack_phantom(region, regions_index, value_index):
    [prefix, infix, postfix] = settings().get("repl")['backtracking']["affixes"]
    return Phantom(region,
                   f"{prefix}{regions_index}{infix}{value_index}{postfix}",
                   LAYOUT_INLINE)

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
        self.slynk_repl.process(to_write)


class EventBasedReplView(sublimerepl.ReplView):
    NEWLINE_SEQUENCE = "\n"  # To allow for future configurability

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.repl.slynk_repl.bind(
            write_string=self.on_print,
            write_values=self.on_write_values,
            prompt=self.on_prompt,
            evaluation_aborted=self.on_evaluation_aborted,
            server_side_repl_close=self.on_server_side_repl_close)
        self.repl.slynk_repl.play_events()
        self.value_phantom_groups = []
        self.backtrack_phantom_set = PhantomSet(self._view, "backtracking")
        self._view.settings().set("is_sly_repl", True)

    def update_view_loop(self):
        return True

    def get_final_character(self):
        return self._view.substr(self._view.size() - 1)

    # Works exactly like (FRESH-LINE) in CL
    def fresh_line(self):
        if self.get_final_character() != self.NEWLINE_SEQUENCE:
            self.write(self.NEWLINE_SEQUENCE)

    def prevent_double_newline(self, to_write):
        is_enabled = settings().get("repl")["avoid_double_newline"]
        are_matching = self.get_final_character() == self.NEWLINE_SEQUENCE == to_write[0]
        if is_enabled and are_matching:
            return to_write[1:]
        else:
            return to_write

    # This is a placeholder so super.update_view_loop
    # can be called to close the REPL if needed.
    def handle_repl_output(self):
        return False

    def on_print(self, message, *args):
        print(f"write: {message}")
        self.fresh_line()
        self.write(self.prevent_double_newline(str(message)))

    def on_write_values(self, values, *args):
        phantom_group_index = len(self.value_phantom_groups)
        phantoms = []
        for value_index, value in enumerate(values):
            self.fresh_line()
            phantoms.append(prepare_backtrack_phantom(
                # First character of next line:
                Region(self._view.size(), self._view.size()),
                phantom_group_index,
                value_index))
            self.write(settings().get("repl")['value_prefix'] + str(value[0]))
        self.value_phantom_groups.append(phantoms)

    def on_prompt(self, package, prompt, error_level, *args):
        terminator = settings().get("repl")['prompt']
        left = settings().get("repl")['error'][0]
        right = settings().get("repl")['error'][1]
        if error_level == 0:
            prompt = prompt + terminator
        else:
            prompt = prompt + left + str(error_level) + right + terminator
        # Write-prompt makes it glitch out for some reason idky
        self.fresh_line()
        start = self._view.size() - 1
        self.write(prompt)
        end = self._view.size() - 1
        self._view.settings().set("package", package)
        self._view.settings().set("prompt-region", [start, end])

    def on_evaluation_aborted(self, *data):
        self.fresh_line()
        self.write("Evaluation aborted for " + " ".join(data))

    def on_server_side_repl_close(self, *data):
        # TODO set _killed to True if the connexion is lost but
        # server_side_repl_close doesn't occur
        super().update_view_loop()

    def show_backtrack_phantoms(self, value_region_group_index=None, value_index=None):
        if value_index is not None and value_region_group_index is not None:
            phantoms = [self.value_phantom_groups[value_region_group_index][value_index]]
        elif value_region_group_index is not None:
            phantoms = self.value_phantom_groups[value_region_group_index]
        else:
            phantoms = list(itertools.chain.from_iterable(self.value_phantom_groups))
        self.backtrack_phantom_set.update(phantoms)

    def hide_backtrack_phantoms(self):
        self.backtrack_phantom_set.update([])


async def create_main_repl(session):
    window = session.window
    slynk = session.slynk
    # Mostly copy and pasted from sublimeREPL.sublimerepl.ReplManager
    try:
        repl = await slynk.create_repl()
        found = None
        for view in window.views():
            break  # I don't know what to do here so break
            if view.id() == "something":
                found = view
                break
        view = found or window.new_file()
        try:
            rv = EventBasedReplView(
                view, 
                ReplWrapper(repl), 
                settings().get("repl")["syntax"], None)
        except Exception as e:
            self.window.status_message(f"REPL-spawning failure {str(e)}")
        #rv.call_on_close.append(self._delete_repl)
        session.repl_views.append(rv)
        sublimerepl.manager.repl_views[rv.repl.id] = rv
        view.set_scratch(True)
        affixes = settings().get("repl")["view_title_affixes"]
        view.set_name(affixes[0] + str(repl.channel.id) + affixes[1])
        return rv
    except Exception as e:
        traceback.print_exc()
        sublime.error_message(repr(e))


class CreateReplCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        global loop
        session = sessions.get_by_window(self.window)
        if session is None: return
        asyncio.run_coroutine_threadsafe(create_main_repl(session), loop)


class ReplNewlineCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if not (repl_view := sublimerepl.manager.repl_view(self.view)): 
            return
        view = repl_view._view
        selection = view.sel()
        caret_point = selection[len(selection) - 1].begin()
        view.insert(edit, caret_point, "\n")


class SlyReplListener(sublime_plugin.EventListener):
    def on_modified(self, view):
        if not (view.settings().get("is_sly_repl")
                and (repl_view := sublimerepl.manager.repl_view(view))): 
            return
        caret_point = view.sel()[0].begin()
        closest_match = util.find_closest(
            view,
            caret_point,
            r"(?i)#v([0-9|\w]*(:[0-9]*)?)?\w*")
        if closest_match and closest_match.contains(caret_point):
            config = settings().get("repl")['backtracking']
            failed = False
            parts = None
            try:
                string = view.substr(closest_match)
                parts = [util.safe_int(index) 
                         for index in string[2:].split(":")]
                if len(parts) < 2 or parts[0] is not None:
                    repl_view.show_backtrack_phantoms(*parts)
                else:
                    failed = True
            except (IndexError, ValueError):
                # To test if it is possible to show the phantoms for
                # at least the value group
                failed = True
                if parts and len(parts) == 2:
                    try:
                        repl_view.show_backtrack_phantoms(parts[0])
                    except IndexError:
                        pass
            style = config["invalid_region" if failed or ':' == string[-1]
                                                      or len(parts) == 0
                                            else "valid_region"]
            view.add_regions(
                "backtracking", [closest_match], style["scope"],
                "", util.compute_flags(style["flags"]))
        else:
            repl_view.hide_backtrack_phantoms()
            view.erase_regions("backtracking")

    def on_selection_modified(self, view):
        self.on_modified(view)
