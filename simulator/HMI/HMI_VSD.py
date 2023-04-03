from typing import Dict, Type, cast
from modbus.compat.builtins import asyncio
from controlblock import VSD_FBD
from io_plc.VSD import VSD, VSD_In
from modbus.types.remote import RemoteDeviceType
from .base_hmi import BaseHMI
from logicblock import create_bitarray, bit_2_signed_integer, signed_integer_2_bit

class HMI_VSD(BaseHMI):
    def init_hmi(self, *args, **kwargs):
        self.Auto: bool = True
        self.Status = 2
        self.Reset: bool = False
        self.Reset_RunHr: bool = True
        self.Speed_Command = 7710
        self.Permissive = create_bitarray(32, 1)
        self.MSG_Permissive = create_bitarray(32, 1)
        self.MSG_Shutdown = create_bitarray(32, 1)
        self.SD = create_bitarray(32, 0)
        self.Avl: bool = True
        self.Fault: bool = False
        self.FTS: bool = False
        self.FTR: bool = False
        self.RunHr: float = 0.0
        self.Total_RunHr: float = 0.0
        self.Speed: float = 0
        self.Drive_Ready: bool = False
        self.Shutdown = create_bitarray(32, 0)
        self.Cmd: int = 1

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.VSD_In, self.VSD, self.IO = (RemoteDeviceType(dev) for dev in ("VSD", "FBD", "IO"))
        
        kwargs.update({self.VSD_In: VSD_In, self.VSD: VSD_FBD, self.IO: VSD})
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        await self.tell_device(self.VSD,
            ("Auto", self.Auto),
            ("Reset", self.Reset),
            ("Reset_RunHr", self.Reset_RunHr),
            ("Permissive", bit_2_signed_integer(self.Permissive)),
            ("SD", bit_2_signed_integer(self.SD)),
            ("Speed_Command", self.Speed_Command),
            ("Cmd", self.Cmd)
        )
        
        (Trip, Active), self.Remote, vsd_vars = await asyncio.gather(
            self.ask_device(self.VSD_In, "Faulted", "Active"),
            self.ask_device(self.IO, "DI_Auto"),
            self.ask_device(self.VSD,
                "Cmd", "Avl","Fault","FTS","FTR","RunHr",
                "Speed","Drive_Ready","Total_RunHr","Shutdown"
            )
        )

        self.Status = 2 if Active else 1
        
        self.Fault = bool(Trip) or self.SD.any()
        if self.Reset:
            self.Shutdown = create_bitarray(32, 0)    # In original PLC code, here it's HMI.SHUTDOWN,  we doubt it's global HMI's SHUTDOWN variable, or it's not case sensitive and equal to Shutdown like we treat it here.
        
        Cmd, Avl, Fault, FTS, FTR, RunHr, Speed, Drive_Ready, Total_RunHr, Shutdown = vsd_vars
        
        self.Cmd = int(Cmd)
        self.Avl, self.Fault, self.FTS, self.FTR, self.Drive_Ready = (
            bool(value) for value in (Avl, Fault, FTS, FTR, Drive_Ready)
        )
        self.RunHr, self.Speed, self.Total_RunHr = \
            float(RunHr), float(Speed), float(Total_RunHr)
        self.Shutdown = signed_integer_2_bit(int(Shutdown))