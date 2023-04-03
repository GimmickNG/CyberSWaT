from typing import Dict, Tuple, Type, cast
from logicblock import TONR
from io_plc import IO_SWITCH
from modbus.base import BaseModbusDevice
from modbus.tag import Tag
from modbus.types.remote import RemoteDeviceType
from .base_fbd import FBD

class SWITCH_FBD(FBD):
    def init_fbd(self, Delay: int, *args, **kwargs) -> None: 
        self.TON_Delay = TONR(Delay, self.device_frequency)

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.IO = RemoteDeviceType("IO")
        
        kwargs.update({self.IO: IO_SWITCH})
        return super().get_device_classes(**kwargs)
    
    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(Tag("Status", bool), *tags)

    async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        TimerEnb: bool = bool(await self.ask_device(self.IO, "DI_LS"))
        
        self.TON_Delay.tick(TimerEnb) #Alarm
        self.Status = self.TON_Delay.DN
