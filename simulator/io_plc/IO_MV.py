from typing import Tuple, Type
from modbus.base import BaseModbusDevice
from modbus.tag import Tag

class IO_MV(BaseModbusDevice):
    def __init__(self, connected: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connected = connected
        self.DI_ZSO: bool = False
        self.DI_ZSC: bool = True
        self.DO_Open: bool = False
        self.DO_Close: bool = False

    @classmethod  
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("DI_ZSO", bool),    Tag("DI_ZSC", bool),
            Tag("DO_Open", bool),   Tag("DO_Close", bool),
            *tags
        )

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        if self.connected:
            self.DI_ZSO = self.DO_Open
            self.DI_ZSC = self.DO_Close
