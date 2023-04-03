from typing import Dict, List, Tuple, Type, cast
from logicblock import TONR
from modbus.tag import Tag
from modbus.types.remote import RemoteDeviceType
from modbus.compat.builtins import asyncio
from controlblock import MV_FBD, SWITCH_FBD, PMP_FBD, Duty2_FBD, AIN_FBD, FIT_FBD
from modbus.base import BaseModbusDevice
from .base_plc import PLC

class PLC2(PLC):
    'plc2 logic'

    def init_plc(self, *args, **kwargs) -> None:
        self.TON_FIT102_P1_TM: TONR = TONR(3, self.device_frequency)
        self.TON_FIT102_P2_TM: TONR = TONR(3, self.device_frequency)
        self.TON_FIT102_P3_TM: TONR = TONR(3, self.device_frequency)
        self.TON_FIT102_P4_TM: TONR = TONR(3, self.device_frequency)
        self.TON_FIT102_P5_TM: TONR = TONR(3, self.device_frequency)
        self.TON_FIT102_P6_TM: TONR = TONR(3, self.device_frequency)
        self.Mid_MV201_AutoInp: bool = False
        self.Mid_P_NACL_DUTY_AutoInp: bool = False
        self.Mid_P_HCL_DUTY_AutoInp: bool = False 
        self.Mid_P_NAOCL_FAC_DUTY_AutoInp: bool = False
        self.Mid_FIT201_Tot_Enb: bool = False

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.MV201, self.LSL201, self.LSL202, self.LSLL203, self.DTY201 = (
            RemoteDeviceType(dev) for dev in ("MV201", "LSL201", "LSL202", "LSLL203", "DTY201")
        )
        self.DTY202, self.DTY203, self.P201, self.P202, self.P203, self.P204 = (
            RemoteDeviceType(dev) for dev in ("DTY202", "DTY203", "P201", "P202", "P203", "P204")
        )
        self.P205, self.P206, self.FIT201, self.AIT201, self.AIT202, self.AIT203 = (
            RemoteDeviceType(dev) for dev in ("P205", "P206", "FIT201", "AIT201", "AIT202", "AIT203")
        )
        self.device_list = (
            (self.MV201, MV_FBD), (self.LSL201, SWITCH_FBD), (self.LSL202, SWITCH_FBD),
            (self.LSLL203, SWITCH_FBD), (self.DTY201, Duty2_FBD), (self.DTY202, Duty2_FBD),
            (self.DTY203, Duty2_FBD), (self.P201, PMP_FBD), (self.P202, PMP_FBD), (self.P203, PMP_FBD),
            (self.P204, PMP_FBD), (self.P205, PMP_FBD), (self.P206, PMP_FBD), (self.FIT201, FIT_FBD),
            (self.AIT201, AIN_FBD), (self.AIT202, AIN_FBD), (self.AIT203, AIN_FBD)
        )
        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        self.Mid_FIT201_Tot_Enb = self.MV201_Status == 2
        self.TON_FIT102_P1_TM.tick( self.FIT201_ALL and self.MV201_Status == 2 and self.P201_Status == 2) 
        self.TON_FIT102_P2_TM.tick( self.FIT201_ALL and self.MV201_Status == 2 and self.P202_Status == 2) 
        self.TON_FIT102_P3_TM.tick( self.FIT201_ALL and self.MV201_Status == 2 and self.P203_Status == 2) 
        self.TON_FIT102_P4_TM.tick( self.FIT201_ALL and self.MV201_Status == 2 and self.P204_Status == 2) 
        self.TON_FIT102_P5_TM.tick( self.FIT201_ALL and self.MV201_Status == 2 and self.P205_Status == 2)
        self.TON_FIT102_P6_TM.tick( self.FIT201_ALL and self.MV201_Status == 2 and self.P206_Status == 2)

        self.TON_FIT102_P1_DN = self.TON_FIT102_P1_TM.DN
        self.TON_FIT102_P2_DN = self.TON_FIT102_P2_TM.DN
        self.TON_FIT102_P3_DN = self.TON_FIT102_P3_TM.DN
        self.TON_FIT102_P4_DN = self.TON_FIT102_P4_TM.DN
        self.TON_FIT102_P5_DN = self.TON_FIT102_P5_TM.DN
        self.TON_FIT102_P6_DN = self.TON_FIT102_P6_TM.DN
        
        if self.State == 1:
            self.Mid_MV201_AutoInp = self.Mid_P_NACL_DUTY_AutoInp = \
                    self.Mid_P_HCL_DUTY_AutoInp = self.Mid_P_NAOCL_FAC_DUTY_AutoInp = \
                            self.Mid_P_NAOCL_UF_DUTY_AutoInp = False

        await asyncio.gather(
            self.tell_and_run(self.MV201, ("AutoInp", self.Mid_MV201_AutoInp)),
            self.run_device(self.LSL201),
            self.run_device(self.LSL202),
            self.run_device(self.LSLL203)
        )

        (is_p201_open, is_p202_open), (is_p203_open, is_p204_open), (is_p205_open, is_p206_open) = \
            await asyncio.gather(
                self.ask_device(self.DTY201, "Start_Pmp1", "Start_Pmp2"),
                self.ask_device(self.DTY202, "Start_Pmp1", "Start_Pmp2"),
                self.ask_device(self.DTY203, "Start_Pmp1", "Start_Pmp2")
            )

        device_wifi = self.get_device_wifi()
        await asyncio.gather(
            self.tell_and_run(self.P201, ("AutoInp", is_p201_open)),
            self.tell_and_run(self.P202, ("AutoInp", is_p202_open)),
            self.tell_and_run(self.P203, ("AutoInp", is_p203_open)),
            self.tell_and_run(self.P204, ("AutoInp", is_p204_open)),
            self.tell_and_run(self.P205, ("AutoInp", is_p205_open)),
            self.tell_and_run(self.P206, ("AutoInp", is_p206_open)),

            self.tell_and_run(self.DTY201, ("AutoInp", self.Mid_P_NACL_DUTY_AutoInp)),
            self.tell_and_run(self.DTY202, ("AutoInp", self.Mid_P_HCL_DUTY_AutoInp)),
            self.tell_and_run(self.DTY203, ("AutoInp", self.Mid_P_NAOCL_FAC_DUTY_AutoInp)),

            self.tell_and_run(self.FIT201, 
                ("Totaliser_Enb", self.Mid_FIT201_Tot_Enb),
                device_wifi
            ),
            
            *(
                self.tell_and_run(ait_dev, device_wifi)
                for ait_dev in (self.AIT201, self.AIT202, self.AIT203)
            )
        )

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("WRIO_Enb", bool),                      Tag("MV201_Status", int),
            Tag("P201_Status", int),                    Tag("P202_Status", int),
            Tag("P203_Status", int),                    Tag("P204_Status", int),
            Tag("P205_Status", int),                    Tag("P206_Status", int),
            Tag("FIT201_ALL", bool),                    Tag("Mid_P_NAOCL_FAC_DUTY_AutoInp", bool),  
            Tag("TON_FIT102_P1_DN", bool),              Tag("TON_FIT102_P2_DN", bool),
            Tag("TON_FIT102_P3_DN", bool),              Tag("TON_FIT102_P4_DN", bool),
            Tag("TON_FIT102_P5_DN", bool),              Tag("TON_FIT102_P6_DN", bool),
            Tag("State", int),                          Tag("Mid_MV201_AutoInp", bool),
            Tag("Mid_P_NACL_DUTY_AutoInp", bool),       Tag("Mid_P_HCL_DUTY_AutoInp", bool),
            *tags
        )
