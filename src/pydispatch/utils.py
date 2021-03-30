import sys
import weakref
from _weakref import ref
try:
    from _weakref import _remove_dead_weakref
except ImportError:
    def _remove_dead_weakref(o, key):
        del o[key]
import types

AIO_AVAILABLE = sys.version_info >= (3, 5)
if AIO_AVAILABLE:
    import asyncio
else:
    asyncio = None

PY2 = sys.version_info.major == 2
if not PY2:
    basestring = str

def get_method_vars(m):
    if PY2:
        f = m.im_func
        obj = m.im_self
    else:
        f = m.__func__
        obj = m.__self__
    return f, obj

def iscoroutinefunction(obj):
    if AIO_AVAILABLE:
        return asyncio.iscoroutinefunction(obj)
    return False

class WeakMethodContainer(weakref.WeakValueDictionary):
    """Container to store weak references to callbacks

    Instance methods are stored using the underlying :term:`function` object
    and the instance id (using :func:`id(obj) <id>`) as the key (a two-tuple)
    and the object itself as the value. This ensures proper weak referencing.

    Functions are stored using the string "function" and the id of the function
    as the key (a two-tuple).
    """
    def keys(self):
        if PY2:
            return self.iterkeys()
        return super(WeakMethodContainer, self).keys()
    def add_method(self, m, **kwargs):
        """Add an instance method or function

        Args:
            m: The instance method or function to store
        """
        if isinstance(m, types.FunctionType):
            self['function', id(m)] = m
        else:
            f, obj = get_method_vars(m)
            wrkey = (f, id(obj))
            self[wrkey] = obj
    def del_method(self, m):
        """Remove an instance method or function if it exists

        Args:
            m: The instance method or function to remove
        """
        if isinstance(m, types.FunctionType) and not iscoroutinefunction(m):
            wrkey = ('function', id(m))
        else:
            f, obj = get_method_vars(m)
            wrkey = (f, id(obj))
        if wrkey in self:
            del self[wrkey]
    def del_instance(self, obj):
        """Remove any stored instance methods that belong to an object

        Args:
            obj: The instance object to remove
        """
        to_remove = set()
        for wrkey, _obj in self.iter_instances():
            if obj is _obj:
                to_remove.add(wrkey)
        for wrkey in to_remove:
            del self[wrkey]
    def iter_instances(self):
        """Iterate over the stored objects

        Yields:
            wrkey: The two-tuple key used to store the object
            obj: The instance or function object
        """
        for wrkey in set(self.keys()):
            obj = self.get(wrkey)
            if obj is None:
                continue
            yield wrkey, obj
    def iter_methods(self):
        """Iterate over stored functions and instance methods

        Yields:
            Instance methods or function objects
        """
        for wrkey, obj in self.iter_instances():
            f, obj_id = wrkey
            if f == 'function':
                yield self[wrkey]
            else:
                yield getattr(obj, f.__name__)

class InformativeDict(dict):
    def __delitem__(self, key):
        super(InformativeDict, self).__delitem__(key)
        self.del_callback(key)

class InformativeWVDict(weakref.WeakValueDictionary):
    """A WeakValueDictionary providing a callback for deletion

    Keyword Arguments:
        del_callback: A callback function that will be called when an item is
            either deleted or dereferenced. It will be called with the key as
            the only argument.
    """
    def __init__(self, **kwargs):
        self.del_callback = kwargs.get('del_callback')
        weakref.WeakValueDictionary.__init__(self)
        def remove(wr, selfref=ref(self)):
            self = selfref()
            if self is not None:
                if self._iterating:
                    self._pending_removals.append(wr.key)
                else:
                    # Atomic removal is necessary since this function
                    # can be called asynchronously by the GC
                    _remove_dead_weakref(self.data, wr.key)
                    self._data_del_callback(wr.key)
        self._remove = remove
        self.data = InformativeDict()
        self.data.del_callback = self._data_del_callback
    def _data_del_callback(self, key):
        self.del_callback(key)

class EmissionHoldLock_(object):
    """Context manager used for :meth:`pydispatch.dispatch.Dispatcher.emission_lock`

    Args:
        event_instance: The :class:`~pydispatch.dispatch.Event` instance
            associated with the lock

    Attributes:
        event_instance: The :class:`~pydispatch.dispatch.Event` instance
            associated with the lock
        last_event: The positional and keyword arguments from the event's last
            emission as a two-tuple. If no events were triggered while the lock
            was held, :obj:`None`.
        held (bool): The internal state of the lock
    """
    def __init__(self, event_instance):
        self.event_instance = event_instance
        self.last_event = None
        self.held = False
    def acquire(self):
        if self.held:
            return
        self.held = True
        self.last_event = None
    def release(self):
        if not self.held:
            return
        if self.last_event is not None:
            args, kwargs = self.last_event
            self.last_event = None
            self.held = False
            self.event_instance(*args, **kwargs)
    def __enter__(self):
        self.acquire()
        return self
    def __exit__(self, *args):
        self.release()

if AIO_AVAILABLE:
    from .aioutils import AioEmissionHoldLock
    class EmissionHoldLock(EmissionHoldLock_, AioEmissionHoldLock):
        pass
else:
    EmissionHoldLock = EmissionHoldLock_
