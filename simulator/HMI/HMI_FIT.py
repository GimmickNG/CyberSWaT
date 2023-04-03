# from io_plc import IO_AIN_FIT
from typing import Dict, Type, cast
from controlblock import FIT_FBD
from modbus.base import BaseModbusClient
from modbus.types.remote import RemoteDeviceType
from .base_hmi import BaseHMI
class HMI_FIT(BaseHMI):
    def init_hmi(self, *args, **kwargs):
        self.SAHH: float = 4.0
        self.SAH: float  = 3.0
        self.SAL: float  = 1.0
        self.SALL: float = 0.5
        self.Rst_Totaliser: bool = False
        self.Hty: bool  = False
        self.Wifi_Enb: bool = False
        self.AHH: bool  = False
        self.AH: bool   = False
        self.AL: bool   = False
        self.ALL: bool  = False
        self.Sim: bool  = False
        self.Sim_Pv: float = 0.0
        self.Totaliser: float = 0.0
        self.Pv: float = 0.0

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.FIT = RemoteDeviceType("FBD")
        
        kwargs.update({self.FIT: FIT_FBD})
        return super().get_device_classes(**kwargs)
    
    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        await self.tell_device(self.FIT,
            ("SAHH", self.SAHH), ("SAH", self.SAH),
            ("SAL", self.SAL),   ("SALL", self.SALL),
            ("Sim", self.Sim),   ("Rst_Totaliser", self.Rst_Totaliser)
        )
        
        if not self.Sim:
            self.Sim_Pv = float(await self.ask_device(self.FIT, "Pv"))
        self.Pv = self.Sim_Pv
        
        Totaliser_Enb = await self.ask_device(self.FIT, "Totaliser_Enb")
        if self.Rst_Totaliser:
            self.Totaliser = 0
        elif Totaliser_Enb and sec_pulse:
            self.Totaliser += abs(self.Pv)/3600
        
        self.Hty, self.Wifi_Enb, self.AHH, self.AH, self.AL, self.ALL = (
            bool(value) for value in await self.ask_device(
                self.FIT, "Hty", "WRIO_Enb", "AHH", "AH", "AL", "ALL"
            )
        )   
        # replace WRIO_Enb with Wifi_Enb if things go wrong
        # self.ALL = self.AHH in original code - replace both parts if it doesn't work correctly