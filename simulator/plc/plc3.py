from typing import Dict, List, Tuple, Type, cast
from modbus.compat.builtins import bitarray, asyncio
from modbus.base import BaseModbusDevice
from .base_plc import PLC
from logicblock import *
from controlblock import *
from modbus.tag import Tag
from modbus.types.remote import RemoteDeviceType
from modbus.helpers import create_contiguous_states

class PLC3(PLC):
    'plc3 logic'

    STATE_DICT = create_contiguous_states(1, 20, {
         1: (bitarray('1000000'), False), 
         2: (bitarray('1000000'), None),
         3: (bitarray('1000100'), True),
         6: (bitarray('1010100'), False),
         8: (bitarray('1010000'), False),
         9: (bitarray('1000000'), False),
        10: (bitarray('1101000'), False), 
        11: (bitarray('1101010'), False),
        13: (bitarray('1101000'), False),
        15: (bitarray('1001000'), True),
        17: (bitarray('0101001'), False),
        19: (bitarray('0101000'), False),
        99: (bitarray('0000000'), False),
    })
    
    def init_plc(self, *args, **kwargs) -> None:
        self.TON_FIT301_P1_TM: TONR = TONR(6, self.device_frequency)
        self.TON_FIT301_P2_TM: TONR = TONR(6, self.device_frequency)
        self.SEC_TEST: int = 0
        self.MIN_TEST: int = 0
        self.Mid_MV301_AutoInp: bool = False
        self.Mid_MV302_AutoInp: bool = False
        self.Mid_MV303_AutoInp: bool = False
        self.Mid_MV304_AutoInp: bool = False
        self.Mid_P_UF_FEED_DUTY_AutoInp: bool = False
        self.Mid_P602_AutoInp: bool = False
        self.Mid_P_NAOCL_UF_DUTY_AutoInp: bool = False

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.LIT301, self.DTY301, self.P301, self.P302, self.FIT301, self.PSH301 = (
            RemoteDeviceType(dev) for dev in ("LIT301", "DTY301", "P301", "P302", "FIT301", "PSH301")
        )
        self.DPSH301, self.DPIT301, self.MV301, self.MV302, self.MV303, self.MV304 = (
            RemoteDeviceType(dev) for dev in ("DPSH301", "DPIT301", "MV301", "MV302", "MV303", "MV304")
        )
        
        self.device_list = (
            (self.LIT301, AIN_FBD), (self.DTY301, Duty2_FBD), (self.P301, PMP_FBD),
            (self.P302, PMP_FBD), (self.FIT301, FIT_FBD), (self.PSH301, SWITCH_FBD),
            (self.DPSH301, SWITCH_FBD), (self.DPIT301, AIN_FBD), (self.MV301, MV_FBD),
            (self.MV302, MV_FBD), (self.MV303, MV_FBD), (self.MV304, MV_FBD)
        )

        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        self.Mid_FIT301_Tot_Enb	= self.P301_Status==2 or self.P302_Status==2
        self.TON_FIT301_P1_TM.tick(self.FIT301_ALL and self.P301_Status == 2)
        self.TON_FIT301_P2_TM.tick(self.FIT301_ALL and self.P302_Status == 2)
        if sec_pulse:
            self.SEC_TEST += 1
        if min_pulse:
            self.MIN_TEST += 1

        current_mid_state, auto_inp_flag = PLC3.STATE_DICT.get(self.State, (None, None))
        if current_mid_state is not None:
            self.Mid_MV301_AutoInp, self.Mid_MV302_AutoInp, \
                self.Mid_MV303_AutoInp, self.Mid_P_UF_FEED_DUTY_AutoInp, \
                    self.Mid_P602_AutoInp, self.Mid_P_NAOCL_UF_DUTY_AutoInp = \
                        tuple(bool(flag) for flag in current_mid_state[1:7])
            
            if auto_inp_flag is not None:
                self.Mid_MV304_AutoInp = bool(auto_inp_flag)
            if current_mid_state[0]:
                self.Mid_Last_State = self.State
            if self.State == 2:
                self.Mid_MV304_AutoInp = not any((self.LIT301_ALL, self.LIT401_AH))

        device_wifi = self.get_device_wifi()
        await asyncio.gather(
            self.tell_and_run(self.LIT301, device_wifi),
            self.tell_and_run(self.DTY301, ("AutoInp", self.Mid_P_UF_FEED_DUTY_AutoInp))
        )

        is_p301_open, is_p302_open = await asyncio.gather(
            self.ask_device(self.DTY301, "Start_Pmp1"), self.ask_device(self.DTY301, "Start_Pmp2")
        )
        
        await asyncio.gather(
            self.tell_and_run(self.P301, ("AutoInp", is_p301_open)),
            self.tell_and_run(self.P302, ("AutoInp", is_p302_open)),

            self.tell_and_run(self.FIT301, 
                ("Totaliser_Enb", self.Mid_FIT301_Tot_Enb),
                device_wifi
            ),
        
            # TODO verify PSH301 == SWH301 and DPSH301 == SWH302
            self.run_device(self.PSH301),
            self.run_device(self.DPSH301),
            self.tell_and_run(self.DPIT301, device_wifi),
            self.tell_and_run(self.MV301, ("AutoInp", self.Mid_MV301_AutoInp)),
            self.tell_and_run(self.MV302, ("AutoInp", self.Mid_MV302_AutoInp)),
            self.tell_and_run(self.MV303, ("AutoInp", self.Mid_MV303_AutoInp)),
            self.tell_and_run(self.MV304, ("AutoInp", self.Mid_MV304_AutoInp))
        )

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("WRIO_Enb", bool),          Tag("P301_Status", int),
            Tag("P302_Status", int),        Tag("FIT301_ALL", bool),
            Tag("LIT301_ALL", bool),        Tag("LIT401_AH", bool),
            Tag("State", int),              Tag("Mid_MV304_AutoInp", bool),
            Tag("Mid_P602_AutoInp", bool),  *tags
        )
