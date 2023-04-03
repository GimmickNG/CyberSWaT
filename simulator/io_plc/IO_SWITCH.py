from typing import List, Tuple, Type
from modbus.base import BaseModbusDevice
from modbus.tag import Tag

class IO_SWITCH(BaseModbusDevice): # PMP_FBD and UV_FBD both use this I/O
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.DI_LS: bool = False

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(Tag("DI_LS", bool), *tags)
