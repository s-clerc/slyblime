import asyncio, threading, pathlib

try:
    from .util import *
    from .structs import *
except ImportError as e:
    print(f"ImportError encoutered, switching gears: {e}")
    from util import *
    from structs import *

class Profiling:
    async def toggle_profiling_function(self, function_name, *args, **kwargs):
        result = await self.rex(f"SLYNK:TOGGLE-PROFILE-FDEFINITION {dumps(function_name)}", ":REPL-THREAD", *args, **kwargs)
        # self.emit("profile_command_complete", result)
        return result

    async def toggle_profiling_package(
            self, package, should_record_callers, should_profile_methods, *args, **kwargs):
        command = f"SLYNK:SLYNK-PROFILE-PACKAGE {dumps(package)} {dumps(should_record_callers)} {dumps(should_profile_methods)}"
        result = await self.rex(command, ":REPL-THREAD", *args, **kwargs)
        # self.emit("profile_command_complete", f"Attempting to profile {package}…")
        return result, f"Attempting to profile {package}…"

    async def stop_all_profiling(self, *args, **kwargs):
        result = await self.rex("SLYNK/BACKEND:UNPROFILE-ALL", ":REPL-THREAD", *args, **kwargs)
        # self.emit("profile_command_complete", result)
        return result

    async def reset_profiling(self, *args, **kwargs):
        result = await self.rex("SLYNK/BACKEND:PROFILE-RESET", ":REPL-THREAD", *args, **kwargs)
        # self.emit("profile_command_complete", result)
        return result

    async def profiling_report(self, *args, **kwargs):
        result = await self.rex("SLYNK/BACKEND:PROFILE-REPORT", ":REPL-THREAD", *args, **kwargs)
        # self.emit("profile_command_complete", "Profile report printed to REPL")
        return result, "Profile report printed to REPL"