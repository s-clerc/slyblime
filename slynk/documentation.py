import asyncio, threading, pathlib

try:
    from .util import *
    from .structs import *
except ImportError as e:
    print(f"ImportError encoutered, switching gears: {e}")
    from util import *
    from structs import *

class Documentation:
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

    # defslyfuns
    async def describe(self, expression_string: str,  mode="symbol", *args):
        result = await self.rex(f"SLYNK:DESCRIBE-{mode.upper()} {dumps(expression_string)}", *args)
        return result
        
    # A defslyfun
    async def documentation_symbol(self, symbol_name):
        documentation = await self.rex(f'SLYNK:DOCUMENTATION-SYMBOL "{symbol_name}"')
        return documentation

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
        
    async def expand(self, form, package=DEFAULT_PACKAGE, name=False, recursively=True, macros=True, compiler_macros=True):
        if macros and compiler_macros:
            function_name = "EXPAND"
        elif macros:
            function_name = "MACROEXPAND"
        elif compiler_macros:
            function_name = "COMPILER-MACROEXPAND"
        else:
            function_name = "nothing"
            print(f"Trivial macroëxpanding being used for {form}")
            return form

        if str(recursively).upper() == "ALL":
            if macros and not compiler_macros:
                function_name += "-ALL"
            else:
                raise Exception("only macroexpand may use a repetition of ALL")
        elif not recursively:
            function_name += "-1"

        result = await self.rex(f"SLYNK:SLYNK-{function_name} {dumps(form)}", "T", package)
        if name:
            return result, function_name
        return result