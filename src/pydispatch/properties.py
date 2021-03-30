"""
:class:`Property` objects can be defined on subclasses of
:class:`~pydispatch.dispatch.Dispatcher` to create instance attributes that act
as events when their values change::

    from pydispatch import Dispatcher, Property

    class Foo(Dispatcher):
        name = Property()
        value = Property()
    def __str__(self):
        return self.__class__.__name__

    class Listener(object):
        def on_foo_name(self, instance, value, **kwargs):
            print("{}'s name is {}".format(instance, value))
        def on_foo_value(self, instance, value, **kwargs):
            print('{} = {}'.format(instance, value))

    foo_obj = Foo()
    listener_obj = Listener()

    foo_obj.bind(name=listener_obj.on_foo_name, value=listener_obj.on_foo_value)

    foo_obj.name = 'bar'
    # Foo's name is bar

    foo_obj.value = 42
    # Foo = 42

Type checking is not enforced, so values can be any valid python type.
Values are however checked for equality to avoid dispatching events for no
reason. If custom objects are used as values, they must be able to support
equality checking. In most cases, this will be handled automatically.
"""

import sys
import weakref

from .utils import InformativeWVDict

PY2 = sys.version_info < (3,)

class Property(object):
    """Defined on the class level to create an observable attribute

    Args:
        default (Optional): If supplied, this will be the default value of the
            Property for all instances of the class. Otherwise :obj:`None`

    Attributes:
        name (str): The name of the Property as defined in the class definition.
            This will match the attribute name for the
            :class:`~pydispatch.dispatch.Dispatcher` instance.

    """
    def __init__(self, default=None):
        self._name = ''
        self.default = default
        self.__storage = {}
        self.__weakrefs = InformativeWVDict(del_callback=self._on_weakref_fin)
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self, value):
        if self._name != '':
            return
        self._name = value
    def _add_instance(self, obj, default=None):
        if default is None:
            default = self.default
        self.__storage[id(obj)] = self.default
        self.__weakrefs[id(obj)] = obj
    def _del_instance(self, obj):
        del self.__storage[id(obj)]
    def _on_weakref_fin(self, obj_id):
        if obj_id in self.__storage:
            del self.__storage[obj_id]
    def __get__(self, obj, objcls=None):
        if obj is None:
            return self
        obj_id = id(obj)
        if obj_id not in self.__storage:
            self._add_instance(obj)
        return self.__storage[obj_id]
    def __set__(self, obj, value):
        obj_id = id(obj)
        if obj_id not in self.__storage:
            self._add_instance(obj)
        current = self.__storage[obj_id]
        if current == value:
            return
        self.__storage[obj_id] = value
        self._on_change(obj, current, value)
    def _on_change(self, obj, old, value, **kwargs):
        """Called internally to emit changes from the instance object

        The keyword arguments here will be passed to callbacks through the
        instance object's :meth:`~pydispatch.dispatch.Dispatcher.emit` method.

        Keyword Args:
            property: The :class:`Property` instance. This is useful if multiple
                properties are bound to the same callback. The attribute name
            keys (optional): If the :class:`Property` is a container type
                (:class:`ListProperty` or :class:`DictProperty`), the changes
                may be found here.
                This is not implemented for nested containers and will only be
                available for operations that do not alter the size of the
                container.

        """
        kwargs['property'] = self
        obj.emit(self.name, obj, value, old=old, **kwargs)
    def __repr__(self):
        return '<{}: {}>'.format(self.__class__, self)
    def __str__(self):
        return self.name

class ListProperty(Property):
    """Property with a :class:`list` type value

    Args:
        default (Optional): If supplied, this will be the default value of the
            Property for all instances of the class. Otherwise :obj:`None`
        copy_on_change (bool, optional): If :obj:`True`, the list will be copied
            when contents are modified. This can be useful for observing the
            original state of the list from within callbacks. The copied
            (original) state will be available from the keyword argument 'old'.
            The default is :obj:`False` (for performance and memory reasons).

    Changes to the contents of the list are able to be observed through
    :class:`ObservableList`.
    """
    def __init__(self, default=None, copy_on_change=False):
        if default is None:
            default = []
        self.copy_on_change = copy_on_change
        super(ListProperty, self).__init__(default)
    def _add_instance(self, obj):
        default = self.default[:]
        default = ObservableList(default, obj=obj, property=self)
        super(ListProperty, self)._add_instance(obj, default)
    def __set__(self, obj, value):
        value = ObservableList(value, obj=obj, property=self)
        super(ListProperty, self).__set__(obj, value)
    def __get__(self, obj, objcls=None):
        if obj is None:
            return self
        value = super(ListProperty, self).__get__(obj, objcls)
        if not isinstance(value, ObservableList):
            value = ObservableList(value, obj=obj, property=self)
            self._Property__storage[id(obj)] = value
        return value

class DictProperty(Property):
    """Property with a :class:`dict` type value

    Args:
        default (Optional): If supplied, this will be the default value of the
            Property for all instances of the class. Otherwise :obj:`None`
        copy_on_change (bool, optional): If :obj:`True`, the dict will be copied
            when contents are modified. This can be useful for observing the
            original state of the dict from within callbacks. The copied
            (original) state will be available from the keyword argument 'old'.
            The default is :obj:`False` (for performance and memory reasons).

    Changes to the contents of the dict are able to be observed through
    :class:`ObservableDict`.
    """
    def __init__(self, default=None, copy_on_change=False):
        if default is None:
            default = {}
        self.copy_on_change = copy_on_change
        super(DictProperty, self).__init__(default)
    def _add_instance(self, obj):
        default = self.default.copy()
        default = ObservableDict(default, obj=obj, property=self)
        super(DictProperty, self)._add_instance(obj, default)
    def __set__(self, obj, value):
        value = ObservableDict(value, obj=obj, property=self)
        super(DictProperty, self).__set__(obj, value)
    def __get__(self, obj, objcls=None):
        if obj is None:
            return self
        value = super(DictProperty, self).__get__(obj, objcls)
        if not isinstance(value, ObservableDict):
            value = ObservableDict(value, obj=obj, property=self)
            self._Property__storage[id(obj)] = value
        return value

class Observable(object):
    """Mixin used by :class:`ObservableList` and :class:`ObservableDict`
    to emit changes and build other observables

    When an item is added to an observable container (a subclass of Observable)
    it is type-checked and, if possible replaced by an observable version of it.

    In other words, if a dict is added to a :class:`ObservableDict`, it is
    copied and replaced by another :class:`ObservableDict`. This allows nested
    containers to be observed and their changes to be tracked.
    """
    def _build_observable(self, item):
        if isinstance(item, list):
            item = ObservableList(item, parent=self)
        elif isinstance(item, dict):
            item = ObservableDict(item, parent=self)
        return item
    def _get_copy_or_none(self):
        p = self.parent_observable
        if p is not None:
            return p._get_copy_or_none()
        if not self.copy_on_change:
            return None
        return self._deepcopy()
    def _deepcopy(self):
        o = self.copy()
        if isinstance(self, list):
            item_iter = enumerate(self)
        elif isinstance(self, dict):
            item_iter = self.items()
        for key, item in item_iter:
            if isinstance(item, Observable):
                o[key] = item._deepcopy()
        return o
    def _emit_change(self, **kwargs):
        if not self._init_complete:
            return
        old = kwargs.pop('old')
        p = self.parent_observable
        if p is not None:
            p._emit_change(old=old)
            return
        self.property._on_change(self.obj, old, self, **kwargs)

class ObservableList(list, Observable):
    """A :class:`list` subclass that tracks changes to its contents

    Note:
        This class is for internal use and not intended to be used directly
    """
    def __init__(self, initlist=None, **kwargs):
        self._init_complete = False
        super(ObservableList, self).__init__()
        self.property = kwargs.get('property')
        self.obj = kwargs.get('obj')
        self.parent_observable = kwargs.get('parent')
        if self.property is not None:
            self.copy_on_change = self.property.copy_on_change
        else:
            self.copy_on_change = False
        if initlist is not None:
            self.extend(initlist)
        self._init_complete = True
    def __setitem__(self, key, item):
        old = self._get_copy_or_none()
        item = self._build_observable(item)
        super(ObservableList, self).__setitem__(key, item)
        self._emit_change(keys=[key], old=old)
    def __delitem__(self, key):
        old = self._get_copy_or_none()
        super(ObservableList, self).__delitem__(key)
        self._emit_change(old=old)
    if PY2:
        def __setslice__(self, *args):
            old = self._get_copy_or_none()
            super(ObservableList, self).__setslice__(*args)
            self._emit_change(old=old)
        def __delslice__(self, *args):
            old = self._get_copy_or_none()
            super(ObservableList, self).__delslice__(*args)
            self._emit_change(old=old)
    if hasattr(list, 'clear'):
        def clear(self):
            old = self._get_copy_or_none()
            super(ObservableList, self).clear()
            self._emit_change(old=old)
    if not hasattr(list, 'copy'):
        def copy(self):
            return self[:]
    def __iadd__(self, other):
        other = self._build_observable(other)
        self.extend(other)
        return self
    def append(self, item):
        old = self._get_copy_or_none()
        item = self._build_observable(item)
        super(ObservableList, self).append(item)
        self._emit_change(old=old)
    def extend(self, other):
        old = self._get_copy_or_none()
        init = self._init_complete
        self._init_complete = False
        for item in other:
            self.append(item)
        if init:
            self._init_complete = True
        self._emit_change(old=old)
    def remove(self, *args):
        old = self._get_copy_or_none()
        super(ObservableList, self).remove(*args)
        self._emit_change(old=old)

class ObservableDict(dict, Observable):
    """A :class:`dict` subclass that tracks changes to its contents

    Note:
        This class is for internal use and not intended to be used directly
    """
    def __init__(self, initdict=None, **kwargs):
        self._init_complete = False
        super(ObservableDict, self).__init__()
        self.property = kwargs.get('property')
        self.obj = kwargs.get('obj')
        self.parent_observable = kwargs.get('parent')
        if self.property is not None:
            self.copy_on_change = self.property.copy_on_change
        else:
            self.copy_on_change = False
        if initdict is not None:
            self.update(initdict)
        self._init_complete = True
    def __setitem__(self, key, item):
        old = self._get_copy_or_none()
        item = self._build_observable(item)
        super(ObservableDict, self).__setitem__(key, item)
        self._emit_change(keys=[key], old=old)
    def __delitem__(self, key):
        old = self._get_copy_or_none()
        super(ObservableDict, self).__delitem__(key)
        self._emit_change(old=old)
    def update(self, other):
        old = self._get_copy_or_none()
        init = self._init_complete
        self._init_complete = False
        keys = set(other.keys()) - set(self.keys())
        for key, val in other.items():
            if key not in keys and self[key] == val:
                continue
            self[key] = val
            keys.add(key)
        if init:
            self._init_complete = True
        self._emit_change(keys=list(keys), old=old)
    def clear(self):
        old = self._get_copy_or_none()
        super(ObservableDict, self).clear()
        self._emit_change(old=old)
    def pop(self, *args):
        old = self._get_copy_or_none()
        super(ObservableDict, self).pop(*args)
        self._emit_change(old=old)
    def setdefault(self, *args):
        old = self._get_copy_or_none()
        super(ObservableDict, self).setdefault(*args)
        self._emit_change(old=old)
