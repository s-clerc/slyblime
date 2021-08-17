import sublime
from .sly import *
from . import util
import importlib
import os
from typing import *

translators = []

class PathnameTranslator():
    def is_active(self, session):
        raise NotImplementedError()

    def local_to_remote(self, pathname):
        raise NotImplementedError()

    def remote_to_local(self, pathname):
        raise NotImplementedError()

    @property
    def description(self) -> Tuple[str, str]: 
        raise NotImplementedError()


class SimpleTranslator(PathnameTranslator):
    def local_to_remote(self, pathname):
        return os.path.join(self.remote_stem, os.path.relpath(pathname, self.local_stem))

    def remote_to_local(self, pathname):
        return os.path.join(self.local_stem, os.path.relpath(pathname, self.remote_stem))

    @property
    def description(self):
        return ("Simple translator, that performs the following bijection:",
                f"{self.local_stem}/rest ≃ {self.remote_stem}/rest")

class IdentityTranslator(SimpleTranslator):
    remote_stem = ""
    local_stem = ""
    description = ("Multiple suitable pathname translators were detected.",
                   "Choose this option if you would prefer to not use a translator.")

    def is_active(self, session):
        return True



def get_translators():
    global translators
    global translator_module
    translators = [IdentityTranslator()]
    try:
        translator_module = importlib.import_module("User.slyblime.filename_translators")
        importlib.reload(translator_module)
    except Exception as e:
        print(f"Failed to import filename translators module: {e}")
        pass
    else:
        for name in dir(translator_module):
            value = translator_module.__dict__[name]
            if value in [SimpleTranslator, PathnameTranslator, IdentityTranslator]:
                continue
            try:
                if PathnameTranslator in value.__mro__:
                    translators.append(value())
            except:
                pass
    print(translators)
    return translators


async def get_translator(window, session, show_change_messages=False):
    try:
        get_translators()
        for translator in translators:
            print(translator)
            try:
                translator.is_active(session)
            except Exception as e:
                print(f"32 {e} ..")
        active_translators = [translator for translator in translators
                                         if translator.is_active(session)]
        if len(active_translators) < 2: # Only the identity
            if show_change_messages:
                window.status_message("No other pathname translators avaliable")
            return active_translators[0]
        print("OK")
        def on_highlighted(index):
            window.status_message(f"Internal name: {active_translators[index].__class__}")

        index = await util.show_quick_panel(
            loop,
            window,
            [translator.description for translator in active_translators],
            sublime.KEEP_OPEN_ON_FOCUS_LOST,
            on_highlighted=on_highlighted)

        return active_translators[index]
    except Exception as e:
        print(f"E: {e}")
        window.status_message("Error selecting translator, identity pathname translator will be used.")
        return IdentityTranslator()

class SlyChangeFilenameTranslatorCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        session = sessions.get_by_window(self.window)
        if session is None: return
        asyncio.run_coroutine_threadsafe(
            self.async_run(session, self.window, **kwargs), 
            loop)

    async def async_run(self, session, window, translator_name=None, require_active=True):
        if translator_name:
            get_translators()
            if require_active:
                active_translators = [translator for translator in translators
                                                 if translator.is_active(session)]
            else:
                active_translators = translators
            for translator in active_translators:
                if translator_name == translator.__name__:
                    session.filename_translator = translator
                    window.status_message(f"Pathname translator set to `{name}` successfully.")
                    return
            active_text = 'active ' if require_active else ''
            window.status_message(
                f"Unable to find {active_text}pathname translator `{name}`.")
            return

        session.filename_translator = await get_translator(window, session, True)







