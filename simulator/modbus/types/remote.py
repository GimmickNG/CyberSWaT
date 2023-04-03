from typing import Generic, NewType, Tuple, TypedDict, Dict, List
from ..compat.modbus import ModbusClient
from ..tag import T, Tag
from . import IPString

RemoteDeviceType = NewType("RemoteDeviceType", str)
"""
A type that indicates the string is to be used in the context of a
remote device query. Used to prevent confusion with tag names in the
ordering of e.g. a `tell_device()` query.
"""

class ContiguousTagSet(Generic[T]):
    """
    A tagset whose tags are laid out contiguously, with spacer tags
    added to mask out any spaces that exist in the tags specified.
    """

    def __init__(self, coils: Tuple[T, ...], holding_registers: Tuple[T, ...]) -> None:
        self.coils: Tuple[T, ...] = coils
        self.holding_registers: Tuple[T, ...] = holding_registers

class RemoteDeviceMapping(TypedDict):
    """
    A RemoteDeviceMapping is used when referring to a dict
    containing mapping keys of `ip`, `port`, `client` and `tags`, e.g. 
    ```
    {
        "ip": "192.168.0.1",
        "port: 502,
        "client": ModbusTcpClient(),
        "tags": {
            "abc": Tag("abc", bool, 0),
            "xyz": Tag("xyz", float, 1)
        }
    }
    ```
    """

    ip: IPString
    port: int
    client: ModbusClient
    tags: Dict[str, Tag]
