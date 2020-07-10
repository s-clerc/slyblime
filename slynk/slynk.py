import asyncio, threading, pathlib
from sys import maxsize

try:
    from .util import *
    from .structs import *
except ImportError as e:
    print(f"ImportError encoutered, switching gears: {e}")
    from util import *
    from structs import *


class SlynkClientProtocol(Dispatcher, asyncio.Protocol):
    _events_ = [
        "reception",
        "connect",
        "disconnect"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.partial_message = None
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.emit("connect")

    def connection_lost(self, something):
        self.emit("disconnect", something)

    def complete_data(self, data):
        if self.partial_message is None:
            packet_size = int(data[0:6].decode("utf-8"), 16)
            if len(data) - 6 < packet_size:
                self.partial_message = data
                return None
            else:  # Data is already complete
                return data
        else:
            self.partial_message += data
            packet_size = int(self.partial_message[0:6].decode("utf-8"), 16)
            if len(self.partial_message) - 6 < packet_size:
                return None
            else:  # Data is finally complete
                data = self.partial_message
                self.partial_message = None
                return data

    def data_received(self, data):
        data = self.complete_data(data)
        if data is None:
            return
        packet_size = int(data[0:6].decode("utf-8"), 16)
        # print(data)
        self.emit("reception", data[6:packet_size + 6])

        remainder = data[packet_size + 6:]
        if len(remainder) > 5:  # sanity check
            # print("Remainder: ")
            # print(remainder)
            self.data_received(remainder)
        elif len(remainder) > 0:
            print("Erroneous remainder of ")
            print(remainder)

    def write(self, message):
        output = message.encode("utf-8")
        length = str(hex(len(output)))[2:].zfill(6).upper()
        buffer = length.encode("utf-8") + output
        self.transport.write(buffer)
        print(buffer)


class SlynkClient(Dispatcher):
    request_table: Dict[int, PromisedRequest]
    _events_ = [
        "connect",
        "write_string",
        "presentation_start",
        "presentation_end",
        "new_package",
        "debug_activate",
        "debug_setup",
        "debug_return",
        "read_from_minibuffer",
        "y_or_n_p",
        "read_string",
        "read_aborted",
        "profile_command_complete",  # only present for completeness, avoid using
        "disconnect"
    ]

    DEFAULT_PACKAGE = "COMMON-LISP-USER"

    def __init__(self, host, port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = host
        self.port = port
        self.connexion = None
        self.connected = False
        self.request_counter = 1
        self.request_table = {}
        # Channel ids seem to be from N*
        self.channels = [None]
        self.output_buffer = "".encode("utf-8")
        self.loop = None
        self.closed_future = None
        self.debug_data = None
        self.repls = []
        self.connexion_info = None
        self.current_inspector = None

    async def connect(self, *args):
        if len(args) > 0:
            self.loop = args[0]
        else:
            self.loop = asyncio.new_event_loop()
            threading.Thread(target=self.loop.run_forever)
        self.connexion = SlynkClientProtocol()
        self.connexion.bind(connect=self.handle_connect,
                            disconnect=self.handle_close,
                            reception=self.handle_read,
                            __aio_loop__=self.loop)
        await self.loop.create_connection(lambda: self.connexion,
                                          self.host, self.port)
        await self.update_connexion_info()
        self.closed_future = self.loop.create_future()

    async def closed(self):
        await self.closed_future
        return self.closed_future.result()

    def send_message(self, message):
        self.connexion.write(message)

    def handle_connect(self):
        self.connected = True
        self.emit("connect")

    def handle_close(self, something):
        if self.connected:
            self.connected = False
            self.closed_future.set_result(True)
            self.emit("disconnect")

    async def handle_read(self, data):
        print(f"handle-read: {data}")
        expression = loads(data.decode("utf-8"))
        command = str(expression[0]).lower()[1:]  # This should be a keyword symbol
        parameter = expression[1]
        if command == "return":
            print("return reception")
            self.rex_return_handler(expression)
        elif command == "write-string":
            self.emit("write_string", parameter)
        elif command == "presentation-start":
            self.emit("presentation_start", parameter)
        elif command == "presentation-end":
            self.emit("presentation_end", parameter)
        elif command == "new-package":
            self.emit("new_package", parameter)
        elif command == "debug":
            self.debug_setup_handler(expression)
        elif command == "debug-activate":
            self.debug_activate_handler(expression)
        elif command == "debug-return":
            self.debug_return_handler(expression)
        elif command == "read-from-minibuffer":
            await self.read_from_minibuffer_handler(expression)
        elif command == "y-or-n-p":
            await self.y_or_n_handler(expression)
        elif command == "read-string":
            await self.read_string_handler(expression)
        elif command == "read-aborted":
            self.read_aborted_handler(expression)
        elif command == "ping":
            self.ping_handler(expression)
        elif command == "channel-send":
            self.channels[parameter].message_recieved(expression[2])
        else:
            print("Danger, unknown command: " + command)

    def make_channel(self):
        id = len(self.channels)
        self.channels.append(Channel(self, id))
        return id, self.channels[id]

    def ping_handler(self, expression):
        self.send_message("(:EMACS-PONG " + str(expression[1]) + " " + str(expression[2]) + ")")

    async def rex(self, command, thread="T", package=DEFAULT_PACKAGE):
        id = self.request_counter
        self.request_counter += 1
        message = f"(:EMACS-REX ({command}) {dumps(package)} {str(thread)} {str(id)})"
        self.send_message(message)
        # This future will be returned when emacs returns.
        future = self.loop.create_future()
        request = PromisedRequest(id, command, package, future)
        self.request_table[request.id] = request
        await future
        return future.result()

    def rex_return_handler(self, expression):
        status = str(expression[1][0]).lower()
        return_value = expression[1][1]
        id = int(expression[2])
        if id in self.request_table:
            request = self.request_table[id]
            del self.request_table[id]
            if request.future.cancelled():
                return
            request.future.set_result(return_value)
        else:
            print(str(self.request_table))
            print(f"Danger, received rex response for unknown command id {id}")

    async def _futured_emit(self, name, *args, **kwargs):
        future = self.loop.create_future()
        # In practice there will only be only such handler for the following
        # but in the interests of consistency (laziness), it is done using an event
        # listener.
        self.emit(name, *args, future, **kwargs)
        await future
        return future.result()

    async def read_from_minibuffer_handler(self, expression):
        thread, tag, prompt, initial_value = extract_question_properties(expression)
        print("OK")
        answer = await self._futured_emit("read_from_minibuffer", prompt, initial_value)
        print("DOK")
        self.send_message(f"(:EMACS-RETURN {thread} {tag} {dumps(answer)})")

    async def y_or_n_handler(self, expression):
        thread, tag, prompt, initial_value = extract_question_properties(expression)
        answer = await self._futured_emit("y_or_n_p", prompt)
        self.send_message(f"(:EMACS-RETURN {thread} {tag} {dumps(answer)})")

    async def read_string_handler(self, expression):
        thread, tag = extract_properties(expression)
        string = await self._futured_emit("read_string", tag)
        self.send_message(f"(:EMACS-RETURN-STRING {thread} {tag} {dumps(string)})")

    def read_aborted_handler(self, expression):
        thread, tag = extract_properties(expression)
        self.emit("read_aborted", tag)

    # A slyfun
    async def require(self, modules):
        if type(modules) != list:
            modules = [modules]  # Only one module
        command = f"SLYNK:SLYNK-REQUIRE '{dumps(modules)}"
        result = await self.rex(command, "T", "NIL")
        return result

    async def add_load_paths(self, paths):
        if type(paths) != list:
            paths = [paths]
        command = f"SLYNK:SLYNK-ADD-LOAD-PATHS '{dumps(paths)}"
        result = await self.rex(command, "T")
        return result

    ### Higher-level commands
    async def create_repl(self):
        id, channel = self.make_channel()
        repl = Repl(channel)
        await self.rex(f"slynk-mrepl:create-mrepl {id}", "T")
        self.repls.append(repl)
        return repl

    async def prepare(self, path=pathlib.Path().parent.absolute()):
        # Missing C-P-C, Fuzzy, Presentations from SLIMAß
        await self.add_load_paths(f"{path}/sly/contrib/")
        await self.require(
            ["slynk/indentation",
             "slynk/stickers",
             "slynk/trace-dialog",
             "slynk/package-fu",
             "slynk/fancy-inspector",
             "slynk/mrepl",
             "slynk/arglists"])
        # await self.rex("SLYNK:INIT-PRESENTATIONS", "T", "COMMON-LISP-USER")
        # await self.rex("SLYNK-REPL:CREATE-REPL NIL :CODING-SYSTEM \"utf-8-unix\"", "T", "COMMON-LISP-USER")
        return

    async def autodoc(self, expression_string, cursor_position, *args):
        expression = loads(expression_string)
        cursor_marker = Symbol("SLYNK::%CURSOR-MARKER%")
        try:
            output_forms = []
            is_cursor_placed = False
            previous_length = 0
            for form in expression:
                output_forms.append(str(form))
                new_length = previous_length + len(dumps(form))
                is_cursor_within_form = previous_length <= cursor_position <= new_length
                if is_cursor_within_form and not is_cursor_placed:
                    break
                previous_length = new_length
            # We're doing the weird thing below, because at the time
            # sexpdata was doing this weird thing where 
            # `dumps(Symbol("SLYNK::%CURSOR-MARKER%"))` => `'"SLYNK::%CURSOR-MARKER"'`
            command = f"SLYNK:AUTODOC '{dumps(output_forms)[:-1]} SLYNK::%CURSOR-MARKER%) :PRINT-RIGHT-MARGIN 80"
        except Exception as e:
            print("Error constructing command")
            print(e)
            return Symbol(":NOT-AVAILABLE")
        else:
            response = await self.rex(command, *args)
            return response[0] if len(response) > 1 else Symbol(":NOT-AVAILABLE")

    # A defslyfun
    async def apropos(self, pattern, external_only=True, case_sensitive=False, *args):
        command = f"slynk-apropos:apropos-list-for-emacs {dumps(pattern)} {dumps(external_only)} {dumps(case_sensitive)}"
        propos_list = await self.rex(command, "T", *args)
        x = [property_list_to_dict(plist) for plist in propos_list]
        return x

    async def completions(self, pattern, package=DEFAULT_PACKAGE, flex=True):
        pattern = dumps(pattern)
        command = f"SLYNK-COMPLETION:{'FLEX' if flex else 'SIMPLE'}-COMPLETIONS (QUOTE {pattern}) \"{package}\""
        response = await self.rex(command, "T", package)
        return [Completion(*completion[:-1], completion[3].split(","))
                for completion in response[0]]

    async def eval(self, expression_string, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        command = f"SLYNK-REPL:LISTENER-EVAL {dumps(expression_string)}"
        result = await self.rex(command, ":REPL-THREAD", package)
        return result

    ### Debugging stuff
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
            [(int(frame[0]), str(frame[1]), is_restartable(frame)) for frame in expression[5]]
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
            response = await self.rex(f"SLYNK-FRAME-LOCALS-AND-CATCH-TAGS {str(index)}", thread, *args)
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
        command = f"SLYNK:EVAL-STRING-IN-FRAME {dumps(expression)} {frame} {str(interpackage)}"
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

    ### Inspector

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

    ### Profiling

    async def toggle_profiling_function(self, function_name, *args):
        result = await self.rex(f"SLYNK:TOGGLE-PROFILE-FDEFINITION {dumps(function_name)}", ":REPL-THREAD", *args)
        # self.emit("profile_command_complete", result)
        return result

    async def toggle_profiling_package(
            self, package, should_record_callers, should_profile_methods, *args):
        command = f"SLYNK:SLYNK-PROFILE-PACKAGE {dumps(package)} {dumps(should_record_callers)} {dumps(should_profile_methods)}"
        result = await self.rex(command, ":REPL-THREAD", *args)
        # self.emit("profile_command_complete", f"Attempting to profile {package}…")
        return result, f"Attempting to profile {package}…"

    async def stop_all_profiling(self, *args):
        result = await self.rex("SLYNK/BACKEND:UNPROFILE-ALL", ":REPL-THREAD", *args)
        # self.emit("profile_command_complete", result)
        return result

    async def reset_profiling(self, *args):
        result = await self.rex("SLYNK/BACKEND:PROFILE-RESET", ":REPL-THREAD", *args)
        # self.emit("profile_command_complete", result)
        return result

    async def profiling_report(self, *args):
        result = await self.rex("SLYNK/BACKEND:PROFILE-REPORT", ":REPL-THREAD", *args)
        # self.emit("profile_command_complete", "Profile report printed to REPL")
        return result, "Profile report printed to REPL"

    ### Code actions

    async def find_definitions(self, function_name, *args):
        raw_definitions = await self.rex(f"SLYNK:FIND-DEFINITIONS-FOR-EMACS {dumps(function_name)}", "T", *args)
        definitions = []
        for raw_definition in raw_definitions:
            try:
                location = parse_location(raw_definition[1])
                if location.buffer_type != "error":
                    definitions.append(Location(raw_definition[0], location))
            except Exception as e:
                print(f"Error find_definitions failed to parse {raw_definition}")
        return definitions

    async def compile_string(self, string, buffer_name, file_name, position,
                             compilation_policy="'NIL", package=DEFAULT_PACKAGE):
        if type(position) == tuple and len(position) > 2:
            position = f"(:POSITION {position[0]}) (:LINE {position[1]} {position[2]})"
        else:
            position = f"(:POSITION {position})"

        command = " ".join(
            ["SLYNK:COMPILE-STRING-FOR-EMACS",
             dumps(string),
             dumps(buffer_name),
             f"(QUOTE ({position}))",
             dumps(file_name),
             str(compilation_policy)])

        result = await self.rex(command, "T", package)

        if str(result[0]).lower() == ":compilation-result":
            return parse_compilation_information(result)
        return result

    async def compile_file(self, file_name, should_load=True, *args):
        result = await self.rex(f"SLYNK:COMPILE-FILE-FOR-EMACS {dumps(file_name)} {dumps(should_load)}", "T", *args)
        # result is (:compilation-result notes success duration load? output-pathname)
        indication = str(result[0]).lower()
        if indication == ":compilation-result":
            result = parse_compilation_information(result)
            if should_load and (result.success or should_load == "always") and result.path:
                await self.load_file(result.path, *args)
        return result

    async def load_file(self, file_name, *args):
        result = await self.rex(f"SLYNK:LOAD-FILE {dumps(file_name)}", "T", *args)
        return result

    async def expand(self, form, package=DEFAULT_PACKAGE, recursively=True, macros=True, compiler_macros=True):
        if macros and compiler_macros:
            function_name = "EXPAND"
        elif macros:
            function_name = "MACROEXPAND"
        elif compiler_macros:
            function_name = "COMPILER-MACROEXPAND"
        else:
            print(f"Trivial macroëxpanding being used for {form}")
            return form

        if str(recursively).upper() == "ALL":
            if macros and not compiler_macros:
                function_name += "-ALL"
            else:
                raise Exception("only macroexpand may use a repetition of ALL")
        elif not recursively:
            function_name += "-1"

        result = self.rex(f"SLYNK:SLYNK-{function_name} {dumps(form)}", "T", package)
        return result

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

    def interrupt(self):
        self.send_message(":EMACS-INTERRUPT :REPL-THREAD")

    async def quit(self):
        result = await self.rex("SLYNK/BACKEND:QUIT-LISP", "T")
        return result

    def disconnect(self):
        print("Disconnect called")
        self.send_message("(:emacs-channel-send 1 (:teardown))")
        self.loop.call_soon(self.connexion.transport.close)

    async def get_connexion_info(self):
        as_dict = None

        def convert(property):
            return DictAsObject(property_list_to_dict(as_dict[property]))

        data = await self.rex("SLYNK:CONNECTION-INFO", "T")
        as_dict = property_list_to_dict(data)

        # Pythonifying internal datastructures.
        return ConnexionInformation(
            as_dict["pid"],
            s[1:] if (s := str(as_dict["style"]))[0] == ":" else s,
            convert("encoding"),
            convert("lisp_implementation"),
            convert("machine"),
            # Remove colon from start of keyword
            [str(feature)[1:] for feature in as_dict["features"]],
            as_dict["modules"],
            convert("package"),
            as_dict["version"]
        )

    async def update_connexion_info(self):
        self.connexion_info = await self.get_connexion_info()
        return self.connexion_info


class TestListener:
    def __init__(self, client: SlynkClient, loop):
        self.client = client
        self.loop = loop
        self.debug_data = None
        client.bind(connect=self.on_connect,
                    disconnect=self.on_disconnect,
                    debug_setup=self.on_debug_setup,
                    debug_activate=self.on_debug_activate,
                    debug_return=self.on_debug_return)

    def on_connect(self):
        print("connexion")

    def on_disconnect(self):
        print("disconnexion")

    def on_debug_setup(self, data):
        print("Debug s")
        self.debug_data = data

    def on_debug_activate(self, data):
        print("debug A")
        r = self.debug_data.restarts
        print(r[len(r) - 1])
        self.loop.create_task(self.client.debug_invoke_restart(self.debug_data.level,
                                                               len(r) - 1,
                                                               self.debug_data.thread))

    def on_debug_return(self, data):
        print("debug R")


async def mainA(x, y, repl):
    print("main")
    await x.connect(asyncio.get_event_loop())
    await x.prepare()
    if repl:
        repl = await x.create_repl()
        print("REPL prepared")
    await x.closed()
    # x.eval("(+ 2 2)")


def main(repl):
    PYTHONASYNCIODEBUG = 1
    loop = asyncio.new_event_loop()
    x = SlynkClient("localhost", 4005)
    y = TestListener(x, loop)
    loop.create_task(mainA(x, y, repl))
    threading.Thread(target=loop.run_forever).start()
    print("Anyways return")
    return x


if __name__ == '__main__':
    main(True)
