from sublime import *
import sublime_plugin

def open_file(*args, **kwargs):
    return open(f"{packages_path()}/SublimeREPL/.python-version", *args, **kwargs) 

def is_upgraded():
    try:
        file = open_file("r")
        if "3.8" in file.read():
            return True
    except Exception:
        # If the file doesn't exist, then there's no way it's upgraded
        pass
    return False

class SlyUpgradeSublimeReplCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        should_continue = ok_cancel_dialog(
            ("Slyblime requires that SublimeREPL be installed and running on Python 3.8,"
            "by default, it runs on 3.3. In the author's experience there are no regressions to switching, however not all functionality was not tested."),
            "Upgrade SublimeREPL to use Python 3.8")
        if not should_continue:
            return
        file = open_file("w") 
        file.write("3.8")
        file.close()
        message_dialog("Upgrade complete, you will now need to restart Sublime Text for the changes to take effect")

    def is_visible(self):
        return not is_upgraded()


class SlyDowngradeSublimeReplCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        should_continue = ok_cancel_dialog(
            ("SublimeREPL will be downgraded to run on Python 3.3 — the default version."
             " This action will mean that Sly's REPL no longer functions."),
            "Downgrade SublimeREPL to use Python 3.3")
        if not should_continue:
            return
        file = open_file("w") 
        file.write("3.3")
        file.close()
        message_dialog("Downgrade complete, you will now need to restart Sublime Text for the changes to take effect")

    def is_visible(self):
        return is_upgraded()


class SlyShowSlynkStarterUrlCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        path = f"{packages_path()}/{__name__.split('.')[0]}/sly/slynk/start-slynk.lisp"
        should_continue = ok_cancel_dialog(
            (f"The path to the bundled version of Slynk is \n\n {path}"
              "\n\nPress OK to copy it to the clipboard"))
        if should_continue:
            set_clipboard(path)