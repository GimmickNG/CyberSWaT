from typing import Tuple, Type
from modbus.base import BaseModbusDevice
from modbus.tag import Tag
class IO_PMP_UV(BaseModbusDevice): # PMP_FBD and UV_FBD both use this I/O
    def __init__(self, connected: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connected = connected
        self.DI_Auto: bool = True
        self.DI_Run: bool  = False
        self.DI_Fault: bool = False
        self.DO_Start: bool = False
        self.Start: bool = False
    
    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("DI_Auto", bool),   Tag("DI_Run", bool),
            Tag("DI_Fault", bool),  Tag("DO_Start", bool),
            Tag("Start", bool),     *tags
        )

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        if self.connected:
            self.DI_Run = self.DO_Start