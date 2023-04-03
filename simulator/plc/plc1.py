#!/usr/bin/env python3

# A digital modbus version of the plc
# from io_plc import IO_PMP_UV

# -
# import swat-plc libraries
# -
from logicblock import TONR
from controlblock import AIN_FBD, MV_FBD, FIT_FBD, Duty2_FBD, PMP_FBD
# -
# import other libraries
# -
from typing import Dict, List, Tuple, Type, cast

from modbus.types.remote import RemoteDeviceType
from modbus.compat.builtins import asyncio
from modbus.tag import Tag
from modbus.base import BaseModbusDevice
from .base_plc import PLC

class PLC1(PLC):
    def init_plc(self, *args, **kwargs) -> None:
        self.TON_FIT102_P1_TM: TONR = TONR(10, self.device_frequency)
        self.TON_FIT102_P2_TM: TONR = TONR(10, self.device_frequency)
        self.Mid_MV101_AutoInp: bool = True
        self.Mid_FIT101_Flow_Hty: bool = True
        self.Mid_P_RAW_WATER_DUTY_AutoInp: bool = True
        self.Min_Test: int = 0

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.LIT101, self.MV101, self.FIT101, self.DTY101, self.P101, self.P102 = (
            RemoteDeviceType(dev) for dev in ("LIT101", "MV101", "FIT101", "DTY101", "P101", "P102")
        )
        
        self.device_list = (
            (self.LIT101, AIN_FBD),    (self.MV101, MV_FBD),
            (self.FIT101, FIT_FBD),    (self.DTY101, Duty2_FBD),
            (self.P101, PMP_FBD),      (self.P102, PMP_FBD)
        )

        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)
    
    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self.FIT101_Tot_Enb = (self.MV101_Status == 2)
        
        self.TON_FIT102_P1_TM = TONR(10, self.device_frequency)
        self.TON_FIT102_P1_DN = self.TON_FIT102_P1_TM.DN
        
        self.TON_FIT102_P2_TM = TONR(10, self.device_frequency)
        self.TON_FIT102_P2_DN = self.TON_FIT102_P2_TM.DN

        if min_pulse:
            self.Min_Test += 1

        if self.State == 1:
            self.Mid_MV101_AutoInp = self.Mid_P_RAW_WATER_DUTY_AutoInp = False

        device_wifi = self.get_device_wifi()
        await asyncio.gather(
            self.tell_and_run(self.LIT101, device_wifi),
            self.tell_and_run(self.FIT101, 
                ("Totaliser_Enb", self.Mid_FIT101_Flow_Hty),
                device_wifi
            ),
            self.tell_and_run(self.MV101, ("AutoInp", self.Mid_MV101_AutoInp)),
            self.tell_and_run(self.DTY101, ("AutoInp", self.Mid_P_RAW_WATER_DUTY_AutoInp)),
        )
        
        is_p101_open, is_p102_open = \
            await self.ask_device(self.DTY101, "Start_Pmp1", "Start_Pmp2")

        await asyncio.gather(
            self.tell_device(self.P101, ("AutoInp", is_p101_open)),
            self.tell_device(self.P102, ("AutoInp", is_p102_open)),

            self.run_device(self.P101),
            self.run_device(self.P102),
        )

    def create_identification(self):
        return super().create_identification(
            pname='SWaT Simulated PLC Stage #1', mname='PLC101'
        )

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("WRIO_Enb", bool),                      Tag("State", int),
            Tag("TON_FIT102_P1_DN", bool),              Tag("TON_FIT102_P2_DN", bool),
            Tag("MV101_Status", int),                   Tag("Mid_MV101_AutoInp", bool),
            Tag("Mid_P_RAW_WATER_DUTY_AutoInp", bool),  *tags
        )
