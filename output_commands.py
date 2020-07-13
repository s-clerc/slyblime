from sublime import *
import sublime_plugin, asyncio
from .sly import *
from . import util
from math import inf

class SlyEvalRegionCommand(sublime_plugin.TextCommand):
    def run (self, *args, **kwargs):
        asyncio.run_coroutine_threadsafe(self.async_run(*args, **kwargs), loop)

    async def async_run(self, *args, input="selection", event=None):
        session = sessions.get_by_window(self.view.window())
        if session is None: return
        print("hi")
        view = self.view
        region = view.sel()[0]
        if event and input != "buffer":
            point = view.window_to_text((event["x"], event["y"]))
            print(point)
            minimal_distance = inf
            if input == "selection":
                for i, selection in enumerate(view.sel()):
                    distance = min(
                        abs(region.begin()-point), 
                        abs(region.end()-point))
                    if  distance < minimal_distance:
                        region = selection
                        if region.contains(point):
                            break
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

        result = await session.slynk.eval(
            view.substr(region), 
            True, 
            package)

        view.window().status_message(result if result else "An error occured during interactive evaluation")

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
