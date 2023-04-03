from typing import List, Tuple, Type
from modbus.base import BaseModbusDevice
from modbus.tag import Tag

class IO_AIN_FIT(BaseModbusDevice): # AIN_FBD and FIT_FBD both use this I/O
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.AI_Value:float   = 0
        self.W_AI_Value:float = 0
        self.AI_Hty: bool     = True
        self.W_AI_Hty: bool   = True

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("AI_Hty", bool),    Tag("W_AI_Hty", bool),
            Tag("AI_Value", float), Tag("W_AI_Value", float),
            *tags
        )
