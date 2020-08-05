import asyncio, threading, pathlib
from typing import *

try:
    from .util import *
    from .structs import *
except ImportError as e:
    print(f"ImportError encoutered, switching gears: {e}")
    from util import *
    from structs import *

class Debug:
    def debug_setup_handler(self, expression):
        def is_restartable(frame):
            return bool(frame[2][1]) if len(frame) >= 3 else False

        data = DebugEventData(
            expression[1],  # Thread
            expression[2],  # Level
            expression[3][0],  # Title
            expression[3][1],  # Type
            [(str(restart[0]), str(restart[1])) for restart in expression[4]],
            # Stack frames
            [StackFrame(int(frame[0]), str(frame[1]), is_restartable(frame)) for frame in expression[5]]
        )
        self.emit("debug_setup", data)

    def debug_activate_handler(self, expression):
        self.emit("debug_activate", DebugEventData(
            expression[1],
            expression[2]
        ))

    def debug_return_handler(self, expression):
        self.emit("debug_return", DebugEventData(
            expression[1],
            expression[2]
        ))

    async def debug_invoke_restart(self, level, restart, thread, *args, **kwargs):
        command = "SLYNK:INVOKE-NTH-RESTART-FOR-EMACS " + str(level) \
                  + " " + str(restart)
        result = await self.rex(command, thread, *args, **kwargs)
        return result

    async def debug_escape_all(self, thread, *args, **kwargs):
        result = await self.rex("SLYNK:THROW-TO-TOPLEVEL", thread, *args, **kwargs)
        return result

    async def debug_continue(self, thread, *args, **kwargs):
        result = await self.rex("SLYNK:SLY-DB-CONTINUE", thread, *args, **kwargs)
        return result

    async def debug_abort_current_level(self, level, thread, *args, **kwargs):
        if level == 1:
            result = await self.debug_escape_all(thread, *args, **kwargs)
        else:
            result = await self.rex("SLYNK:SLY-DB-ABORT", thread, *args, **kwargs)
        return result

    async def debug_get_stack_trace(self, thread, *args, **kwargs):
        frames = await self.rex("SLYNK:BACKTRACE 0 NIL", thread, *args, **kwargs)
        return [StackFrame(
            int(frame[0]),
            str(frame[1]),
            True if len(frame) >= 3 and bool(frame[2][1]) else False
        ) for frame in frames]

    async def debug_stack_frame_details(self, index, stack_frames, *args, **kwargs):
        frame = [frame for frame in stack_frames if frame.index == index][0]
        if frame.locals is not None:
            return frame
        else:
            response = await self.rex(f"SLYNK:FRAME-LOCALS-AND-CATCH-TAGS {str(index)}", *args, **kwargs)
            frame.locals = [StackFrameLocal(
                str(local[1]),
                int(local[3]),
                str(local[5])
            ) for local in response[0]]

            frame.catch_tags = [str(tag) for tag in response[1]]
            return frame

    async def debug_restart_frame(self, frame, *args, **kwargs):
        response = await self.rex(f"SLYNK:RESTART-FRAME {frame}", *args, **kwargs)
        return response

    async def debug_return_from_frame(self, frame, value, *args, **kwargs):
        was_error = await self.rex(f"SLYNK:SLY-DB-RETURN-FROM-FRAME {frame} {dumps(value)}", *args, **kwargs)
        if bool(was_error):
            raise Exception("Lisp error while returning from frame: " + str(was_error))

    async def debug_frame_source(self, frame, thread, *args, **kwargs):
        result = await self.rex(f"SLYNK:FRAME-SOURCE-LOCATION {frame}", thread, *args, **kwargs)
        return parse_location(result)

    async def debug_disassemble_frame(self, frame, *args, **kwargs):
        result = await self.rex(f"SLYNK:SLY-DB-DISASSEMBLE {frame}", *args, **kwargs)
        return str(result)

    async def debug_eval_in_frame(self, frame, expression, *args, **kwargs):
        interpackage = await self.rex(f"SLYNK:FRAME-PACKAGE-NAME {frame}", *args, **kwargs)
        command = f'SLYNK:EVAL-STRING-IN-FRAME {dumps(expression)} {frame} "{str(interpackage)}"'
        result = await self.rex(command, *args, **kwargs)
        return str(result)

    async def debug_step(self, frame, *args, **kwargs):
        result = await self.rex(f"SLYNK:SLY-DB-STEP {frame}", *args, **kwargs)
        return result

    async def debug_next(self, frame, *args, **kwargs):
        result = await self.rex(f"SLYNK:SLY-DB-NEXT {frame}", *args, **kwargs)
        return result

    async def debug_out(self, frame, *args, **kwargs):
        result = await self.rex(f"SLYNK:SLY-DB-OUT {frame}", *args, **kwargs)
        return result

    async def debug_break_on_return(self, frame, *args, **kwargs):
        result = await self.rex(f"SLYNK:SLY-DB-BREAK-ON-RETURN {frame}", *args, **kwargs)
        return result

    async def debug_break(self, function_name, *args, **kwargs):
        result = await self.rex(f"SLYNK:SLY-DB-BREAK {dumps(function_name)}", *args, **kwargs)
        return result

# For the trace dialog:

    async def tracer_toggle(self, function_name, *args, **kwargs) -> str:
        result = await self.rex(
            f"slynk-trace-dialog:dialog-toggle-trace (slynk::from-string {dumps(function_name)})",
            *args, **kwargs)
        return result

    async def tracer_trace(self, function_name, *args, **kwargs) -> str:
        result = await self.rex(
            f"slynk-trace-dialog:dialog-trace (slynk::from-string {dumps(function_name)})",
            *args, **kwargs)
        return result

    async def tracer_untrace(self, function_name, *args, **kwargs):
        result = await self.rex(
            f"slynk-trace-dialog:dialog-untrace '{function_name}",
            *args, **kwargs)
        return result

    async def tracer_untrace_all(self, *args, **kwargs) -> Tuple[str, str]:
        result = await self.rex("slynk-trace-dialog:dialog-untrace-all", *args, **kwargs)
        return [(spec[0], str(spec[2])) for spec in result]

    async def tracer_report_specs(self, *args, **kwargs) -> Tuple[str, str]:
        result = await self.rex("slynk-trace-dialog:report-specs", *args, **kwargs)
        return [(spec[0], str(spec[2])) for spec in result]

    async def tracer_report_total(self, *args, **kwargs) -> int:
        result = await self.rex("slynk-trace-dialog:report-total", *args, **kwargs)
        return result       

    async def tracer_clear(self, *args, **kwargs):
        result = await self.rex("slynk-trace-dialog:clear-trace-tree", *args, **kwargs)
        return result       

    async def tracer_report_partial_tree(self, key, *args, **kwargs) -> Tuple[List[Trace], int, str]:
        results = await self.rex(f"slynk-trace-dialog:report-partial-tree '{key}", *args, **kwargs)
        traces = [Trace(result[0], result[1],
                        (result[2][0], str(result[2][2])),
                        [argument[1] for argument in result[3]],
                        [returnee[1] for returnee in result[4]],
                        *result[5:])
                   for result in results[0]]
        return (traces, results[1], str(results[2]))
