from umodbus import const as ModbusConst
from typing import List, Literal, Optional, Dict, Tuple, Union
from ..types import ModbusRegisterData

class ModbusDeviceIdentification:
    def __init__(self, info: Optional[Dict[int, str]] = None):
        if info is None:
            info = {}
        self.VendorName: str = info.get(0x00, '')
        self.ProductCode: str = info.get(0x01, '')
        self.MajorMinorRevision: str = info.get(0x02, '')
        self.VendorUrl: str = info.get(0x03, '')
        self.ProductName: str = info.get(0x04, '')
        self.ModelName: str = info.get(0x05, '')
        self.UserApplicationName: str = info.get(0x06, '')
        self.private_objects: Dict[int, str] = {
            int(key): value for key, value in info.items() if 0x80 <= int(key) <= 0xFF
        }

class ModbusSparseDataBlock(dict):
    """
    Compatibility layer with `pymodbus.datastore.store.ModbusSparseDataBlock`.
    However, as this is intended for use with umodbus, it functions slightly
    differently, even though the original semantics are retained. The biggest
    difference is that this class extends `dict`, whereas the pymodbus version
    does not.
    """

    def __init__(self, values: Optional[Union[Dict[int, ModbusRegisterData], List[ModbusRegisterData]]] = None):
        """
        `values` can be a dict of index: registers or a list of registers, e.g.

        `{0: [0, 255], 1: [120, 200, 240, 20]}` or `[0, 255, 120, 200, 240, 20]`

        In both cases, each element in the list is interpreted as a byte and groups 
        of two bytes (1 word/register) are located in each slot:

        `{0: [0, 255], 1: [120, 200], 2: [240, 20]}`

        (is the intent, but right now it is stored as 1 index = 1 byte, e.g.)

        `{0: 0, 1: 255, 2: 120, 3: 200, 4: 240, 5:  20}`
        """


        if values:
            iterator = values.items() if isinstance(values, dict) else enumerate(values)
            for key, value in iterator:
                if not isinstance(value, list):
                    value = [value]
                # TODO chunk by register, i.e. take 2 steps/bytes
                for idx, item in enumerate(value):
                    self[key+idx] = {'val': item}
        self.default_values = {
            key: value.copy() for key, value in self.items()
        }
    
    def reset(self) -> None:
        """Resets data block to its initially supplied values"""

        self.clear()
        for key, values in self.default_values:
            self[key] = values
        
    def setValues(self, address: int, value: ModbusRegisterData) -> None:
        """
        Compatibility with pymodbus. Currently only supports
        setting a single register at an address.
        """

        for i, val in enumerate(value):
            self[address + i] = {'val': val}

    def getValues(self, address: int, count: int = 1) -> List[ModbusRegisterData]:
        try:
            return [self[i]['val'] for i in range(address, address + count)]
        except KeyError:
            print("KeyError (1/2) when getting values. Self dict is: ", self)
            print("KeyError (2/2) when getting values from range {0} -> {1}. values is ".format(address, address+count), values)
            raise
        return values

    @classmethod
    def create(cls, values = None):
        return cls(values)

class ModbusSlaveContext(dict):
    SupportedFunctionCodes = Literal[1, 2, 3, 4, 5, 6, 15, 16, 22, 23]

    _fc_to_reg = {2: ModbusConst.COILS, 4: ModbusConst.ISTS}
    _fc_to_reg.update({i: ModbusConst.HREGS for i in (3, 6, 16, 22, 23)})
    _fc_to_reg.update({i: ModbusConst.COILS for i in (1, 5, 15)})

    def __init__(self, **kwargs: ModbusSparseDataBlock):
        self[ModbusConst.ISTS] = kwargs.get('di', ModbusSparseDataBlock.create())
        self[ModbusConst.COILS] = kwargs.get('co', ModbusSparseDataBlock.create())
        self[ModbusConst.IREGS] = kwargs.get('ir', ModbusSparseDataBlock.create())
        self[ModbusConst.HREGS] = kwargs.get('hr', ModbusSparseDataBlock.create())
        self.zero_mode = kwargs.get("zero_mode", False)

    def _decode(self, fx: SupportedFunctionCodes):
        """
        From `pymodbus.interfaces.IModbusSlaveContext` as compatibility
        with pymodbus. Currently only supports Modbus function codes
        1-6, 15, 16, 22 and 23.
        """

        return ModbusSlaveContext._fc_to_reg[fx]

    def getValues(self, fx: SupportedFunctionCodes, address: int, count: int = 1) -> List[ModbusRegisterData]:
        if not self.zero_mode:
            address += 1
        block: ModbusSparseDataBlock = self[self._decode(fx)]
        return block.getValues(address, count)

    def setValues(self, fx: SupportedFunctionCodes, address: int, values: ModbusRegisterData):
        """
        Compatibility with pymodbus. Currently only supports setting
        one register value in a given address at a time, and function
        codes in the range specified by ModbusSlaveContext.SupportedFunctionCodes
        """

        if not self.zero_mode:
            address += 1
        block: ModbusSparseDataBlock = self[self._decode(fx)]
        block.setValues(address, values)
        
class ModbusServerContext:
    """
    Compatibility class for pymodbus.datastore.ModbusServerContext.
    Attempts to retain as much of the original semantics re: unit id
    in this class with umodbus.

    Currently only supports sparse data blocks, as this is the format
    implicitly used by umodbus (i.e. accessing undefined registers is
    not supported)

    WARNING: The umodbus library only supports a single common data
    block for all the unit IDs! What this means is that only the value
    at `slaves[0]` will be used, and all other values will be ignored.
    The keys in `slaves` (if a dict is passed) will be used to construct
    the address list for the modbus server, but the datablock used will
    be common to them all! This can result in data being overwritten in
    shared registers, leading to unexpected behaviour if this is not
    properly accounted for. Do NOT set `single` to False unless you
    WANT to share data amongst all the devices across unit IDs!
    """

    def __init__(self, 
        slaves: Union[ModbusSlaveContext, Dict[int, ModbusSlaveContext]],
        single: Literal[True] = True
    ):
        """
        Creates a new server context. Unlike pymodbus, this requires `slaves` to be
        specified; uses the data block at unit ID 0 for storing data. While `single`
        is allowed as a parameter, this is only for compatibility with pymodbus; in
        practice, this is always True, and setting False will flag an error in the
        type checker. This is because setting it to False with the expectation that
        the devices will have independent data blocks can lead to unexpected errors,
        so this behaviour is explicitly discouraged. However, it is not regarded as
        an error, for testing purposes.

        Also, unlike pymodbus, data blocks cannot be added or removed at runtime.
        """

        self.single: bool = single
        if isinstance(slaves, ModbusSlaveContext):
            self._unit: ModbusSlaveContext = slaves
            self.unit_ids: Tuple[int, ...] = (0,)
        else:
            self._unit: ModbusSlaveContext = slaves[0]
            self.unit_ids: Tuple[int, ...] = tuple(slaves.keys())
        
    def __getitem__(self, slave) -> ModbusSlaveContext:
        """
        Compatibility with pymodbus. Since `single` is always
        True, this always returns the slave context at position
        0 when this class was instantiated.
        """
        
        return self._unit

    def slaves(self) -> Tuple[int, ...]:
        """
        Returns a list of all the unit IDs for this device.
        """
        
        return self.unit_ids

class Endian:
    """
    Endian constants for Modbus payload builder and decoder.
    Uses the same definitions as pymodbus.constants.Endian 
    for compatibility purposes, which itself uses struct 
    constants.
    """

    Auto: str = '@'
    Big: str = '>'
    Little: str = '<'