import asyncio, threading, pathlib
from sys import maxsize

try:
    from .util import *
    from .structs import *
except ImportError as e:
    print(f"ImportError encoutered, switching gears: {e}")
    from util import *
    from structs import *

class Inspector:
    async def parse_inspection(self, result, *args):
        if not result:
            return None
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        inspection = InspectionData("", -1, [])
        raw_content = []
        for (key, value) in zip(result, result[1:]):
            key = key.upper()
            if key == ":TITLE":
                inspection.title = value
            elif key == ":CONTENT":
                raw_content = value
            else:
                print(f"Unknown key {key} found in presentation results")

        [content_description, content_length, content_start, content_end] = raw_content

        if content_end < content_length:
            result_1 = await self.rex(f"SLYNK:INSPECTOR-RANGE {str(content_length)} {maxsize}", "T", package)
            content_description_1 = result_1[0]
            if int(result_1[3]) <= int(result_1[1]):
                raise Exception("Continues to miss part of the inspection")
            content_description += content_description_1

        inspection.content = [
            [element[0], element[1], element[2]] if type(element) != str else element
            for element in content_description]

        return inspection

    # Careful, the format for commands here is as a list and not
    # a precomposed string
    async def eval_for_inspector(self, slyfun, *args, 
                                # Keyword arguments in the original
                                 package=DEFAULT_PACKAGE,
                                 error_message="Inspection Failed",
                                 restore_point=None, 
                                 save_selected_window=False,
                                 current_inspector=None,
                                 target_inspector=None):
                            # (Due to encapsulation, opener is non-present)
        if not target_inspector:
            target_inspector = self.current_inspector
        if not current_inspector:
            current_inspector = self.current_inspector

        query = " ".join([
            "SLYNK:EVAL-FOR-INSPECTOR",
            dumps(current_inspector),
            dumps(target_inspector),
            f"'{slyfun}", 
        ] + [dumps(element) for element in args])
        result = await self.rex(query, "T", package)
        return result

    async def inspect(self, query, current_inspector=None, target_inspector=None, package=DEFAULT_PACKAGE):
        result = await self.eval_for_inspector(
            "SLYNK:INIT-INSPECTOR", query,
            target_inspector=target_inspector,
            current_inspector=current_inspector,
            package=package)
        return parse_inspection(result)

    async def inspect_part(self, part, current_inspector=None, target_inspector=None):
        result = await self.eval_for_inspector(
            "SLYNK:INSPECT-NTH-PART", part,
            target_inspector=target_inspector,
            current_inspector=current_inspector)
        return parse_inspection(result)

    async def inspector_call_action(self, action, current_inspector=None, target_inspector=None):
        result = await self.eval_for_inspector(
            "SLYNK::INSPECTOR-CALL-NTH-ACTION", action,
            target_inspector=target_inspector,
            current_inspector=current_inspector)
        return parse_inspection(result)

    async def inspector_previous(self, current_inspector=None, target_inspector=None):
        result = await self.eval_for_inspector(
            "SLYNK:INSPECTOR-POP",
            target_inspector=target_inspector,
            current_inspector=current_inspector)
        return parse_inspection(result)

    async def inspector_next(self, current_inspector=None, target_inspector=None):
        result = await self.eval_for_inspector(
            "SLYNK:INSPECTOR-NEXT",
            target_inspector=target_inspector,
            current_inspector=current_inspector)
        return parse_inspection(result)

    async def reinspect(self, current_inspector=None, target_inspector=None):
        result = await self.eval_for_inspector(
            "SLYNK:INSPECTOR-REINSPECT",
            target_inspector=target_inspector,
            current_inspector=current_inspector)
        return parse_inspection(result)

    async def toggle_verbose_inspection(self, current_inspector=None, target_inspector=None):
        result = await self.eval_for_inspector(
            "SLYNK:INSPECTOR-REINSPECT",
            target_inspector=target_inspector,
            current_inspector=current_inspector)
        return parse_inspection(result)

    async def inspect_presentation(self, presentation_id, should_reset=False, *args):
        should_reset = "T" if len(args) > 0 and args[0] else "NIL"
        inspection_result = await self.rex(f"SLYNK:INSPECT-PRESENTATION {str(presentation_id)} {dumps(should_reset)}",
                                           ":REPL-THREAD", *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_frame_var(self, frame_index, variable, thread, *args):
        inspection_result = await self.rex(f"SLYNK:INSPECT-FRAME-VAR {str(frame_index)} {str(variable)}", thread, *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_in_frame(self, frame_index, expression_string, thread, *args):
        inspection_result = await self.rex(f"SLYNK:INSPECT-IN-FRAME {dumps(expression_string)} {str(frame_index)}",
                                           thread, *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_current_condition(self, thread, *args):
        inspection_result = await self.rex(f"SLYNK:INSPECT-CURRENT-CONDITION", thread, *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_nth_part(self, n, *args):
        inspection_result = await self.rex(f"SLYNK:INSPECT-NTH-PART {str(n)}", ":REPL-THREAD", *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_call_action(self, n, *args):
        inspection_result = await self.rex(f"SLYNK:INSPECTOR-CALL-NTH-ACTION {str(n)}", ":REPL-THREAD", *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_previous_object(self, *args):
        inspection_result = await self.rex("SLYNK:INSPECTOR-POP", ":REPL-THREAD", *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result

    async def inspect_next_object(self, *args):
        inspection_result = await self.rex("SLYNK:INSPECTOR-NEXT", ":REPL-THREAD", *args)
        result = await self.parse_inspection(inspection_result, *args)
        return result