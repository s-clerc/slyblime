import types

from .utils import (
    WeakMethodContainer,
    EmissionHoldLock,
    AIO_AVAILABLE,
    iscoroutinefunction,
)
from .properties import Property
if AIO_AVAILABLE:
    import asyncio
    from .aioutils import AioWeakMethodContainer, AioEventWaiters


class Event(object):
    """Holds references to event names and subscribed listeners

    This is used internally by :class:`Dispatcher`.
    """
    __slots__ = ('name', 'listeners', 'aio_waiters', 'aio_listeners', 'emission_lock')
    def __init__(self, name):
        self.name = name
        self.listeners = WeakMethodContainer()
        if AIO_AVAILABLE:
            self.aio_listeners = AioWeakMethodContainer()
            self.aio_waiters = AioEventWaiters()
        self.emission_lock = EmissionHoldLock(self)
    def add_listener(self, callback, **kwargs):
        if AIO_AVAILABLE:
            if iscoroutinefunction(callback):
                loop = kwargs.get('__aio_loop__')
                if loop is None:
                    raise RuntimeError('Coroutine function given without event loop')
                self.aio_listeners.add_method(loop, callback)
                return
        self.listeners.add_method(callback)
    def remove_listener(self, obj):
        if isinstance(obj, (types.MethodType, types.FunctionType)):
            self.listeners.del_method(obj)
            if AIO_AVAILABLE:
                self.aio_listeners.del_method(obj)
        else:
            self.listeners.del_instance(obj)
            if AIO_AVAILABLE:
                self.aio_listeners.del_instance(obj)
    def __call__(self, *args, **kwargs):
        """Dispatches the event to listeners

        Called by :meth:`~Dispatcher.emit`
        """
        if self.emission_lock.held:
            self.emission_lock.last_event = (args, kwargs)
            return
        if AIO_AVAILABLE:
            self.aio_waiters(*args, **kwargs)
            self.aio_listeners(*args, **kwargs)
        for m in self.listeners.iter_methods():
            r = m(*args, **kwargs)
            if r is False:
                return r
    if AIO_AVAILABLE:
        def __await__(self):
            return self.aio_waiters.__await__()
    def __repr__(self):
        return '<{}: {}>'.format(self.__class__, self)
    def __str__(self):
        return self.name

class Dispatcher(object):
    """Core class used to enable all functionality in the library

    Interfaces with :class:`Event` and :class:`~pydispatch.properties.Property`
    objects upon instance creation.

    Events can be created by calling :meth:`register_event` or by the subclass
    definition::

        class Foo(Dispatcher):
            _events_ = ['awesome_event', 'on_less_awesome_event']

    Once defined, an event can be dispatched to listeners by calling :meth:`emit`.
    """
    __initialized_subclasses = set()
    __skip_initialized = True
    def __new__(cls, *args, **kwargs):
        def iter_bases(_cls):
            if _cls is not object:
                yield _cls
                for b in _cls.__bases__:
                    for _cls_ in iter_bases(b):
                        yield _cls_
        skip_initialized = Dispatcher._Dispatcher__skip_initialized
        if not skip_initialized or cls not in Dispatcher._Dispatcher__initialized_subclasses:
            props = {}
            events = set()
            for _cls in iter_bases(cls):
                for attr in dir(_cls):
                    prop = getattr(_cls, attr)
                    if attr not in props and isinstance(prop, Property):
                        props[attr] = prop
                        prop.name = attr
                    _events = getattr(_cls, '_events_', [])
                    events |= set(_events)
            cls._PROPERTIES_ = props
            cls._EVENTS_ = events
            if skip_initialized:
                Dispatcher._Dispatcher__initialized_subclasses.add(cls)
        obj = super(Dispatcher, cls).__new__(cls)
        obj._Dispatcher__init_events()
        return obj
    def __init__(self, *args, **kwargs):
        # Everything is handled by __new__
        # This is only here to prevent exceptions being raised
        pass
    def __init_events(self):
        if hasattr(self, '_Dispatcher__events'):
            return
        self.__events = {}
        for name in self._EVENTS_:
            self.__events[name] = Event(name)
        self.__property_events = {}
        for name, prop in self._PROPERTIES_.items():
            self.__property_events[name] = Event(name)
            prop._add_instance(self)
    def register_event(self, *names):
        """Registers new events after instance creation

        Args:
            *names (str): Name or names of the events to register
        """
        for name in names:
            if name in self.__events:
                continue
            self.__events[name] = Event(name)
    def bind(self, **kwargs):
        """Subscribes to events or to :class:`~pydispatch.properties.Property` updates

        Keyword arguments are used with the Event or Property names as keys
        and the callbacks as values::

            class Foo(Dispatcher):
                name = Property()

            foo = Foo()

            foo.bind(name=my_listener.on_foo_name_changed)
            foo.bind(name=other_listener.on_name,
                     value=other_listener.on_value)

        The callbacks are stored as weak references and their order is not
        maintained relative to the order of binding.

        **Async Callbacks**:

            Callbacks may be :term:`coroutine functions <coroutine function>`
            (defined using :keyword:`async def` or decorated with
            :func:`@asyncio.coroutine <asyncio.coroutine>`), but an event loop
            must be explicitly provided with the keyword
            argument ``"__aio_loop__"`` (an instance of
            :class:`asyncio.BaseEventLoop`)::

                import asyncio
                from pydispatch import Dispatcher

                class Foo(Dispatcher):
                    _events_ = ['test_event']

                class Bar(object):
                    def __init__(self):
                        self.got_foo_event = asyncio.Event()
                    async def wait_for_foo(self):
                        await self.got_foo_event.wait()
                        print('got foo!')
                    async def on_foo_test_event(self, *args, **kwargs):
                        self.got_foo_event.set()

                foo = Foo()
                bar = Bar()

                loop = asyncio.get_event_loop()
                foo.bind(test_event=bar.on_foo_test_event, __aio_loop__=loop)

                loop.run_until_complete(bar.wait_for_foo())

            This can also be done using :meth:`bind_async`.

            .. versionadded:: 0.1.0

        """
        aio_loop = kwargs.pop('__aio_loop__', None)
        props = self.__property_events
        events = self.__events
        for name, cb in kwargs.items():
            if name in props:
                e = props[name]
            else:
                e = events[name]
            e.add_listener(cb, __aio_loop__=aio_loop)
    def unbind(self, *args):
        """Unsubscribes from events or :class:`~pydispatch.properties.Property` updates

        Multiple arguments can be given. Each of which can be either the method
        that was used for the original call to :meth:`bind` or an instance
        object.

        If an instance of an object is supplied, any previously bound Events and
        Properties will be 'unbound'.
        """
        props = self.__property_events.values()
        events = self.__events.values()
        for arg in args:
            for prop in props:
                prop.remove_listener(arg)
            for e in events:
                e.remove_listener(arg)
    def bind_async(self, loop, **kwargs):
        """Subscribes to events with async callbacks

        Functionality is matches the :meth:`bind` method, except the provided
        callbacks should be coroutine functions. When the event is dispatched,
        callbacks will be placed on the given event loop.

        For keyword arguments, see :meth:`bind`.

        Args:
            loop: The :class:`EventLoop <asyncio.BaseEventLoop>` to use when
                events are dispatched

        Availability:
            Python>=3.5

        .. versionadded:: 0.1.0
        """
        kwargs['__aio_loop__'] = loop
        self.bind(**kwargs)
    def emit(self, name, *args, **kwargs):
        """Dispatches an event to any subscribed listeners

        Note:
            If a listener returns :obj:`False`, the event will stop dispatching to
            other listeners. Any other return value is ignored.

        Args:
            name (str): The name of the :class:`Event` to dispatch
            *args (Optional): Positional arguments to be sent to listeners
            **kwargs (Optional): Keyword arguments to be sent to listeners
        """
        e = self.__property_events.get(name)
        if e is None:
            e = self.__events[name]
        return e(*args, **kwargs)
    def get_dispatcher_event(self, name):
        """Retrieves an Event object by name

        Args:
            name (str): The name of the :class:`Event` or
                :class:`~pydispatch.properties.Property` object to retrieve

        Returns:
            The :class:`Event` instance for the event or property definition

        .. versionadded:: 0.1.0
        """
        e = self.__property_events.get(name)
        if e is None:
            e = self.__events[name]
        return e
    def emission_lock(self, name):
        """Holds emission of events and dispatches the last event on release

        The context manager returned will store the last event data called by
        :meth:`emit` and prevent callbacks until it exits. On exit, it will
        dispatch the last event captured (if any)::

            class Foo(Dispatcher):
                _events_ = ['my_event']

            def on_my_event(value):
                print(value)

            foo = Foo()
            foo.bind(my_event=on_my_event)

            with foo.emission_lock('my_event'):
                foo.emit('my_event', 1)
                foo.emit('my_event', 2)

            >>> 2

        Args:
            name (str): The name of the :class:`Event` or
                :class:`~pydispatch.properties.Property`

        Returns:
            A context manager to be used by the :keyword:`with` statement.

            If available, this will also be an async context manager to be used
            with the :keyword:`async with` statement (see `PEP 492`_).

        Note:
            The context manager is re-entrant, meaning that multiple calls to
            this method within nested context scopes are possible.

        .. _PEP 492: https://www.python.org/dev/peps/pep-0492/#asynchronous-context-managers-and-async-with
        """
        e = self.__property_events.get(name)
        if e is None:
            e = self.__events[name]
        return e.emission_lock
