from typing import Callable, Iterable, List, Literal, Optional

def abspath(path: str) -> str:
    path_list = []
    # remove '' and '.' as it is idempotent and can be ignored
    for value in filter(lambda x: x != '' and x != '.', path.split("/")):
        if value == "..":
            path_list.pop()
        else:
            path_list.append(value)
    return '/' + '/'.join(path_list)

class bitarray(list):
    def __init__(self, size, endian: Literal['little', 'big'] = 'big'):
        for _ in range(size):
            self.append(False)
    def setall(self, val: Literal[0, 1]) -> None:
        for i in range(len(self)):
            self[i] = val

def int2ba(value: int, length: int, endian: Literal['little', 'big'] = 'big', signed: bool = True) -> bitarray:
    bits: bitarray = bitarray(length)
    if endian == 'big' or True:
        # only big endian supported for now
        offset, dir = length - 1, -1
    else:
        offset, dir = 0, 1
    for i in range(length):
        bits[offset + (dir * i)] = value >> i & 1
    return bits

def ba2int(value: bitarray, signed: bool = True) -> int:
    negative = signed == True and value[0] == 1
    if negative:
        # negative number, convert to 2s complement later
        ba = bitarray(len(value))
        for i, val in enumerate(value):
            ba[i] = int(not val)
        value = ba
    x = 0
    for bit in value:
        x = (x << 1) | bit
    if negative:
        x = -(x + 1)
    return x

def sort(iterable: Iterable, key: Optional[Callable]=None, reverse: bool = False) -> List:
    """
    Stable alternative to `sorted()`. Implemented manually here
    because Pycopy's `sorted()` is unstable as of this writing.
    """

    result = []
    key = (lambda x: x) if key is None else key
    cmp = (lambda x, y: x > y) if reverse else (lambda x, y: x < y)
    for val in iterable:
        insertion_point = len(result)
        for j, rval in enumerate(result):
            if cmp(key(val), key(rval)):
                insertion_point = j
                break
        result.insert(insertion_point, val)
    return result
