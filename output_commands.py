from sublime import *
import sublime_plugin, asyncio, uuid
from html import escape
from .sly import *
from . import util
from . import ui_view as ui

"""
  This function determines what the input should be.
  It takes into account cursor position for commands run 
  from the context menu and the argument to the input command.

  Basically if you use the command contextually it'll choose
  the toplevel the mouse is hovering over, or the closest region to it.

  Otherwise, it uses the closest to the caret
"""
async def determine_input(view, input_source, event):
    if event and input_source != "buffer":
        point = util.event_to_point(view, event)
    else:
        point = view.sel()[0].begin()
    if isinstance(input_source, list) and input_source[0] == "ask":
        query = await util.show_input_panel(
                loop, 
                view.window(), 
                input_source[1] if len(input_source) > 1 else "Enter value for output command",
                input_source[2] if len(input_source) > 2 else "")
        region = Region(point, point)
    elif input_source == "selection":
        region = util.nearest_region_to_point(point, view.sel())
        print(region)
        if region is None:
            view.window().status_message("No selection found")
            return None, None
    elif "toplevel" == input_source:
        region = util.find_toplevel_form(view, point)
    elif input_source == "form":
        region = util.find_containing_form(view, point)
    elif "buffer" == input_source:
        region = Region(0, view.size() - 1)
    else:
        view.window().status_message("Command error: unable to determine input")
        return None, None

    if isinstance(input_source, str):
        query = view.substr(region)

    # No highlighting for buffer evaluation
    if input_source != "buffer":
        highlighting = settings().get("highlighting")
        package, package_region = util.current_package(view, region.begin(), True)
        util.highlight_region(view, region, highlighting, None, highlighting["form_scope"])
        if package_region:
            util.highlight_region(view, package_region, highlighting, None, highlighting["package_scope"])
    else:
        package = None
    return query, package


class SlyExpandCommand(sublime_plugin.TextCommand):
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, input_source="selection", output="panel", event=None, **kwargs):
        session = sessions.get_by_window(self.view.window())
        if session is None: return
        print("OK")
        try:
            text, package = await determine_input(self.view, input_source, event)
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
            ui.send_result_to_panel(
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
        text, package = await determine_input(self.view, input_source, event)
        if text is None:
            return
        result = await session.slynk.eval(
            text, 
            True, 
            package)
        if output == "status_message":
            self.view.window().status_message(
                result if result 
                       else f"An error occured during interactive evaluation")
        elif output == "panel":
            ui.send_result_to_panel(
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

    async def async_run(self, *args, mode="symbol", event=None, input_source=["ask", "Describe"], output="panel", **kwargs):
      try:
        window = self.view.window() or self.window
        view = self.view or self.window.active_view()
        session = sessions.get_by_window(window)
        if session is None: return 
        print("hello")
        if input_source == "given":
            query = kwargs["query"]
        else:
            query, __ = await determine_input(view, input_source, event)
            print(query)
        result = await session.slynk.describe(query, mode)
        print(result)
        ui.send_result_to_panel(
            window=window,
            result=result, 
            header=f"Description ({mode}) for {query}")
      except Exception as e:
        print("SlyDescribeCommandException", e)


ALL = ["calls", "calls-who", "references", "sets", "macroexpands", "callers", "callees",]

class SlyReferenceCommand(sublime_plugin.TextCommand):
    ASSORTED_PHANTOMS = []
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, modes=ALL, event=None, input_source=["ask"], package="CL-USER", output="panel", **kwargs):
      try:
        window = self.view.window() or self.window
        view = self.view or self.window.active_view()
        session = sessions.get_by_window(window)
        if session is None: return 

        if input_source == "given":
            query = kwargs["query"]
        else:
            query, package = await determine_input(view, input_source, event)
        results = ui.get_results_view(window)

        out = f"\n\nReferences for `{query}`:\n"
        all_references = []
        for mode in modes:
            try:
                references = await session.slynk.xref(query, mode, "T", package)
            except Exception as e:
                continue
            if len(references) == 0: 
                continue
            all_references += references
            out += f"   with mode `{mode}`:\n"
            for name, location in references:
                snippet = None
                try:
                    if str(location.hints[0][0]).lower() == ":snippet":
                        snippet = location.hints[0][1].strip()
                except Exception as e:
                    pass
                out += f"      {name}: in \x1F\n"
                if snippet:
                    out += ui.number_lines(snippet, "          ") + "\n"
        results.run_command("repl_insert_text",
            {"pos": (start := results.size()),
             "text": out})

        phantoms = []
        for reference in all_references:
            region = results.find("\x1F", start)
            file_name = escape(reference[1].file)
            phantoms.append(Phantom(
                region, 
                f'"<a href="{reference[1].position.offset} {file_name}">{file_name}</a>"', 
                LAYOUT_INLINE, 
                self.open))
            start = region.end()
        hex = uuid.uuid4().hex
        window.focus_view(results)
        self.ASSORTED_PHANTOMS.append(PhantomSet(results, hex))
        self.ASSORTED_PHANTOMS[-1].update(phantoms)
      except Exception as e:
        print("SlyReferenceCommandException", e)

    def open(self, url):
        window = self.view.window() or self.window
        point, path = url.split(" ", 1)
        print("open", path, point)
        util.open_file_at(window, path, int(point))