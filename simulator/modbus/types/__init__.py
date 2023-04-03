from ..compat.builtins import namedtuple
from typing import List, Literal, Tuple, Union, NewType

IPString = NewType('IPString', str)

ModbusRegisterData = Union[List[int], List[bool], Tuple[int, ...], Tuple[bool, ...]]
"""
A Modbus register. This is a list of up to 16 values, with
each value corresponding to a bit in the register.
"""

RegisterValue = Union[float, int, bool]
"""A RegisterValue is stored in Registers"""

ReadFunctionCode = Literal[0x01, 0x03]
"""
Supported Modbus read coil/register function codes.
* 0x01 = Read Coil (bool) status
* 0x03 = Read Holding Registers
"""

WriteFunctionCode = Literal[0x05, 0x0F, 0x10]
"""
Supported Modbus write coil/register function codes.
* 0x05 = Force Single Coil (bool)
* 0x0F = Force Multiple Coils (bool)
* 0x10 = Force/Preset Multiple Registers.
    * used for int, float and other complex types as they require
      multiple registers to fully encode/decode.
"""

Registers = namedtuple("Registers", ["start", "length", "end"])
"""Used to retrieve RegisterValues stored at these indice(s)"""