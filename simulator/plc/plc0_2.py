from modbus.compat.builtins import asyncio, sleep, time
from typing import Coroutine, Dict, List, Literal, Optional, Tuple, Type, Union, cast
from io_plc import DI_WIFI
from logicblock import XSETD
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import PLC, SCADAStage
from .plc2 import PLC2

class SCADAS2(SCADAStage):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool         = True
        self.Auto_On: bool          = True
        self.Auto_Off: bool         = False
        self.Stop: bool             = False
        self.Start: bool            = True
        self.Critical_SD_On: bool   = False
        self.MV301_Status: bool     = False
        self.LIT301_AL: bool        = False
        self.LIT301_AH: bool        = False    
        self.AIT402_AL: bool        = False
        self.AIT402_AH: bool        = False    
        self.AIT503_AL: bool        = False
        self.AIT503_AH: bool        = False

        dev = kwargs.get("remote_devices", {})
        def get_remote_fbd(tag: str):
            return { "FBD": dev.get(tag), "IO": dev.get(f"IO{tag}") }
        
        self.P2 = HMI_phase()

        # P2
        self.MV201 = HMI_mv(remote_devices=get_remote_fbd("MV201"))
        self.FIT201 = HMI_FIT(remote_devices=get_remote_fbd("FIT201"))
        self.LS201, self.LS202, self.LSL203, self.LSLL203 = p2_switches = (
            HMI_LS(remote_devices=get_remote_fbd("LSL201")),
            HMI_LS(remote_devices=get_remote_fbd("LSL202")),
            HMI_LS(remote_devices=get_remote_fbd("LSL203")),
            HMI_LS(remote_devices=get_remote_fbd("LSLL203"))
        )
        self.P201, self.P202, self.P203, self.P204, \
            self.P205, self.P206, self.P207, self.P208 = p2_pumps = tuple(
                HMI_pump(remote_devices=get_remote_fbd(f"P20{i + 1}")) for i in range(8)
            )
        self.P_NACL_DUTY, self.P_HCL_DUTY, self.P_NAOCL_FAC_DUTY = p2_duty = (
            HMI_duty2(self.P201, self.P202, remote_devices=get_remote_fbd("DTY201")),
            HMI_duty2(self.P203, self.P204, remote_devices=get_remote_fbd("DTY202")),
            HMI_duty2(self.P205, self.P206, remote_devices=get_remote_fbd("DTY203"))
        )
        self.AIT201, self.AIT202, self.AIT203 = p2_ait = (
            HMI_ait(950.0, 260.0, 250.0,50.0, remote_devices=get_remote_fbd("AIT201")),
            HMI_ait(12.0, 7.05, 6.95, 3.0, remote_devices=get_remote_fbd("AIT202")),
            HMI_ait(750.0, 480.0, 440.0, 100.0, remote_devices=get_remote_fbd("AIT203"))
        )

        self.P2_Permissive_On = self.P2.Permissive_On
        self.MV201_Status: int = self.MV201.Status
        self.AIT202_Pv: float = self.AIT202.Pv

        self.p2_devices: Tuple[BaseHMI, ...] = (self.MV201, self.FIT201) + p2_switches + p2_pumps + p2_duty + p2_ait

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PLC2 = RemoteDeviceType("PLC201")
        self.device_list = (self.PLC2, PLC2)

        kwargs.update({self.PLC2: PLC2})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),          Tag("Auto_On", bool),
            Tag("Auto_Off", bool),          Tag("Stop", bool),
            Tag("Start", bool),             Tag("Critical_SD_On", bool),
            # set
            Tag("P2_Permissive_On", bool),  Tag("MV201_Status", int),
            Tag("AIT202_Pv", float),
            # get
            Tag("MV301_Status", bool),      Tag("LIT301_AL", bool),
            Tag("LIT301_AH", bool),         Tag("AIT402_AL", bool),
            Tag("AIT402_AH", bool),         Tag("AIT503_AL", bool),
            Tag("AIT503_AH", bool),         *tags
        )

    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started SCADA S2 at time", time())
        await asyncio.gather(*(dev.init_device_map() for dev in self.p2_devices))
        return await super().start()

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self._set_hmi_status(self.Reset_On, self.Auto_On, self.Auto_Off,
            self.MV201, self.P201, self.P202, self.P203, self.P204,
            self.P205, self.P206, self.P207, self.P208
        )
        
        self.P2.Permissive_On = all((
            self.MV201.Avl, self.P201.Avl or self.P202.Avl,
            self.P203.Avl or self.P204.Avl, self.P205.Avl or self.P206.Avl
        ))
        self.P2_Permissive_On = self.P2.Permissive_On

        await self.tell_device(self.PLC2,
            ("WRIO_Enb", self.WRIO_Enb), ("MV201_Status", self.MV201.Status),
            ("P201_Status", self.P201.Status),   ("P202_Status", self.P202.Status),
            ("P203_Status", self.P203.Status),   ("P204_Status", self.P204.Status),
            ("P205_Status", self.P205.Status),   ("P206_Status", self.P206.Status),
            ("FIT201_ALL", self.FIT201.ALL)
        )
        
        self.P201.Permissive[0] = not self.LS201.Alarm
        self.P201.Permissive[1] = self.MV201.Status == 2
        self.P201.Permissive[2] = self.FIT201.AH

        self.P202.MSG_Permissive[1:4] = \
            self.P201.MSG_Permissive[1:4] = \
                self.P202.Permissive[0:3] = self.P201.Permissive[0:3]
        
        self.P203.Permissive[0] 	= not self.LS202.Alarm
        self.P203.Permissive[1:3] 	= self.P202.Permissive[1:3]

        self.P204.MSG_Permissive[1:4] = \
            self.P203.MSG_Permissive[1:4] = \
                self.P204.Permissive[0:3] = self.P203.Permissive[0:3]
        
        self.P205.Permissive[0] 	= not self.LSL203.Alarm
        self.P205.Permissive[1] 	= self.MV201.Status == 2
        self.P205.Permissive[2] 	= self.FIT201.AH

        self.P206.MSG_Permissive[1:4] = \
            self.P205.MSG_Permissive[1:4] = \
                self.P206.Permissive[0:3] = self.P205.Permissive[0:3]
        
        self.P207.Permissive[0] 	= not self.LSL203.Alarm
        self.P207.Permissive[1] 	= self.MV301_Status == 2
        
        self.P208.Permissive[0:2] 	= self.P207.Permissive[0:2]

        self.P207.MSG_Permissive[1:4] = self.P207.Permissive[0:3]
        self.P208.MSG_Permissive[1:4] = self.P208.Permissive[0:3]
        
        # TODO check if the timers are correct - says fit102 but for process P2?
        P201SD, P202SD, P203SD, P204SD, P205SD, P206SD = \
            await self.ask_device(self.PLC2,
                "TON_FIT102_P1_DN", "TON_FIT102_P2_DN", "TON_FIT102_P3_DN", 
                "TON_FIT102_P4_DN", "TON_FIT102_P5_DN", "TON_FIT102_P6_DN"
            )
        self.P201.SD[2], self.P202.SD[2], self.P203.SD[2], \
            self.P204.SD[2], self.P205.SD[2], self.P206.SD[2] = \
                bool(P201SD), bool(P202SD), bool(P203SD), bool(P204SD), \
                    bool(P205SD), bool(P206SD)

        self.P201.SD[0] 	= self.LS201.Alarm
        self.P201.SD[1] 	= self.P201.Status  ==  2 and self.MV201.Status  !=  2
        self.P202.SD[0:2] 	= self.P201.SD[0:2]
        
        self.P203.SD[0] 	= self.LS202.Alarm
        self.P203.SD[1] 	= self.P201.Status  ==  2 and self.MV201.Status  !=  2
        self.P204.SD[0:2] 	= self.P203.SD[0:2]

        self.P205.SD[0] 	= self.LSL203.Alarm
        self.P205.SD[1] 	= self.P201.Status == 2 and self.MV201.Status != 2
        self.P206.SD[0:2] = self.P205.SD[0:2]
        
        self.P207.SD[0] 	= self.LSL203.Alarm
        self.P207.SD[1] 	= self.P207.Status == 2 and self.MV301_Status != 2

        self.P208.SD[0:2] 	= self.P207.SD[0:2]

        self._copy_shutdowns(slice(1, 4), slice(0, 3), 
            self.P201, self.P202, self.P203, self.P204,
            self.P205, self.P206, self.P207, self.P208
        )
        
        if self.Stop or self.Critical_SD_On:
            self.P2.Shutdown = True

        await self.tell_device(self.PLC2, ("State", self.P2.State))
        if self.P2.State==1:
            if self.P2.Permissive_On and self.Start:
                self.P2.State=2
        elif self.P2.State == 2:
            await asyncio.gather(
                self._xsetd_plc(self.PLC2,
                    XSETD(
                        self.LIT301_AL,
                        self.LIT301_AH
                    ),
                    "Mid_MV201_AutoInp"
                ),
                self._xsetd_plc(self.PLC2,
                    XSETD(
                        self.MV201.Status==2    and self.AIT201.AL  and not self.AIT503_AH,
                        self.MV201.Status!=2    or  self.AIT201.AH  or  self.AIT503_AH      or  self.LS201.Alarm    or  self.FIT201.ALL
                    ),
                    "Mid_P_NACL_DUTY_AutoInp"
                ),
                self._xsetd_plc(self.PLC2,
                    XSETD(
                        self.MV201.Status==2    and self.AIT202.AH,
                        self.MV201.Status!=2    or  self.AIT202.AL  or  self.LS202.Alarm    or  self.FIT201.ALL
                    ),
                    "Mid_P_HCL_DUTY_AutoInp"
                ),
                self._xsetd_plc(self.PLC2,
                    XSETD(
                        self.MV201.Status==2    and self.AIT203.AL  and not self.AIT402_AH,
                        self.MV201.Status!=2    or  self.AIT203.AH  or  self.AIT402_AH      or  self.LSL203.Alarm
                    ),
                    "Mid_P_NAOCL_FAC_DUTY_AutoInp"
                )
            )

            self.P2.Ready = True
            if self.P2.Shutdown and self.LIT301_AH:
                self.P2.State       = 1
                self.P2.Shutdown	= False
        else:	
            self.P2.State=1

        await self._run_hmis(sec_pulse, min_pulse, hrs_pulse, time_interval,
            self.MV201, self.LS201, self.LS202, self.LSL203, self.LSLL203, self.P201,
            self.P202, self.P203, self.P204, self.P205, self.P206, self.P_NACL_DUTY,
            self.P_HCL_DUTY, self.P_NAOCL_FAC_DUTY, self.FIT201, self.AIT201, self.AIT202, self.AIT203
        )

        self.MV201_Status = self.MV201.Status
        self.AIT202_Pv = self.AIT202.Pv