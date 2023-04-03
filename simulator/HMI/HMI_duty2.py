from typing import Dict, Type, Union, cast
from modbus.base import BaseModbusClient
from controlblock.Duty2_FBD import Duty2_FBD
from modbus.types.remote import RemoteDeviceType
from .base_hmi import BaseHMI
from .HMI_pump import HMI_pump
from .HMI_VSD import HMI_VSD
class HMI_duty2(BaseHMI):
    def init_hmi(self, PMP1: Union[HMI_pump, HMI_VSD], PMP2: Union[HMI_pump, HMI_VSD], *args, **kwargs):
        self.Selection: bool = True
        self.Pump_Running: bool = False
        self.Selected_Pmp_Not_Avl: bool = False
                
        self.PMP1, self.PMP2 = PMP1, PMP2

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.Duty2 = RemoteDeviceType("FBD")
        
        kwargs.update({self.Duty2: Duty2_FBD})
        return super().get_device_classes(**kwargs)
    
    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        await self.tell_device(self.Duty2, 
            ("PMP1_Avl", self.PMP1.Avl), ("PMP1_Status", self.PMP1.Status),
            ("PMP2_Avl", self.PMP2.Avl), ("PMP2_Status", self.PMP2.Status),
            ("Selection", self.Selection)
        )
        self.Pump_Running = (self.PMP1.Status == 2 or self.PMP2.Status == 2)
        self.Both_Pmp_Not_Avl = not (self.PMP1.Avl or self.PMP2.Avl)
        self.Selected_Pmp_Not_Avl = bool(await self.ask_device(self.Duty2, "Selected_Pmp_Not_Avl"))
