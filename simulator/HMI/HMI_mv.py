# from io_plc import IO_MV
from typing import Dict, Type
from controlblock import MV_FBD
from io_plc import IO_MV
from modbus.types.remote import RemoteDeviceType
from modbus.compat.builtins import asyncio
from .base_hmi import BaseHMI

class HMI_mv(BaseHMI):
    def init_hmi(self, *args, **kwargs):
        self.Auto: bool = True
        self.Reset: bool = True
        self.FTO: bool = False
        self.FTC: bool = False
        self.Avl: bool = True
        self.Open: bool = True
        self.Close: bool = False
        self.Cmd: int = 0
        self.Status: int = 0
        
    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.MV, self.IO = RemoteDeviceType("FBD"), RemoteDeviceType("IO")

        kwargs.update({self.MV: MV_FBD, self.IO: IO_MV})
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        (DI_ZSC, DI_ZSO), *_ = await asyncio.gather(
            self.ask_device(self.IO, "DI_ZSC", "DI_ZSO"),
            self.tell_device(self.MV, 
                ("Auto", self.Auto), ("Cmd", self.Cmd), ("Reset", self.Reset)
            )
        )

        if DI_ZSC:
            self.Status = 1
        elif DI_ZSO:
            self.Status = 2
        else:
            self.Status = 70

        self.Avl, self.FTO, self.FTC = (
            bool(value) for value in await self.ask_device(
                self.MV, "Avl", "FTO", "FTC"
            )
        )
