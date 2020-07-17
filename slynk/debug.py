import asyncio, threading, pathlib

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

    async def debug_invoke_restart(self, level, restart, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        command = "SLYNK:INVOKE-NTH-RESTART-FOR-EMACS " + str(level) \
                  + " " + str(restart)
        result = await self.rex(command, thread, package)
        return result

    async def debug_escape_all(self, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        result = await self.rex("SLYNK:THROW-TO-TOPLEVEL", thread, package)
        return result

    async def debug_continue(self, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        result = await self.rex("SLYNK:SLY-DB-CONTINUE", thread, package)
        return result

    async def debug_abort_current_level(self, level, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        if level == 1:
            result = await self.debug_escape_all(thread, package)
        else:
            result = await self.rex("SLYNK:SLY-DB-ABORT", thread, package)
        return result

    async def debug_get_stack_trace(self, thread, *args):
        frames = await self.rex("SLYNK:BACKTRACE 0 NIL", thread, *args)
        return [StackFrame(
            int(frame[0]),
            str(frame[1]),
            True if len(frame) >= 3 and bool(frame[2][1]) else False
        ) for frame in frames]

    async def debug_stack_frame_details(self, index, stack_frames, thread, *args):
        frame = [frame for frame in stack_frames if frame.index == index][0]
        if frame.locals is not None:
            return frame
        else:
            response = await self.rex(f"SLYNK:FRAME-LOCALS-AND-CATCH-TAGS {str(index)}", thread, *args)
            frame.locals = [StackFrameLocal(
                str(local[1]),
                int(local[3]),
                str(local[5])
            ) for local in response[0]]

            frame.catch_tags = [str(tag) for tag in response[1]]
            return frame

    async def debug_restart_frame(self, frame, thread, *args):
        response = await self.rex(f"SLYNK:RESTART-FRAME {frame}", thread, *args)
        return response

    async def debug_return_from_frame(self, frame, value, thread, *args):
        was_error = await self.rex(f"SLYNK:SLY-DB-RETURN-FROM-FRAME {frame} {dumps(value)}", thread, *args)
        if bool(was_error):
            raise Exception("Lisp error while returning from frame: " + str(was_error))

    async def debug_frame_source(self, frame, thread, *args):
        result = await self.rex(f"SLYNK:FRAME-SOURCE-LOCATION {frame}", thread, *args)
        return parse_location(result)

    async def debug_disassemble_frame(self, frame, thread, *args):
        result = await self.rex(f"SLYNK:SLY-DB-DISASSEMBLE {frame}", thread, *args)
        return str(result)

    async def debug_eval_in_frame(self, frame, expression, thread, *args):
        interpackage = await self.rex(f"SLYNK:FRAME-PACKAGE-NAME {frame}", thread, *args)
        command = f'SLYNK:EVAL-STRING-IN-FRAME {dumps(expression)} {frame} "{str(interpackage)}"'
        result = await self.rex(command, thread, *args)
        return str(result)

    async def debug_step(self, frame, thread, *args):
        result = await self.rex(f"SLYNK:SLY-DB-STEP {frame}", thread, *args)
        return result

    async def debug_next(self, frame, thread, *args):
        result = await self.rex(f"SLYNK:SLY-DB-NEXT {frame}", thread, *args)
        return result

    async def debug_out(self, frame, thread, *args):
        result = await self.rex(f"SLYNK:SLY-DB-OUT {frame}", thread, *args)
        return result

    async def debug_break_on_return(self, frame, thread, *args):
        result = await self.rex(f"SLYNK:SLY-DB-BREAK-ON-RETURN {frame}", thread, *args)
        return result

    async def debug_break(self, function_name, thread, *args):
        result = await self.rex(f"SLYNK:SLY-DB-BREAK {dumps(function_name)}", thread, *args)
        return result
