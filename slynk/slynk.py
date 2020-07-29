import asyncio, threading, pathlib

try:
    from .util import *
    from .structs import *
    from .client import *
    from . import inspector, documentation, profiling, debug
except ImportError as e:
    print(f"ImportError encoutered, switching gears: {e}")
    from util import *
    from structs import *
    from client import *
    from . import inspector, documentation, profiling, debug

class SlynkClient(
        Dispatcher,
        inspector.Inspector,
        documentation.Documentation,
        profiling.Profiling,
        debug.Debug):
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
        expression = loads(data.decode("utf-8"))
        command = str(expression[0]).lower()[1:]  # This should be a keyword symbol
        parameter = expression[1]
        if command == "return":
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
        answer = await self._futured_emit("read_from_minibuffer", prompt, initial_value)
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
    async def create_repl(self, information_needed=False):
        id, channel = self.make_channel()
        repl = Repl(channel)
        information = await self.rex(f"slynk-mrepl:create-mrepl {id}", "T")
        self.repls.append(repl)
        if information_needed:
            return repl, information
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

    async def eval(self, expression_string, is_region, *args):
        package = (args[0] if len(args) > 0 and args[0] is not None 
                           else "COMMON-LISP-USER")
        mode = "-REGION" if is_region else ""
        command = f"SLYNK:INTERACTIVE-EVAL{mode} {dumps(expression_string)}"
        result = await self.rex(command, "T", package)
        return result

    async def compile_string(self, string, buffer_name, file_name, position, stickers=None,
                             compilation_policy="'NIL", package=DEFAULT_PACKAGE):
        if type(position) == tuple and len(position) > 2:
            position = f"(:POSITION {position[0]}) (:LINE {position[1]} {position[2]})"
        else:
            position = f"(:POSITION {position})"

        command = " ".join(
            (["SLYNK:COMPILE-STRING-FOR-EMACS"] if not stickers else [
                    "slynk-stickers:compile-for-stickers", 
                    dumps(Quoted(stickers))])
            + [dumps(string),
               dumps(buffer_name),
               f"(QUOTE ({position}))",
               dumps(file_name),
               str(compilation_policy)])
  
        result = await self.rex(command, "T", package)

        if stickers:
            stickers_stuck = result[0]
            result = result[1]
        if str(result[0]).lower() == ":compilation-result":
            if stickers:
                return parse_compilation_information(result), stickers_stuck
            return parse_compilation_information(result)
        if stickers:
            return result, stickers_stuck
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

    async def toggle_sticker_breaking(self, *args):
        result = await self.rex("slynk-stickers:toggle-break-on-stickers", *args)
        return result

    async def sticker_recording(self, key: str, ignored_ids: List[int], 
            should_ignore_zombies=False, zombies: List[int] = [], direction: int = 0, 
            command: str = "nil", *args):
        result = await self.rex(
            f"""slynk-stickers:search-for-recording 
                '{key} '{dumps(ignored_ids)} '{dumps(should_ignore_zombies)} 'nil {direction} '{command}""",
            *args)
        return result

    async def sticker_fetch(self, dead_stickers: List[int], *args):
        result = await self.rex(f"slynk-stickers:fetch '{dumps(dead_stickers)}")
        return result

    async def disassemble(self, symbol, *args):
        result = await self.rex(f"slynk:disassemble-form {dumps(symbol)}", *args)
        return result

    async def xref(self, symbol: str, mode="calls", *args) -> List[Tuple[str, Location]]:
        result = await self.rex(f"""slynk:xref ':{mode} '"{symbol}\"""", *args)
        return [(name, parse_location(location)) for name, location in result]

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


async def mainA(x, y, actions):
    print("main")
    await x.connect(asyncio.get_event_loop())
    await x.prepare()
    if "repl" in actions:
        repl, info = await x.create_repl()
        print("REPL prepared")
        print(info)
    if "docs" in actions:
        d = await x.documentation_symbol("print")
        print(d)
        print(await x.autodoc("(print 12)", 5))
    if "mp" in actions:
        print("hi")
        print(await x.expand("(loop for x from 1 to 5 do (print x))"))
        print(await x.expand("(loop for x from 1 to 5 do (print x))"))
    if "xref" in actions:
        print(xref("evolution::move"))
    while (evaluee := input("a>>")) != "quit":
        eval(evaluee, globals(), locals())
    x.disconnect()
    # x.eval("(+ 2 2)")


def main(actions):
    PYTHONASYNCIODEBUG = 1
    loop = asyncio.new_event_loop()
    x = SlynkClient("localhost", 4005)
    y = TestListener(x, loop)
    loop.create_task(mainA(x, y, actions))
    threading.Thread(target=loop.run_forever).start()
    print("Anyways return")
    return x


if __name__ == '__main__':
    main(["xref"])
