from typing import Dict, Tuple, Type, cast
from io_plc import IO_AIN_FIT
from modbus.types.remote import RemoteDeviceType
from .base_fbd import FBD
from logicblock import SCL, ALM
from modbus.base import BaseModbusClient, BaseModbusDevice
from modbus.tag import Tag

class AIN_FBD(FBD):
    """Function Block Diagram for Level Transmitters"""

    def init_fbd(self,
        L_Raw_RIO: float, HEU: float, LEU: float, Hty: bool, AHH: bool, AH: bool,
        AL: bool, ALL: bool, Wifi_Enb: bool, *args, **kwargs
    ) -> None:
        self.Hty: bool = Hty
        self.WRIO_Enb: bool = Wifi_Enb
        self.Wifi_Enb: bool = Wifi_Enb
        self.AHH: bool = AHH
        self.AH: bool = AH
        self.AL: bool = AL
        self.ALL: bool = ALL
        
        self.L_Raw_RIO: float   = L_Raw_RIO
        self.H_Raw_RIO: float   = 31208.0
        self.L_Raw_WRIO: float  = 3277.0
        self.H_Raw_WRIO: float  = 16383.0
        self.HEU, self.LEU      = HEU, LEU

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.IO = RemoteDeviceType("IO")

        kwargs.update({self.IO: IO_AIN_FIT})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("WRIO_Enb", bool),  Tag("Pv", float),
            Tag("Hty", bool),       Tag("Wifi_Enb", bool),
            Tag("AHH", bool),       Tag("AH", bool),
            Tag("AL", bool),        Tag("ALL", bool),
            Tag("Sim", bool),       Tag("SAHH", float),
            Tag("SAH", float),      Tag("SAL", float),
            Tag("SALL", float),     *tags
        )
    
    async def _fbd_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float):
        # queries RIO rather than read directly from
        # register because RIO is controlled by AIN
        if self.WRIO_Enb:
            self.Wifi_Enb           =  True
            Mid_H_Raw, Mid_L_Raw    =  self.H_Raw_WRIO, self.L_Raw_WRIO
            Mid_Raw, Mid_Inst_Hty   =  await self.ask_device(self.IO, "W_AI_Value", "W_AI_Hty")
        else:
            self.Wifi_Enb           =  False
            Mid_H_Raw, Mid_L_Raw    =  self.H_Raw_RIO, self.L_Raw_RIO
            Mid_Raw, Mid_Inst_Hty   =  await self.ask_device(self.IO, "AI_Value", "AI_Hty")

        #Calculation for PV*)
        if not self.Sim: # -> Simulation = HMI.Sim
            #print (Mid_Raw, Mid_H_Raw,Mid_L_Raw, self.HEU, self.LEU)
            SCALE_Out = SCL(Mid_Raw, Mid_H_Raw,Mid_L_Raw, self.HEU, self.LEU)
            self.Pv = max(0, SCALE_Out)

        ###Alarms*)
        self.AHH, self.AH, self.AL, self.ALL = ALM(self.Pv, self.SAHH, self.SAH, self.SAL, self.SALL)
        self.Hty = (Mid_Inst_Hty != 0 and (Mid_Raw > Mid_L_Raw) and (Mid_Raw < Mid_H_Raw))
