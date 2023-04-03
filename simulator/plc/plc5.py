from typing import Dict, Tuple, Type, cast

from modbus.compat.builtins import bitarray, asyncio
from logicblock import * 
from controlblock import *
from modbus.tag import Tag
from modbus.types.remote import RemoteDeviceType
from modbus.base import BaseModbusDevice
from .base_plc import PLC
from modbus.helpers import create_contiguous_states

class PLC5(PLC):
    'plc5 logic'
    
    STATE_LIST = create_contiguous_states(1, 21, {
         1: bitarray("00000"),  3: bitarray("00011"),  5: bitarray("10011"), 
         8: bitarray("11011"),  9: bitarray("11101"), 10: bitarray("11100"),
        13: bitarray("01100"), 14: bitarray("01101"), 15: bitarray("01001"),
        16: bitarray("01011"), 17: bitarray("00011"), 20: bitarray("00000")
    })

    def init_plc(self, *args, **kwargs) -> None:
        self.TON_FIT401_TM=TONR(3, self.device_frequency)
        self.SEC_TEST: int = 0
        self.TEST_MIN: int = 0
        self.Mid_FIT501_Tot_Enb: bool = True
        self.Mid_FIT502_Tot_Enb: bool = True
        self.Mid_FIT503_Tot_Enb: bool = True
        self.Mid_FIT504_Tot_Enb: bool = True
        self.Mid_MV501_AutoInp: bool = True
        self.Mid_MV502_AutoInp: bool = True
        self.Mid_MV503_AutoInp: bool = True
        self.Mid_MV504_AutoInp: bool = True
        self.Mid_P_RO_HIGH_AutoInp: bool = True

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.AIT501, self.AIT502, self.AIT503,self.AIT504, self.PIT501 = (
            RemoteDeviceType(dev) for dev in ("AIT501", "AIT502", "AIT503","AIT504", "PIT501")
        )
        self.PIT502,self.PIT503, self.FIT501, self.FIT502,self.FIT503 = (
            RemoteDeviceType(dev) for dev in ("PIT502","PIT503", "FIT501", "FIT502", "FIT503")
        )
        self.FIT504, self.MV501,self.MV502, self.MV503, self.MV504 = (
            RemoteDeviceType(dev) for dev in ("FIT504", "MV501","MV502", "MV503", "MV504")
        )
        self.DTY501, self.P501, self.P502 = (
            RemoteDeviceType(dev) for dev in ("DTY501", "P501", "P502")
        )
        
        self.device_list = (
            (self.AIT501, AIN_FBD),   (self.AIT502, AIN_FBD), (self.AIT503, AIN_FBD),
            (self.AIT504, AIN_FBD),   (self.PIT501, FIT_FBD), (self.PIT502, FIT_FBD),
            (self.PIT503, FIT_FBD),   (self.FIT501, FIT_FBD), (self.FIT502, FIT_FBD),
            (self.FIT503, FIT_FBD),   (self.FIT504, FIT_FBD), (self.MV501, MV_FBD),
            (self.MV502, MV_FBD),     (self.MV503, MV_FBD),   (self.MV504, MV_FBD),
            (self.DTY501, Duty2_FBD), (self.P501, VSD_FBD), (self.P502, VSD_FBD)
        )

        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)
        
    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        self.Mid_FIT501_Tot_Enb	= self.P501_Status==2 or self.P502_Status==2
        self.Mid_FIT502_Tot_Enb	= self.MV501_Status==2
        self.Mid_FIT503_Tot_Enb	= self.Mid_FIT504_Tot_Enb = \
            self.P401_Status==2 or self.P402_Status==2

        self.TON_FIT401_TM.tick(self.FIT401_ALL and self.Pump_Running) 
        self.TON_FIT401_DN = self.TON_FIT401_TM.DN

        if sec_pulse:
            self.SEC_TEST += 1
        if min_pulse:
            self.TEST_MIN +=1

        if self.State in PLC5.STATE_LIST:
            self.Mid_P_RO_HIGH_AutoInp, self.Mid_MV501_AutoInp, \
                self.Mid_MV502_AutoInp, self.Mid_MV503_AutoInp, self.Mid_MV504_AutoInp = \
                    (bool(flag) for flag in PLC5.STATE_LIST[self.State])
        else:
            self.State = 1

        device_wifi = self.get_device_wifi()
        await asyncio.gather(*(
            self.tell_and_run(ait_dev, device_wifi)
            for ait_dev in (
                self.AIT501, self.AIT502, self.AIT503, self.AIT504,
                self.PIT501, self.PIT502, self.PIT503
            )
        ))

        await asyncio.gather(
            self.tell_and_run(self.FIT501, 
                ("Totaliser_Enb", self.Mid_FIT501_Tot_Enb),
                device_wifi
            ),
            self.tell_and_run(self.FIT502, 
                ("Totaliser_Enb", self.Mid_FIT502_Tot_Enb),
                device_wifi
            ),
            self.tell_and_run(self.FIT503,
                ("Totaliser_Enb", self.Mid_FIT503_Tot_Enb),
                device_wifi
            ),
            self.tell_and_run(self.FIT504, 
                ("Totaliser_Enb", self.Mid_FIT504_Tot_Enb),
                device_wifi
            ),

            self.tell_and_run(self.MV501, ("AutoInp", self.Mid_MV501_AutoInp)),
            self.tell_and_run(self.MV502, ("AutoInp", self.Mid_MV502_AutoInp)),
            self.tell_and_run(self.MV503, ("AutoInp", self.Mid_MV503_AutoInp)),
            self.tell_and_run(self.MV504, ("AutoInp", self.Mid_MV504_AutoInp))
        )

        is_p501_open, is_p502_open = await self.ask_device(self.DTY501, "Start_Pmp1", "Start_Pmp2")
        
        await asyncio.gather(
            self.tell_and_run(self.P501,
                ("AutoSpeed", self.Mid_P50X_AutoSpeed),
                ("AutoInp", is_p501_open)
            ),
            self.tell_and_run(self.P502,
                ("AutoSpeed", self.Mid_P50X_AutoSpeed),
                ("AutoInp", is_p502_open)
            ),
            self.tell_and_run(self.DTY501, ("AutoInp", self.Mid_P_RO_HIGH_AutoInp))
        )

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("P401_Status", int),            Tag("P402_Status", int),
            Tag("P501_Status", int),            Tag("P502_Status", int),
            Tag("Pump_Running", bool),          Tag("MV501_Status", int),
            Tag("FIT401_ALL", bool),            Tag("TON_FIT401_DN", bool),
            Tag("State", int),                  Tag("WRIO_Enb", bool),
            Tag("Mid_P50X_AutoSpeed", float),   *tags
        )
