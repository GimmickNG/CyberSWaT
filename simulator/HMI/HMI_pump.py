from typing import Dict, Type, cast
from modbus.compat.builtins import bitarray
from controlblock import PMP_FBD
from io_plc import IO_PMP_UV
from modbus.types.remote import RemoteDeviceType
from modbus.compat.builtins import asyncio
from .base_hmi import BaseHMI
from logicblock import create_bitarray, bit_2_signed_integer, signed_integer_2_bit

class HMI_pump(BaseHMI):
    def init_hmi(self, *args, **kwargs):
        self.Auto: bool = True
        self.Permissive: bitarray = create_bitarray(32, 1) 
        self.MSG_Permissive: bitarray = create_bitarray(6, 0)# Actually values [1-5] is needed, but for expressiveness, we difine from [0-5]
        self.SD: bitarray  = create_bitarray(32, 0) 
        self.MSG_Shutdown: bitarray = create_bitarray(6, 0)
        self.Reset: bool = False
        self.Reset_RunHr: bool = False
        self.Avl: bool = True
        self.Fault: bool = False
        self.FTS: bool = False
        self.FTR: bool = False
        self.RunHr: float = 0
        self.Total_RunHr: float = 0
        self.Shutdown: bitarray = create_bitarray(32, 0) 
        self.Pump_Running: bool = False
        self.Status: int = 1
        self.Cmd: int = 1

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PMP, self.IO = RemoteDeviceType("FBD"), RemoteDeviceType("IO")
        
        kwargs.update({self.PMP: PMP_FBD, self.IO: IO_PMP_UV})
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        await self.tell_device(self.PMP,
            ("Auto", self.Auto),
            ("Reset", self.Reset),
            ("Reset_RunHr", self.Reset_RunHr),
            ("Permissive", bit_2_signed_integer(self.Permissive)),
            ("SD", bit_2_signed_integer(self.SD)),
            ("Cmd", self.Cmd)
        )

        io_vars, pump_vars = await asyncio.gather(
            self.ask_device(self.IO, "DI_Auto", "DI_Run"),
            self.ask_device(self.PMP, 
                "Cmd", "Avl", "Fault", "FTS", "FTR", "RunHr", "Total_RunHr", "Shutdown"
            )
        )
        self.Remote, Run = io_vars
        Cmd, Avl, Fault, self.FT_Stop, self.FT_Start, \
            self.RunHr, self.Total_RunHr, SD = pump_vars

        self.Status = 2 if Run else 1

        self.Cmd = int(Cmd)
        self.Avl = bool(Avl)
        self.Fault = bool(Fault)
        self.SD = signed_integer_2_bit(int(SD))