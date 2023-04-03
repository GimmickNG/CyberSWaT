from typing import Dict, Type, cast
from modbus.base import BaseModbusClient
from modbus.compat.builtins import bitarray
from controlblock.SWITCH_FBD import SWITCH_FBD
from modbus.types.remote import RemoteDeviceType
from .base_hmi import BaseHMI
from logicblock import create_bitarray

class HMI_LS(BaseHMI):
    def init_hmi(self, *args, **kwargs):
        # appears to be unused
        self.Delay: bitarray = create_bitarray(32, 0)
        self.Alarm: bool = False
        self.Status: int = 0

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.SWH = RemoteDeviceType("FBD")
        
        kwargs.update({self.SWH: SWITCH_FBD})
        return super().get_device_classes(**kwargs)
    
    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        # appears to be unused
        self.Status = int(await self.ask_device(self.SWH, "Status"))