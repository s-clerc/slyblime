#import pkg_resources

try:
    __version__ = pkg_resources.require('python-dispatch')[0].version
except: # pragma: no cover
    __version__ = 'unknown'

from .dispatch import Dispatcher
from .properties import Property
