from typing import Dict, List, Tuple, Type, cast

from modbus.types.remote import RemoteDeviceType
# from HMI import HMI_FIT
from .base_fbd import FBD
from logicblock import ALM, SCL
from io_plc import IO_AIN_FIT
from modbus.base import BaseModbusClient, BaseModbusDevice
from modbus.tag import Tag
# from io_plc import IO_AIN_FIT

class FIT_FBD(FBD):
    def init_fbd(self, 
        L_Raw_RIO:int, HEU:float, LEU:float, Hty: bool, AHH: bool, AH: bool,
        AL: bool, ALL: bool, Wifi_Enb: bool, *args, **kwargs
    ) -> None:
        self.Hty: bool = Hty
        self.WRIO_Enb: bool = Wifi_Enb
        self.Wifi_Enb: bool = Wifi_Enb
        self.Pv: float = 0
        self.AHH: bool = AHH
        self.AH: bool = AH
        self.AL: bool = AL
        self.ALL: bool = ALL
        
        self.L_Raw_RIO: int = L_Raw_RIO
        self.H_Raw_RIO: int = 31208
        self.L_Raw_WRIO: int = 3277
        self.H_Raw_WRIO: int = 16383
        self.HEU: float = HEU
        self.LEU: float = LEU

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.IO = RemoteDeviceType("IO")
        
        kwargs.update({self.IO: IO_AIN_FIT})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Totaliser_Enb", bool), Tag("Rst_Totaliser", bool),
            Tag("WRIO_Enb", bool),      Tag("Sim", bool),
            Tag("Hty", bool),           Tag("Wifi_Enb", bool),
            Tag("AHH", bool),           Tag("AH", bool),
            Tag("AL", bool),            Tag("ALL", bool),           
            Tag("Totaliser", float),    Tag("Pv", float),
            Tag("Sim_Pv", float),       Tag("SAHH", float),
            Tag("SAH", float),          Tag("SAL", float),
            Tag("SALL", float),         *tags
        )

    def _run_totaliser(self, sec_pulse, reset):
        if reset:
            self.Totaliser = 0.0
        elif sec_pulse and self.Totaliser_Enb:
            self.Totaliser += abs(self.Pv)/3600

    async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        Raw_RIO, Raw_WRIO, RIO_Hty, WRIO_Hty = \
            await self.ask_device(self.IO, "AI_Value", "W_AI_Value", "AI_Hty", "W_AI_Hty")
        
        self._run_totaliser(sec_pulse=sec_pulse, reset=self.Rst_Totaliser)

        self.Wifi_Enb = self.WRIO_Enb
        if self.Wifi_Enb:
            Mid_Raw = Raw_WRIO
            Mid_H_Raw = self.H_Raw_WRIO
            Mid_L_Raw = self.L_Raw_WRIO
            Mid_Inst_Hty = bool(WRIO_Hty)
        else:
            Mid_Raw = Raw_RIO
            Mid_H_Raw = self.H_Raw_RIO
            Mid_L_Raw = self.L_Raw_RIO
            Mid_Inst_Hty = bool(RIO_Hty)

        if self.Sim:
            self.Pv = self.Sim_Pv
        else:
            self.Pv = max(0, SCL(Mid_Raw, Mid_H_Raw, Mid_L_Raw, self.HEU, self.LEU))

        self.AHH, self.AH, self.AL, self.ALL = ALM(self.Pv, self.SAHH, self.SAH, self.SAL, self.SALL)
        self.Hty = Mid_Inst_Hty and (Mid_Raw > Mid_L_Raw) and (Mid_Raw > Mid_H_Raw)
        # original code set HMI.ALL = self.AHH which doesn't sound right
        # revert if errors caused because of this change