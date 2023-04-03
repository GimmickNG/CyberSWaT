# from io_plc import IO_AIN_FIT
from time import time
from typing import Dict, Type, cast
from logicblock import ALM
from controlblock import AIN_FBD
from modbus.base import BaseModbusClient
from modbus.types.remote import RemoteDeviceType
from .base_hmi import BaseHMI
from pymodbus import exceptions

class HMI_LIT(BaseHMI):
    def init_hmi(self,
        SAHH: float=1000, SAH: float=800, SAL: float=500,
        SALL: float=250, AH:bool = False, *args, **kwargs
    ):
        self.SAHH: float = SAHH
        self.SAH: float  = SAH
        self.SAL: float  = SAL
        self.SALL: float = SALL
        self.Sim: bool  = False
        self.Hty: bool  = True
        self.Wifi_Enb: bool = False
        self.AHH: bool  = False
        self.AH: bool   = AH
        self.AL: bool   = False
        self.ALL: bool  = False
        self.Sim_Pv: float = 0
        self.Pv: float   = 0        

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.LIT = RemoteDeviceType("FBD")
        
        kwargs.update({self.LIT: AIN_FBD})
        return super().get_device_classes(**kwargs)

    def set_alarm(self):
        self.AHH, self.AH, self.AL, self.ALL = ALM(self.Pv, self.SAHH, self.SAH, self.SAL, self.SALL)

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        await self.tell_device(self.LIT, 
            ("Sim", self.Sim),      ("SAHH", self.SAHH),
            ("SAH", self.SAH),      ("SAL", self.SAL),
            ("SALL", self.SALL)
        )
        #Calculation for PV*)
        if not self.Sim:
            self.Sim_Pv	= await self.ask_device(self.LIT, "Pv")
        self.Pv = self.Sim_Pv
        
        self.Hty, self.Wifi_Enb, self.AHH, self.AH, self.AL, self.ALL = (
            bool(value) for value in await self.ask_device(
                self.LIT, "Hty", "WRIO_Enb", "AHH", "AH", "AL", "ALL"
            )
        )
        # replace WRIO_Enb with Wifi_Enb if things go wrong

class HMI_ait(HMI_LIT):
	def __init__(self, SAHH: float, SAH: float, SAL: float, SALL: float, *args, **kwargs):
		super().__init__(
            SAHH=SAHH, SAH=SAH, SAL=SAL, SALL=SALL, *args, **kwargs
        )

class HMI_PIT(HMI_LIT):
    def __init__(self, *args, **kwargs):
        super().__init__(
            SAHH=100, SAH=40, SAL=15,SALL=10, AH=True, *args, **kwargs
        )