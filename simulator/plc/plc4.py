from typing import Dict, List, Tuple, Type, cast
from logicblock import TONR
from controlblock import *
from modbus.tag import Tag
from modbus.types.remote import RemoteDeviceType
from modbus.base import BaseModbusDevice
from modbus.compat.builtins import asyncio
from .base_plc import PLC
class PLC4(PLC):
    'plc4 logic'
    
    def init_plc(self, *args, **kwargs) -> None:
        self.Mid_UV401_AutoInp: bool = False
        self.Mid_FIT401_Tot_Enb: bool = False
        self.TON_FIT401_TM: TONR = TONR(6, self.device_frequency)
        self.TON_FIT401_P1_TM: TONR = TONR(6, self.device_frequency)
        self.TON_FIT401_P2_TM: TONR = TONR(6, self.device_frequency)
        self.Mid_P_RO_FEED_DUTY_AutoInp: bool = False
        self.Mid_P_NAHSO3_ORP_DUTY_AutoInp: bool = False

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.LIT401, self.DTY401, self.DTY402, self.P401, self.P402, self.P403 = (
            RemoteDeviceType(dev) for dev in ("LIT401", "DTY401", "DTY402", "P401", "P402", "P403")
        )
        self.AIT401, self.AIT402, self.FIT401, self.UV401, self.LS401, self.P404 = (
            RemoteDeviceType(dev) for dev in ("AIT401", "AIT402", "FIT401", "UV401", "LS401", "P404")
        )
        
        self.device_list = (
            (self.LIT401, AIN_FBD), (self.DTY401, Duty2_FBD), (self.DTY402, Duty2_FBD),
            (self.P401, PMP_FBD), (self.P402, PMP_FBD), (self.P403, PMP_FBD),
            (self.AIT401, AIN_FBD), (self.AIT402, AIN_FBD), (self.FIT401, FIT_FBD),
            (self.UV401, UV_FBD), (self.LS401, SWITCH_FBD),  (self.P404, PMP_FBD)
        )

        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)
        
    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        self.Mid_FIT401_Tot_Enb	= self.P401_Status == 2 or self.P402_Status == 2
        self.TON_FIT401_TM.tick(self.FIT401_ALL and self.Mid_FIT401_Tot_Enb)
        self.TON_FIT401_P1_TM.tick(self.FIT401_ALL and self.P401_Status == 2)
        self.TON_FIT401_P2_TM.tick(self.FIT401_ALL and self.P402_Status == 2)

        self.TON_FIT401_P1_DN = self.TON_FIT401_P1_TM.DN
        self.TON_FIT401_P2_DN = self.TON_FIT401_P2_TM.DN
        self.TON_FIT401_DN = self.TON_FIT401_TM.DN
        
        if self.State == 1:
            self.Mid_UV401_AutoInp = \
                self.Mid_P_RO_FEED_DUTY_AutoInp = \
                    self.Mid_P_NAHSO3_ORP_DUTY_AutoInp = False

            if self.Permissive_On and self.PLANT_Start:
                self.State=2

        if self.State == 2:
            self.Mid_UV401_AutoInp				= False		
            self.Mid_P_RO_FEED_DUTY_AutoInp		= (self.MV503_Status==2 and self.MV504_Status==2)
            self.Mid_P_NAHSO3_ORP_DUTY_AutoInp	= False

            if self.P_RO_FEED_Pump_Running:
                self.State=3

        if self.State == 3:
            self.Mid_UV401_AutoInp = \
                self.Mid_P_RO_FEED_DUTY_AutoInp	= True
            self.Mid_P_NAHSO3_ORP_DUTY_AutoInp	= False

            if self.UV401_Status == 2:
                self.State=4

        if self.State == 4:
            self.Mid_UV401_AutoInp = self.Mid_P_RO_FEED_DUTY_AutoInp = True

            if self.RO_HPP_SD_On:
                self.State=5

        if self.State == 5:
            self.Mid_UV401_AutoInp				= True
            self.Mid_P_RO_FEED_DUTY_AutoInp		= (self.MV503_Status==1 and self.MV504_Status==1)
            self.Mid_P_NAHSO3_ORP_DUTY_AutoInp	= False

            if not self.P_RO_FEED_Pump_Running:
                self.State=6

        if self.State == 6:
            self.Mid_UV401_AutoInp = \
                self.Mid_P_RO_FEED_DUTY_AutoInp = \
                    self.Mid_P_NAHSO3_ORP_DUTY_AutoInp = False

        device_wifi = self.get_device_wifi()
        await asyncio.gather(
            self.tell_and_run(self.LIT401, device_wifi),
            self.tell_and_run(self.DTY401, ("AutoInp", self.Mid_P_RO_FEED_DUTY_AutoInp))
        )

        is_p401_open, is_p402_open, is_p403_open, is_p404_open = await asyncio.gather(
            self.ask_device(self.DTY401, "Start_Pmp1"), self.ask_device(self.DTY401, "Start_Pmp2"),
            self.ask_device(self.DTY402, "Start_Pmp1"), self.ask_device(self.DTY402, "Start_Pmp2")
        )

        await asyncio.gather(
            self.tell_and_run(self.P401, ("AutoInp", is_p401_open)),
            self.tell_and_run(self.P402, ("AutoInp", is_p402_open)),

            self.tell_and_run(self.AIT401, device_wifi),

            self.tell_and_run(self.FIT401, 
                ("Totaliser_Enb", self.Mid_FIT401_Tot_Enb),
                device_wifi
            ),
            self.tell_and_run(self.AIT402, device_wifi),
            self.tell_and_run(self.UV401, ("AutoInp", self.Mid_UV401_AutoInp)),

            self.run_device(self.LS401),

            self.tell_and_run(self.DTY402, ("AutoInp", self.Mid_P_NAHSO3_ORP_DUTY_AutoInp)),
            self.tell_and_run(self.P403, ("AutoInp", is_p403_open)),
            self.tell_and_run(self.P404, ("AutoInp", is_p404_open))
        )


    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("P_RO_FEED_Pump_Running", bool),        Tag("RO_HPP_SD_On", bool),
            Tag("Permissive_On", bool),                 Tag("WRIO_Enb", bool),
            Tag("UV401_Status", int),                   Tag("State", int),
            Tag("MV503_Status", int),                   Tag("MV504_Status", int),
            Tag("P401_Status", int),                    Tag("P402_Status", int),
            Tag("FIT401_ALL", bool),                    Tag("PLANT_Start", bool),
            Tag("TON_FIT401_P1_DN", bool),              Tag("TON_FIT401_P2_DN", bool),
            Tag("TON_FIT401_DN", bool),                 Tag("Mid_P_NAHSO3_ORP_DUTY_AutoInp", bool), 
            *tags
        )
