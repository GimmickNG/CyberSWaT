from modbus.compat.builtins import asyncio, sleep, time
from typing import Dict, Tuple, Type, cast
from logicblock import XSETD
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import SCADAStage
from .plc4 import PLC4

class SCADAS4(SCADAStage):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool             = True
        self.Auto_On: bool              = True
        self.Auto_Off: bool             = False
        self.Ready: bool                = True
        self.Start: bool                = True
        self.Cy_P5_RO_HPP_SD_On: bool   = False
        self.MV501_Status: int          = False
        self.MV502_Status: int          = False
        self.MV503_Status: int          = False
        self.MV504_Status: int          = False

        dev = kwargs.get("remote_devices", {})
        def get_remote_fbd(tag: str):
            return { "FBD": dev.get(tag), "IO": dev.get(f"IO{tag}") }

        self.P4 = HMI_phase()

        # self.P4
        self.LS401 = HMI_LS(remote_devices=get_remote_fbd("LS401"))
        self.P401, self.P402, self.P403, self.P404 = (
            HMI_pump(remote_devices=get_remote_fbd(f"P40{i + 1}")) for i in range(4)
        )
        self.UV401 = HMI_UV(remote_devices=get_remote_fbd("UV401"))
        p4_pumps = (self.P401, self.P402, self.P403, self.P404, self.UV401)
        
        self.P_RO_FEED_DUTY   = HMI_duty2(self.P401, self.P402, remote_devices=get_remote_fbd("DTY401"))
        self.P_NAHSO3_ORP_DUTY = HMI_duty2(self.P403, self.P404, remote_devices=get_remote_fbd("DTY402"))
        self.LIT401, self.AIT401, self.AIT402 = p4_transmitters = (
            HMI_LIT(remote_devices=get_remote_fbd("LIT401")),
            HMI_ait(100.0, 80.0, 0.0, 0.0, remote_devices=get_remote_fbd("AIT401")),
            HMI_ait(800.0, 300.0, 250.0, 200.0, remote_devices=get_remote_fbd("AIT402"))
        )
        
        self.FIT401 = HMI_FIT(remote_devices=get_remote_fbd("FIT401"))
        self.p4_devices: Tuple[BaseHMI, ...] = p4_pumps + p4_transmitters + (
            self.LS401, self.P_NAHSO3_ORP_DUTY, self.P_RO_FEED_DUTY, self.FIT401
        )

        self.P_RO_FEED_Pump_Running: bool = self.P_RO_FEED_DUTY.Pump_Running
        self.P4_Permissive_On: bool            = self.P4.Permissive_On
        self.FIT401_ALL: bool                  = self.FIT401.ALL
        self.AIT402_AL: bool                   = self.AIT402.AL
        self.AIT402_AH: bool                   = self.AIT402.AH
        self.LIT401_AL: bool                   = self.LIT401.AL
        self.LIT401_AH: bool                   = self.LIT401.AH
        self.LIT401_ALL: bool                  = self.LIT401.ALL
        self.LIT401_AHL: bool                  = self.LIT401.AHH
        self.UV401_Status: int                 = self.UV401.Status
        self.P401_Status: int                  = self.P401.Status
        self.P402_Status: int                  = self.P402.Status
        
    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PLC4 = RemoteDeviceType("PLC401")
        self.device_list = (self.PLC4, PLC4)

        kwargs.update({self.PLC4: PLC4})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),      Tag("Auto_On", bool),
            Tag("Auto_Off", bool),      Tag("Ready", bool),
            Tag("Start", bool),         Tag("Cy_P5_RO_HPP_SD_On", bool),    #get
            Tag("MV501_Status", int),   Tag("MV502_Status", int),
            Tag("MV503_Status", int),   Tag("MV504_Status", int),
            # set
            Tag("P_RO_FEED_Pump_Running", bool),
            Tag("FIT401_ALL", bool),    Tag("P4_Permissive_On", bool),
            Tag("AIT402_AL", bool),     Tag("AIT402_AH", bool),
            Tag("LIT401_AL", bool),     Tag("LIT401_ALL", bool),
            Tag("LIT401_AH", bool),     Tag("LIT401_AHH", bool),
            Tag("UV401_Status", int),   Tag("P401_Status", int),
            Tag("P402_Status", int),    *tags
        )

    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started SCADA S4 at time", time())
        await asyncio.gather(*(dev.init_device_map() for dev in self.p4_devices))
        return await super().start()

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self._set_hmi_status(self.Reset_On, self.Auto_On, self.Auto_Off,
            self.P401, self.P402, self.P403, self.P404, self.UV401
        )

        self.P4.Permissive_On = (self.P401.Avl or self.P402.Avl) and (self.P403.Avl or self.P404.Avl) and self.UV401.Avl
        self.P4_Permissive_On = self.P4.Permissive_On

        await self.tell_device(self.PLC4,
            ("P_RO_FEED_Pump_Running", self.P_RO_FEED_DUTY.Pump_Running),
            # below line not in original source code - remove if problems occur
            ("RO_HPP_SD_On", self.Cy_P5_RO_HPP_SD_On),
            ("Permissive_On", self.P4.Permissive_On),
            ("WRIO_Enb", self.WRIO_Enb),
            ("UV401_Status", self.UV401.Status),
            ("MV503_Status", self.MV503_Status),
            ("MV504_Status", self.MV504_Status),
            ("P401_Status", self.P401.Status),
            ("P402_Status", self.P402.Status),
            ("FIT401_ALL", self.FIT401.ALL),
            ("State", self.P4.State)
        )
        
        m5status = self.MV501_Status!=2 and self.MV502_Status!=2 and self.MV503_Status!=2 and self.MV504_Status!=2

        self.P401.Permissive[0] 	= not self.LIT401.ALL
        self.P401.Permissive[1] 	= not m5status

        self.P401.MSG_Permissive[1] = self.P401.Permissive[0]
        self.P401.MSG_Permissive[2] = 0

        self.P402.Permissive[0] 	= not self.LIT401.ALL
        self.P402.Permissive[1] 	= not m5status 

        self.P402.MSG_Permissive[1] = self.P402.Permissive[0]

        self.P403.Permissive[0] 	= not self.LS401.Alarm
        self.P403.Permissive[1]	= self.P401.Status==2 or self.P402.Status==2

        self.P403.MSG_Permissive[1] = self.P403.Permissive[0]
        self.P403.MSG_Permissive[2] = self.P403.Permissive[1]

        self.P404.Permissive[0] 	= not self.LS401.Alarm
        self.P404.Permissive[1] 	= self.P401.Status==2 or self.P402.Status==2

        self.P404.MSG_Permissive[1] = self.P404.Permissive[0]
        self.P404.MSG_Permissive[2] = self.P404.Permissive[1]

        self.UV401.Permissive[0] 	= self.P401.Status==2 or self.P402.Status==2
        self.UV401.Permissive[1] 	= not self.FIT401.ALL

        self.UV401.MSG_Permissive[1] = self.P403.Permissive[0]
        self.UV401.MSG_Permissive[2] = self.P403.Permissive[1]

        
        P401SD, P402SD, UV401SD = await self.ask_device(self.PLC4,
            ("TON_FIT401_P1_DN"), ("TON_FIT401_P2_DN"), ("TON_FIT401_DN")
        )

        self.P401.SD[1], self.P402.SD[1], self.UV401.SD[0] = \
            bool(P401SD), bool(P402SD), bool(UV401SD)

        self.P401.SD[0]	    = self.LIT401.ALL
        self.P401.SD[2]	    = self.P401.Status==2 and m5status 

        self.P402.SD[0]     = self.LIT401.ALL
        self.P402.SD[2]     = self.P402.Status==2 and m5status

        self.P403.SD[0]     = self.LS401.Alarm
        self.P403.SD[1]     = self.FIT401.ALL and (self.P401.Status==2 or self.P402.Status==2)

        self.P404.SD[0:2]   = self.P403.SD[0:2]

        self._copy_shutdowns(
            slice(1, 6), slice(0, 5), self.P401, self.P402, self.P403, self.P404, self.UV401
        )

        if self.P4.State == 1 and self.P4.Permissive_On and self.Start:
            self.P4.State=2
        if self.P4.State == 2 and self.P_RO_FEED_DUTY.Pump_Running:
            self.P4.State=3
        if self.P4.State == 3 and self.UV401.Status==2:
            self.P4.State=4
        if self.P4.State == 4:
            await self._xsetd_plc(self.PLC4,
                XSETD(
                    (self.P401.Status==2 or self.P402.Status==2) and self.AIT402.AH,
                    (self.P401.Status!=2 and self.P402.Status!=2) or self.AIT402.AL
                ),
                "Mid_P_NAHSO3_ORP_DUTY_AutoInp"
            )
            if self.Cy_P5_RO_HPP_SD_On:
                self.P4.State=5
        if self.P4.State == 5 and not self.P_RO_FEED_DUTY.Pump_Running:			
            self.P4.State=6
        if self.P4.State == 6 and self.UV401.Status==1:
            self.P4.State=1
        else:
            self.P4.State=1

        await self._run_hmis(sec_pulse, min_pulse, hrs_pulse, time_interval,
            self.LIT401,    self.P_RO_FEED_DUTY,    self.P401,      self.P402,
            self.AIT401,    self.FIT401,            self.AIT402,    self.UV401,
            self.LS401,     self.P_NAHSO3_ORP_DUTY, self.P403,      self.P404
        )

        self.FIT401_ALL = self.FIT401.ALL
        self.P401_Status = self.P401.Status
        self.P402_Status = self.P402.Status
        self.UV401_Status = self.UV401.Status
        self.AIT402_AL = self.AIT402.AL
        self.AIT402_AH = self.AIT402.AH
        self.LIT401_AL = self.LIT401.AL
        self.LIT401_AH = self.LIT401.AH
        self.LIT401_ALL = self.LIT401.ALL
        self.LIT401_AHL = self.LIT401.AHH
        self.P_RO_FEED_Pump_Running = self.P_RO_FEED_DUTY.Pump_Running