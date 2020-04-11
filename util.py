import asyncio

def get_if_in(dictionary, *items):
    return tuple(dictionary[item] if item in dictionary else None 
                                  for item in items)

async def show_input_panel(session, prompt, initial_value, on_change=None):
    future = session.loop.create_future()
    print("OK")
    def on_confirm(value):
        nonlocal future
        nonlocal session
        async def set_result(future, value):
            future.set_result(value)
        asyncio.run_coroutine_threadsafe(set_result(future, value), session.loop)
    def on_cancel():
        nonlocal future
        nonlocal session
        async def set_result(future):
            future.cancelled()
        asyncio.run_coroutine_threadsafe(set_result(future), session.loop)
    session.window.show_input_panel(prompt, initial_value, on_confirm, on_change, on_cancel)
    await future
    return future.result()

async def show_quick_panel(session, items, flags, selected_index=0, on_highlighted=None):
    future = session.loop.create_future()
    print("OK")
    def on_done(index):
        nonlocal future
        nonlocal session
        async def set_result(future, index):
            future.set_result(index)
        asyncio.run_coroutine_threadsafe(set_result(future, index), session.loop)
    session.window.show_quick_panel(items, on_done, flags, selected_index, on_highlighted)
    await future
    return future.result()
