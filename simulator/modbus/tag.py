from math import ceil
from typing import List, Optional, Tuple, Type, TypeVar, Generic, Union
from .types import Registers, ReadFunctionCode, WriteFunctionCode
from .compat.builtins import struct, bitarray

# uses pymodbus based structures for compatibility with it    
class PayloadBuilder:
    def __init__(self, payload: Optional[bytes] = None, *args, **kwargs):
        self.payload: bytearray = bytearray(payload) if payload is not None else bytearray()
    def write_int(self, value:int) -> None:
        self.payload.extend(struct.pack(">i", value))
    def write_float(self, value:float) -> None:
        self.payload.extend(struct.pack(">f", value))
    def write_bool(self, value: bool) -> None:
        self.payload.extend(struct.pack(">B", 0x0001 if value else 0x0000))
    def to_registers(self) -> Tuple[int, ...]:
        fmt = "H" * (len(self.payload) >> 1)
        return struct.unpack(">" + fmt, self.payload)
    def to_coils(self) -> Tuple[bool, ...]:
        fmt = "B" * len(self.payload)
        return struct.unpack(">" + fmt, self.payload)

class PayloadDecoder:
    def __init__(self, payload: bytes, *args, **kwargs):
        self.pointer: int = 0
        self.payload: memoryview = memoryview(payload)
    def get_bytes(self, nbytes):
        byte_data = self.payload[self.pointer: self.pointer + nbytes]
        if len(byte_data) < nbytes:
            raise ValueError("Buffer too small: pointer is {0}, but payload is {1}".format(self.pointer, self.payload))
        return byte_data
    def next_int(self) -> int:
        val = struct.unpack(">i", self.get_bytes(4))[0]
        self.pointer += 4
        return int(val)
    def next_float(self) -> float:
        val = struct.unpack(">f", self.get_bytes(4))[0]
        self.pointer += 4
        return float(val)
    def next_bool(self) -> bool:
        val = struct.unpack(">B", self.get_bytes(1))[0]
        self.pointer += 1
        return bool(val) # 0x0001 => True, 0x0000 => False
    def skip_bytes(self, num_bytes:int) -> None:
        self.pointer += num_bytes
    
    @classmethod
    def from_registers(cls, registers: List[int], flatten:bool=False):
        if flatten:
            registers = Tag.flatten(registers)
        fmt = "H" * len(registers)
        return cls(struct.pack(">" + fmt, *registers))

    @classmethod
    def from_coils(cls, coils: List[bool], flatten:bool=False):
        if flatten:
            coils = Tag.flatten(coils)
        fmt = "B" * len(coils)
        try:
            return cls(struct.pack(">" + fmt, *coils))
        except:
            print("Error: received coils of type", type(coils), 'and value', coils)
            raise


T = TypeVar('T')
class Tag(Generic[T]):
    """Stores tag information."""

    COILS = 1
    HOLDING_REGISTERS = 2
    MAX_CONTIGUOUS_BYTES: int = 32
    def __init__(self, name: str, data_type: Type[T], desired_offset: int = 0) -> None:
        """
        Creates a Tag that identifies a data type with a number of registers. 
        The desired offset is not guaranteed to be granted, if using a tag packer;
        that is, if overlapping sections exist, then they will be moved up.
        """

        self.get_function_code, self.set_function_code = self.get_fc(data_type)
        self.data_size = Tag.get_num_registers(Tag.get_size(data_type))
        self.offset = desired_offset
        self.data_type: Type[T] = data_type
        self.name = name
        if self.data_size == 1:
            self.storage_location = Tag.COILS
        else:
            self.storage_location = Tag.HOLDING_REGISTERS

    def __repr__(self) -> str:
        return "{0}: {1} @ {2} (sz={3}, loc={4})".format(
            self.name, self.data_type, self.resolve_registers(),
            self.data_size, self.storage_location
        )

    def resolve_registers(self) -> Registers:
        """Gets the `[start, <length>, end)` registers for the given tag."""

        return Registers(self.offset, self.data_size, self.offset + self.data_size)

    def encode_with(self, value:T, builder: PayloadBuilder) -> None:
        if self.data_type is int:
            builder.write_int(value)
        elif self.data_type is float:
            builder.write_float(value)
        elif self.data_type is bool:
            builder.write_bool(value)
        else:
            raise NotImplementedError("`Tag.encode_with()` not implemented for type", self.data_type)

    @staticmethod
    def flatten(registers: Union[List[T], List[List[T]]]) -> List[T]:
        items: List[T] = []
        for data in registers:
            if isinstance(data, (list, tuple)):
                items.extend(data)
            else:
                items.append(data)
        return items
        
    def decode_with(self, decoder:PayloadDecoder) -> T:
        if self.data_type is int:
            data = decoder.next_int()
        elif self.data_type is float:
            data = decoder.next_float()
        elif self.data_type is bool:
            data = decoder.next_bool()
        else:
            raise NotImplementedError("`Tag.decode_with()` does not yet support types apart from int, float and bool.")
        return self.data_type(data)

    def get_fc(self, data_type: Type[T]) -> Tuple[ReadFunctionCode, WriteFunctionCode]:
        if data_type is bool:
            #0x01 = Read Coil (bool) status; 0x05 = Force Single Coil (bool)
            return 0x01, 0x0F
        elif data_type is int or data_type is float:
            # 0x03 = Read Holding Registers; 0x10 = Force/Preset Multiple Registers
            # used for int, float and other complex types as they require multiple
            # registers to fully decode
            return 0x03, 0x10
        # more complex data types not used in this codebase so something must
        # have gone wrong; replace this if using more tags
        raise ValueError("Attempted to use invalid data type for tag: ", data_type)

    @staticmethod
    def get_num_registers(num_bytes: int) -> int:
        """
        Returns the number of registers needed for storing the piece of data of num_bytes size.
        Since Modbus uses 2-byte words for each register, this results in the number of registers
        being at least 1/2 the number of bytes required.
        """

        return ceil(num_bytes / 2)

    @staticmethod
    def get_size(data_type: Type) -> int:
        """
        Returns size in number of bytes required for the data type when storing it in a register.
        That is, using sys.getsizeof() won't work here as it includes extra data which is not used here.
        """
        
        if data_type is bool:
            return 1
        if data_type is int or data_type is bitarray:
            return 4
        if data_type is float:
            return 4
        return Tag.MAX_CONTIGUOUS_BYTES

class SkipTag(Tag):
    def __init__(self, desired_offset:int, end_register:int):
        super().__init__(name="", data_type=type(None), desired_offset=desired_offset)
        self.data_size = end_register - desired_offset
        self.end_register = end_register

    def get_fc(self, data_type: Optional[Type[None]]) -> Tuple[int, int]:
        return (0x00, 0x00)
    
    def encode_with(self, value: None, builder: PayloadBuilder) -> None:
        raise ValueError("SkipTag is not meant to be encoded")

    def decode_with(self, builder: PayloadDecoder) -> None:
        builder.skip_bytes(self.data_size)