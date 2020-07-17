from sublime import *
import sublime_plugin, asyncio, math
from .sly import *
from . import util


def get_results_view(window):
    view = None
    for maybe_view in window.views():
        if maybe_view.name() == "Sly Output":
            view = maybe_view
            break
    if view and view.settings().get("is-sly-output-view"):
        return view
    session = sessions.get_by_window(window)
    if session is None: 
        print("Error session should exist but doesn't 1")
        raise Exception("Session should exist but doesn't 1")
    view = window.new_file()
    view.set_name("Sly Output")
    view.set_scratch(True)
    view.set_read_only(True)
    view.settings().set("is-sly-output-view", True)
    return view

def send_result_to_panel(window, text=None, result="[No result]", header="[Command_header]", file_name=None, should_fold=True):
    view = get_results_view(window)
    out = [header + "\n",
           number_lines(text, " ") if text else "",
           f"\nfrom: {file_name} is:\n" if file_name else "\n is:\n",
           number_lines(result, " "),
           "\n\n"]
    # We store the position just before the result so
    # we can navigate the user there as that's what they actually care about
    # we also fold the region of the original text
    origin = view.size()
    region = Region(origin+len(out[0]), origin+len(out[0])+len(out[1]))
    out = "".join(out)
    view.run_command("repl_insert_text",
        {"pos": view.size(),
         "text": out})
    window.focus_view(view)
    view.fold(region)
    if text and should_fold:
        view.show(Region(origin, origin+len(out)))    
"""
  This function determines what the input should be.
  It takes into account cursor position for commands run 
  from the context menu and the argument to the input command.

  Basically if you use the command contextually it'll choose
  the toplevel the mouse is hovering over, or the closest region to it.

  Otherwise, it uses the closest to the caret
"""
def determine_input(view, input, event):
    region = view.sel()[0]
    if event and input != "buffer":
        point = util.event_to_point(view, event)
        if input == "selection":
            region = util.nearest_region_to_point(point, view.sel())
            if region is None:
                view.window().status_message("No selection found")
                return None, None
        else:
            region = Region(point, point)

    if "toplevel" in input:
        region = util.find_toplevel_form(view, region.begin())
    elif "buffer" in input:
        region = Region(0, view.size() - 1)

    # No highlighting for buffer evaluation
    if input in ["toplevel", "selection"]:
        highlighting = settings().get("highlighting")
        package, package_region = util.current_package(view, region.begin(), True)
        util.highlight_region(view, region, highlighting, None, highlighting["form_scope"])
        if package:
            util.highlight_region(view, package_region, highlighting, None, highlighting["package_scope"])
    else:
        package = None
    return view.substr(region), package


def number_lines(text, prefix="", suffix=" "):
    width = math.ceil(math.log(len(lines := text.split("\n"))))
    offset = settings().get("line_offset")
    return "\n".join([prefix + str(n+offset).rjust(width, ' ') + suffix + line 
                      for n, line in enumerate(lines)])


class SlyExpandCommand(sublime_plugin.TextCommand):
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, input_source="selection", output="panel", event=None, **kwargs):
        session = sessions.get_by_window(self.view.window())
        if session is None: return
        print("OK")
        try:
            text, package = determine_input(self.view, input_source, event)
            print(text)
            if text is None:
                return
            print("now start")
            print(kwargs)
            result, name = await session.slynk.expand(
                text, 
                package,
                True,
                **kwargs)
            send_result_to_panel(
                self.view.window(),
                text,
                result,
                f"Expansion (`{name}` in `{package or 'CL-USER'}`) of",
                self.view.file_name())
        except Exception as e:
            window.status_message(f"An error occured: {e}")
            print(f"SlyExpandCommandException: {e}")     
    def want_event(self):
        return True


class SlyEvalRegionCommand(sublime_plugin.TextCommand):
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, mode="eval", input_source="selection", output="status_message", event=None, **kwargs):
        session = sessions.get_by_window(self.view.window())
        if session is None: return
        text, package = determine_input(self.view, input_source, event)
        if text is None:
            return
        result = await session.slynk.eval(
            text, 
            True, 
            package)
        if output == "status_message":
            view.window().status_message(
                result if result 
                       else f"An error occured during interactive evaluation")
        elif output == "panel":
            send_result_to_panel(
                self.view.window(),
                text,
                result,
                f"Interactive evaluation (in `{package or 'CL-USER'}`) of",
                self.view.file_name())
    def want_event(self):
        return True


class SlyEvalCommand(sublime_plugin.WindowCommand):
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, **kwargs):
        session = sessions.get_by_window(self.window)
        if session is None: return
        view = self.window.active_view()

        package, package_region = util.current_package(view, None, True)
        if package:
            highlighting = settings().get("highlighting")
            util.highlight_region(view, package_region, highlighting, None, highlighting["package_scope"])
        evaluee = await util.show_input_panel(loop, self.window, f"Evaluee in {package or 'CL-USER'}", "")
        if evaluee is None:
            return
        result = await session.slynk.eval(
            evaluee, 
            False, 
            package)
        self.window.status_message(f"⇒ {result}" if result else "An error occured during interactive evaluation")


class SlyDescribeCommand(sublime_plugin.TextCommand):
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, mode="symbol", input_source="ask", output="panel", **kwargs):
      try:
        window = self.view.window() or self.window
        session = sessions.get_by_window(window)
        if session is None: return 
        print("hello")
        if input_source == "ask":
            query = await util.show_input_panel(
                loop, 
                window, 
                f"Describe:", 
                "")
        elif input_source == "given":
            query = kwargs["query"]
        result = await session.slynk.describe(query, mode)
        print(result)
        send_result_to_panel(
            window=window,
            result=result, 
            header=f"Description ({mode}) for {query}")
      except Exception as e:
        print("SlyDescribeCommandException", e)