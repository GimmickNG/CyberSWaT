from . import IS_PYCOPY

if IS_PYCOPY:
    from .base_structs import abspath, bitarray, int2ba, ba2int, sort
    from utime import time, time as perf_counter
    from ucollections import namedtuple
    from uasyncio import sleep, Event
    import uasyncio as asyncio
    import ustruct as struct
else:
    sort = sorted
    import struct
    import asyncio
    from os.path import abspath
    from time import time, perf_counter
    from bitarray import bitarray
    from asyncio import sleep, Event
    from collections import namedtuple
    from bitarray.util import int2ba, ba2int

# abspath included in compat module since 
# Pycopy does not produce normalized paths
# as of this writing
__all__ = [
    "Event", "sleep", "abspath", "bitarray", "int2ba",
    "ba2int", "namedtuple", "struct", "sort", "asyncio",
    "perf_counter"
]