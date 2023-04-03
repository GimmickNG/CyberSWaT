from modbus.compat.builtins import asyncio, sleep, time
from typing import Dict, Tuple, Type
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import SCADAStage
from .plc3 import PLC3

class SCADAS3(SCADAStage):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool         = True
        self.Auto_On: bool          = True
        self.Auto_Off: bool         = False
        self.Stop: bool             = False
        self.Start: bool            = True
        self.Critical_SD_On: bool   = False
        self.TMP_High: bool         = False
        self.LIT401_AL: bool        = False
        self.LIT401_ALL: bool       = False
        self.LIT401_AH: bool        = False
        self.LIT401_AHH: bool       = False
        self.P602_Status: bool      = False
        
        dev = kwargs.get("remote_devices", {})
        def get_remote_fbd(tag: str):
            return { "FBD": dev.get(tag), "IO": dev.get(f"IO{tag}") }
        
        self.P3 = HMI_phase()
        
        # self.P3
        self.P3_Mid_NEXT = 0
        # This a variable shared and mostly read by P6 PLC, it's not HMI variable(maybe from SCADA, people can't change)  --PF
        self.Mid_P602_AutoInp = 0
        self.Cy_P3 = HMI_Ultrafiltration_Cycle()
        self.LIT301 = HMI_LIT(remote_devices=get_remote_fbd("LIT301"))
        self.P301   = HMI_pump(remote_devices=get_remote_fbd("P301"))
        self.P302   = HMI_pump(remote_devices=get_remote_fbd("P302"))
        self.P_UF_FEED_DUTY = HMI_duty2(self.P301, self.P302, remote_devices=get_remote_fbd("DTY301"))
        self.FIT301 = HMI_FIT(remote_devices=get_remote_fbd("FIT301"))
        self.PSH301 = HMI_PSH(remote_devices=get_remote_fbd("PSH301"))
        self.DPSH301 = HMI_DPSH(remote_devices=get_remote_fbd("DPSH301"))
        self.DPIT301 = HMI_DPIT(remote_devices=get_remote_fbd("DPIT301"))
        self.MV301, self.MV302, self.MV303, self.MV304 = p3_mv = tuple(
            HMI_mv(remote_devices=get_remote_fbd(f"MV30{i + 1}")) for i in range(4)
        )
        self.p3_devices: Tuple[BaseHMI, ...] = p3_mv + (
            self.Cy_P3, self.LIT301, self.P301, self.P302, self.P_UF_FEED_DUTY,
            self.FIT301, self.PSH301, self.DPSH301, self.DPIT301
        )

        self.Mid_P602_AutoInp: bool = False
        self.P3_Permissive_On: bool = self.P3.Permissive_On
        self.LIT301_AL: bool = self.LIT301.AL
        self.LIT301_AH: bool = self.LIT301.AH
        self.MV301_Status: int = self.MV301.Status

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PLC3 = RemoteDeviceType("PLC301")
        self.device_list = (self.PLC3, PLC3)

        kwargs.update({self.PLC3: PLC3})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),          Tag("Auto_On", bool),
            Tag("Auto_Off", bool),          Tag("Stop", bool),
            Tag("Start", bool),             Tag("Critical_SD_On", bool),
            # set
            Tag("Mid_P602_AutoInp", bool),  Tag("P3_Permissive_On", bool),
            Tag("LIT301_AL", bool),         Tag("LIT301_AH", bool),
            Tag("MV301_Status", int),
            # get
            Tag("TMP_High", bool),          Tag("LIT401_AL", bool),
            Tag("LIT401_ALL", bool),        Tag("LIT401_AH", bool),
            Tag("LIT401_AHH", bool),        Tag("P602_Status", int),
            *tags
        )

    def _reset_and_increment_p3(self, p3_state: int):
        self.P3_Mid_NEXT = 0
        self.P3.State = p3_state + 1

    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started SCADA S3 at time", time())
        await asyncio.gather(*(dev.init_device_map() for dev in self.p3_devices))
        return await super().start()

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self._set_hmi_status(self.Reset_On, self.Auto_On, self.Auto_Off,
            self.MV301, self.MV302, self.MV303, self.MV304, self.P301, self.P302
        )

        self.P3.Permissive_On 	=  all((
            self.MV301.Avl, self.MV302.Avl, self.MV303.Avl,
            self.MV304.Avl, (self.P301.Avl or self.P302.Avl)
        ))
        self.P3_Permissive_On = self.P3.Permissive_On

        await self.tell_device(self.PLC3,
            ("WRIO_Enb", self.WRIO_Enb),        ("P301_Status", self.P301.Status),
            ("P302_Status", self.P302.Status),  ("FIT301_ALL", self.FIT301.ALL),
            ("LIT301_ALL", self.LIT301.ALL),    ("LIT401_AH", self.LIT401_ALL)
        )

        mv_status = self.MV302.Status != 2 and self.MV304.Status != 2
        self.P301.Permissive[0] 	= not self.LIT301.ALL
        self.P301.Permissive[1] 	= not self.LIT401_AHH
        self.P301.Permissive[2] 	= not mv_status

        self.P301.MSG_Permissive[1:4] = \
            self.P302.MSG_Permissive[1:4] = \
                self.P302.Permissive[0:3] = self.P301.Permissive[0:3]

        self.P301.SD[0] 	= self.LIT301.ALL
        self.P301.SD[1] 	= self.LIT401_AHH
        self.P301.SD[2] 	= self.PSH301.Alarm
        self.P301.SD[3] 	= 0
        self.P301.SD[4] 	= self.P301.Status ==2 and mv_status

        self.P302.SD[0:4] 	= self.P301.SD[0:4]
        self.P302.SD[4] 	= self.P302.Status ==2 and mv_status

        self._copy_shutdowns(slice(1, 6), slice(0, 5), self.P301, self.P302)

        if self.Stop or self.Critical_SD_On:
            self.P3.Shutdown=True
        
        if self.DPIT301.Hty:
            self.TMP_High= self.DPIT301.AH
        else:
            self.TMP_High= self.DPSH301.Alarm

        if self.LIT401_AH and self.P3.State > 1:
            self.P3.State=99
        
        await self.tell_device(self.PLC3,
            ("State", self.P3.State), ("Mid_MV304_AutoInp", not self.LIT301.ALL and not self.LIT401_AH)
        )
        
        p3_mn = self.P3_Mid_NEXT
        self.Cy_P3._state = p3_state = self.P3.State
        p7_reset_condition = (p3_mn or (self.Cy_P3.UF_FILTRATION_MIN>=self.Cy_P3.UF_FILTRATION_MIN_SP))
        reset_and_increment_states = (2 <= p3_state <= 18) and any((
            (p3_state ==  2 or p3_state == 15) and (p3_mn or self.MV304.Status == 2),
            p3_state ==  3 and     (p3_mn or self.P_UF_FEED_DUTY.Pump_Running),
            p3_state ==  4 and     (p3_mn or (sec_pulse and self.Cy_P3.UF_REFILL_SEC>self.Cy_P3.UF_REFILL_SEC_SP)),
            p3_state ==  5 and     (p3_mn or self.MV302.Status == 2),
            p3_state ==  6 and     (p3_mn or self.MV304.Status == 1),
            p3_state ==  7 and     (p7_reset_condition or (self.P3.Shutdown and self.LIT401_AH)),
            p3_state ==  8 and     (p3_mn or not self.P_UF_FEED_DUTY.Pump_Running),
            p3_state ==  9 and not self.P3.Shutdown and (p3_mn or self.MV302.Status==1),
            p3_state == 10 and     (p3_mn or (self.MV301.Status==2 and self.MV303.Status==2)),
            p3_state == 11 and     (p3_mn or self.P602_Status == 2),
            p3_state == 14 and     (p3_mn or self.MV301.Status == 1),
            p3_state == 17 and     (p3_mn), #or self.P_NAOCL_UF_DUTY.Pump_Running), # NOTE: P_NAOCL_UF_DUTY doesn't appear anywhere
            p3_state == 18 and     (p3_mn or (sec_pulse and self.Cy_P3.CIP_CLEANING_SEC>self.Cy_P3.CIP_CLEANING_SEC_SP)),
        ))
        
        if p3_state == 1 and (self.P3.Permissive_On and self.Start):
            self.P3.State=2
        elif p3_state == 7:			
            if self.P3.TMP_High:
                self.P3.State=8	
            elif min_pulse:
                self.Cy_P3.UF_FILTRATION_MIN+=1
        elif p3_state == 9 and self.P3.Shutdown:	
            self.P3.State=1
        elif p3_state == 12 and (self.P3_Mid_NEXT or (sec_pulse and self.Cy_P3.BACKWASH_SEC> self.Cy_P3.BACKWASH_SEC_SP)):
            self._reset_and_increment_p3(p3_state)
            self.Cy_P3.BW_CNT +=1
        elif p3_state == 13 and (self.P3_Mid_NEXT or self.P602_Status==1):
            self.P3.State = 14
        elif p3_state == 16 and (self.P3_Mid_NEXT or (sec_pulse and self.Cy_P3.DRAIN_SEC>self.Cy_P3.DRAIN_SEC_SP)):
            self.P3_Mid_NEXT=0
            self.P3.State=4
        elif p3_state == 19 and (self.P3_Mid_NEXT):# or not self.P_NAOCL_UF_DUTY.Pump_Running): # NOTE: P_NAOCL_UF_DUTY
            self.P3_Mid_NEXT=0
            self.P3.State=14
        elif p3_state == 99:
            if  (self.LIT401_AL and not self.P3.Shutdown) or self.Start:
                self.P3.State=2
            elif self.LIT401_AH and self.P3.Shutdown:
                self.P3.State=1
        elif not reset_and_increment_states:
            self.P3.State=1

        if reset_and_increment_states:
            self._reset_and_increment_p3(p3_state)

        self.Mid_P602_AutoInp = bool(await self.ask_device(self.PLC3, "Mid_P602_AutoInp"))

        await self._run_hmis(sec_pulse, min_pulse, hrs_pulse, time_interval,
            self.LIT301, self.P_UF_FEED_DUTY, self.P301, self.P302,
            self.FIT301, self.PSH301, self.DPSH301, self.DPIT301,
            self.MV301, self.MV302, self.MV303, self.MV304
        )
        
        self.LIT301_AL = self.LIT301.AL
        self.LIT301_AH = self.LIT301.AH
        self.MV301_Status = self.MV301.Status