from typing import Dict, Type, cast
from modbus.compat.builtins import asyncio
from controlblock import PMP_FBD
from io_plc import IO_PMP_UV
from modbus.types.remote import RemoteDeviceType
from .base_hmi import BaseHMI
from logicblock import create_bitarray, bit_2_signed_integer, signed_integer_2_bit

class HMI_UV(BaseHMI):
    def init_hmi(self, Auto:bool = False, Avl: bool = False, *args, **kwargs):
        self.Auto: bool = Auto
        self.Avl: bool = Avl
        self.Reset: bool = True
        self.FTS: bool   = False
        self.FTR: bool   = False
        self.RunHr: float = 0
        self.Reset_RunHr: bool = False
        self.Permissive = create_bitarray(32, 1)
        self.MSG_Permissive = create_bitarray(6, 0)
        self.SD    = create_bitarray(32, 0)
        self.MSG_Shutdown = create_bitarray(6, 0)
        self.Shutdown = create_bitarray(32, 0)
        self.Fault: bool = False
        self.Status: int = 1
        self.Total_RunHr: float = 0.0
        self.Cmd:int = 0

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PMP, self.IO = RemoteDeviceType("FBD"), RemoteDeviceType("IO")
        
        kwargs.update({self.PMP: PMP_FBD, self.IO: IO_PMP_UV})
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        await self.tell_device(self.PMP,
            ("FTS", self.FTS),                  ("FTR", self.FTR),
            ("Auto", self.Auto),                ("Reset", self.Reset),
            ("Reset_RunHr", self.Reset_RunHr),  ("Permissive", bit_2_signed_integer(self.Permissive)),
            ("Cmd", self.Cmd),                  ("SD", bit_2_signed_integer(self.SD))
        )

        io_vars, pump_vars = await asyncio.gather(
            self.ask_device(self.IO, "DI_Auto", "DI_Run"),
            self.ask_device(self.PMP, 
                "Cmd", "Avl", "Fault", "FTS", "FTR", "RunHr", "Total_RunHr", "Shutdown"
            )
        )
        self.Remote, Run = io_vars
        self.Status = 2 if Run else 1

        Cmd, Avl, Fault, FTS, FTR, RunHr, Total_RunHr, Shutdown = pump_vars
        
        self.Cmd = int(Cmd)
        self.Avl, self.Fault, self.FTS, self.FTR = (
            bool(value) for value in (Avl, Fault, FTS, FTR)
        )
        self.RunHr, self.Total_RunHr = float(RunHr), float(Total_RunHr)
        self.Shutdown = signed_integer_2_bit(int(Shutdown))