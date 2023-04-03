from typing import Dict, List, Tuple, Type, cast
from controlblock import *
from modbus.tag import Tag
from modbus.types.remote import RemoteDeviceType
from modbus.compat.builtins import asyncio
from modbus.base import BaseModbusDevice
from .base_plc import PLC

class PLC6(PLC):
    'plc6 logic'

    def init_plc(self, *args, **kwargs) -> None:
        self.Mid_P601_AutoInp: bool = False
        self.Mid_P602_AutoInp: bool = False
        self.Mid_P603_AutoInp: bool = False
        self.switches = self.LSL601, self.LSL602, self.LSL603, self.LSH601, self.LSH602, self.LSH603

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.LSL601, self.LSL602, self.LSL603, self.LSH601, self.LSH602, self.LSH603 = (
            RemoteDeviceType(dev) for dev in ("LSL601", "LSL602", "LSL603", "LSH601", "LSH602", "LSH603")
        )
        
        self.P601, self.P602, self.P603 = (
            RemoteDeviceType(dev) for dev in ("P601", "P602", "P603")
        )
        
        self.device_list = (
            (self.LSL601, SWITCH_FBD), (self.LSL602, SWITCH_FBD), (self.LSL603, SWITCH_FBD),
            (self.LSH601, SWITCH_FBD), (self.LSH602, SWITCH_FBD), (self.LSH603, SWITCH_FBD),
            (self.P601, PMP_FBD),      (self.P602, PMP_FBD),      (self.P603, PMP_FBD)
        )

        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        self.Mid_FIT601_Tot_Enb	= (self.P602_Status == 2)
        await asyncio.gather(
            self.tell_and_run(self.P601, ("AutoInp", self.Mid_P601_AutoInp)),
            self.tell_and_run(self.P602, ("AutoInp", self.Mid_P602_AutoInp)),
            self.tell_and_run(self.P603, ("AutoInp", self.Mid_P603_AutoInp)),
            *(self.run_device(switch) for switch in self.switches)
        )

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("WRIO_Enb", bool),          Tag("P602_Status", int),
            Tag("Mid_P601_AutoInp", bool),  Tag("Mid_P602_AutoInp", bool),
            Tag("Mid_P603_AutoInp", bool),  *tags
        )
