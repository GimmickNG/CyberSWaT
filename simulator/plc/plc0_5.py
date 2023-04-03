from modbus.compat.builtins import asyncio, sleep, time
from typing import Dict, Tuple, Type, cast
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import SCADAStage
from .plc5 import PLC5

class SCADAS5(SCADAStage):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool                = True
        self.Auto_On: bool                 = True
        self.Auto_Off: bool                = False
        self.Stop: bool                    = False
        self.Start: bool                   = True
        self.P_RO_FEED_Pump_Running: bool  = False
        self.FIT401_ALL: bool              = False
        self.P401_Status: int              = 0
        self.P402_Status: int              = 0
        self.UV401_Status: int             = 0

        dev = kwargs.get("remote_devices", {})
        def get_remote_fbd(tag: str):
            return { "FBD": dev.get(tag), "IO": dev.get(f"IO{tag}") }
        
        self.P5 = HMI_phase()

        # self.P5
        self.P5_Mid_NEXT = 0
        self.Mid_Stop    = 0
        # This a variable shared and mostly read by P6 PLC, it's not HMI variable(maybe from SCADA, people can't change),but in our current PLC coding, Phase 5 is not writing to this variable, it keeps 0  --PF
        self.Mid_P603_AutoInp = 0
        self.Mid_P50X_AutoSpeed = 0
        self.AIT501, self.AIT502, self.AIT503, self.AIT504 = (
            HMI_ait(0.0,     0.0,   0.0, 0.0, remote_devices=get_remote_fbd("AIT501")),
            HMI_ait(300.0, 250.0,   0.0, 0.0, remote_devices=get_remote_fbd("AIT502")),
            HMI_ait(500.0, 260.0, 250.0, 0.0, remote_devices=get_remote_fbd("AIT503")),
            HMI_ait(15.0,   12.0,   0.0, 0.0, remote_devices=get_remote_fbd("AIT504")),
        )
        self.PIT501, self.PIT502, self.PIT503 = (
            HMI_PIT(remote_devices=get_remote_fbd(f"PIT50{i + 1}")) for i in range(3)
        )
        p5_transmitters = (self.AIT501, self.AIT502, self.AIT503, self.AIT504, self.PIT501, self.PIT502, self.PIT503)
        self.FIT501, self.FIT502, self.FIT503, self.FIT504 = p5_fits = tuple(
            HMI_FIT(remote_devices=get_remote_fbd(f"FIT50{i + 1}")) for i in range(4)
        )
        self.MV501, self.MV502, self.MV503, self.MV504 = p5_mv = tuple(
            HMI_mv(remote_devices=get_remote_fbd(f"MV50{i + 1}")) for i in range(4)
        )

        # special case since VSDs are different
        self.P501, self.P502 = p5_vsd = tuple(
            HMI_VSD(remote_devices={
                "VSD": dev[f"IOP50{i + 1}I"], "FBD": dev[f"P50{i + 1}"], "IO": dev[f"IOP50{i + 1}O"]
            }) for i in range(2)
        )
        self.Cy_P5  = HMI_ReverseOsmosis_Cycle()
        self.P_RO_HIGH_DUTY = HMI_duty2(self.P501, self.P502, remote_devices=get_remote_fbd("DTY501"))
        self.p5_devices: Tuple[BaseHMI, ...] = p5_transmitters + p5_fits + p5_mv + p5_vsd + (
            self.Cy_P5, self.P_RO_HIGH_DUTY
        )

        self.Cy_P5_RO_HPP_SD_On: bool   = self.Cy_P5.RO_HPP_SD_On
        self.P5_Permissive_On: bool     = self.P5.Permissive_On
        self.AIT503_AL: bool            = self.AIT503.AL
        self.AIT503_AH: bool            = self.AIT503.AH
        self.MV501_Status: int          = self.MV501.Status
        self.MV502_Status: int          = self.MV502.Status
        self.MV503_Status: int          = self.MV503.Status
        self.MV504_Status: int          = self.MV504.Status

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PLC5 = RemoteDeviceType("PLC501")
        self.device_list = (self.PLC5, PLC5)

        kwargs.update({self.PLC5: PLC5})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),              Tag("Auto_On", bool),
            Tag("Auto_Off", bool),              Tag("Stop", bool),
            Tag("Start", bool),             
            # set
            Tag("P5_Permissive_On", bool),      Tag("Cy_P5_RO_HPP_SD_On", bool),
            Tag("AIT503_AL", bool),             Tag("AIT503_AH", bool),             
            Tag("MV501_Status", int),           Tag("MV502_Status", int),
            Tag("MV503_Status", int),           Tag("MV504_Status", int),
            # get
            Tag("P_RO_FEED_Pump_Running", bool),
            Tag("FIT401_ALL", bool),            Tag("P401_Status", int),
            Tag("P402_Status", int),            Tag("UV401_Status", int),
            *tags
        )

    def _reset_and_increment_p5(self, p5_state: int):
        self.P5_Mid_NEXT = 0
        self.P5.State = max(3, p5_state + 1)
        
    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started SCADA S5 at time", time())
        await asyncio.gather(*(dev.init_device_map() for dev in self.p5_devices))
        return await super().start()

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self._set_hmi_status(self.Reset_On, self.Auto_On, self.Auto_Off,
            self.P501, self.P502, self.MV501, self.MV502, self.MV503, self.MV504
        )
        
        self.P5_Permissive_On = all((
            (self.P501.Avl or self.P502.Avl), self.MV501.Avl,
            self.MV502.Avl, self.MV503.Avl, self.MV504.Avl
        ))
        self.P5_Permissive_On = self.P5.Permissive_On

        await self.tell_device(self.PLC5, 
            ("Pump_Running", self.P_RO_FEED_Pump_Running),
            ("WRIO_Enb", self.WRIO_Enb),
            ("MV501_Status", self.MV501.Status),
            ("P401_Status", self.P401_Status),
            ("P402_Status", self.P402_Status),
            ("P501_Status", self.P501.Status),
            ("P502_Status", self.P502.Status),
            ("FIT401_ALL", self.FIT401_ALL)
        )

        self.P501.Permissive[0] = self.P_RO_FEED_Pump_Running
        self.P501.Permissive[1] = not self.FIT401_ALL
        self.P501.Permissive[2] = self.UV401_Status==2

        self.P502.MSG_Permissive[1:4] = \
            self.P501.MSG_Permissive[1:4] = \
                self.P502.Permissive[0:3] = self.P501.Permissive[0:3]

        self.P501.SD[0] 	= not self.P_RO_FEED_Pump_Running
        self.P501.SD[1] 	= bool(await self.ask_device(self.PLC5, "TON_FIT401_DN"))
        self.P501.SD[2] 	= self.UV401_Status!=2
        self.P501.SD[3] 	= 0
        self.P501.SD[4] 	= 0

        self.P502.SD[0:5]   = self.P501.SD[0:5]

        self._copy_shutdowns(slice(1, 6), slice(0, 5), self.P501, self.P502)

        if self.Stop:
            self.P5.State=13

        self.Cy_P5.RO_TMP	= ((self.PIT501.Pv+ self.PIT503.Pv)/2)-self.PIT502.Pv 
        self.Cy_P5.HPP_Q_MAX_M3H	 	= 2
        self.Cy_P5.HPP_Q_SET_M3H 		= 1.25
        self.Cy_P5.MIN_RO_VSD_SPEED		= self.Cy_P5.HPP_Q_SET_M3H / self.Cy_P5.HPP_Q_MAX_M3H *50 * 0.1
        self.Cy_P5.RAMPING_RATE_PER_SEC	= 1.5
        self.Cy_P5.VSD_MIN_SPEED		= 10
        self.Cy_P5.VSD_HIGH_SPEED		= 30

        self.Cy_P5._state = p5_state = self.P5.State
        await self.tell_device(self.PLC5, ("State", p5_state))
        # not required as P50X_AutoSpeed sent directly already
        # tell_plc5(self.Cy_P5.VSD_MIN_SPEED, "VSD_MIN_SPEED")
        #Cy_PX.MVXXX.Status => replace with self.MVXXX.Status if things go wrong.
        reset_and_increment_states = (1 <= p5_state <= 20) and any((
            p5_state ==  1 and (self.P5.Permissive_On and self.Start),
            p5_state ==  2 and (self.P5_Mid_NEXT and self.P_RO_FEED_Pump_Running),
            p5_state ==  3 and (self.MV503.Status==2 and self.MV504.Status==2 and self.P_RO_FEED_Pump_Running or self.P5_Mid_NEXT),
            p5_state ==  4 and (self.P5_Mid_NEXT or self.Cy_P5.FLUSHING_MIN>self.Cy_P5.FLUSHING_MIN_SP),
            p5_state ==  5 and (self.P5_Mid_NEXT or (self.P501.Speed >= self.Mid_P50X_AutoSpeed) or (self.P502.Speed >= self.Mid_P50X_AutoSpeed)),
            p5_state ==  6 and (((self.FIT501.Pv > self.Cy_P5.HPP_Q_SET_M3H) and (self.PIT502.Pv<self.PIT503.Pv)) and self.PIT501.Pv>250 or self.P5_Mid_NEXT),
            p5_state ==  7 and (self.P5_Mid_NEXT or self.AIT504.Pv < self.AIT504.SAH),
            # NOTE: Cy_p5.MV50X does not exist; if problems occcur, try replacing self.Cy_P5.MV50X with self.MV50X
            p5_state ==  8 and (self.P5_Mid_NEXT), #or self.Cy_P5.MV501.Status==2),
            p5_state ==  9 and (self.P5_Mid_NEXT), #or self.Cy_P5.MV503.Status==1),
            p5_state == 10 and (self.P5_Mid_NEXT), #or self.Cy_P5.MV502.Status==2),
            p5_state == 11 and (self.P5_Mid_NEXT), #or self.Cy_P5.MV504.Status==1),
            p5_state == 13 and ((self.P501.Speed <= self.Cy_P5.VSD_MIN_SPEED) and (self.P502.Speed <= self.Cy_P5.VSD_MIN_SPEED) or self.P5_Mid_NEXT),
            p5_state == 14 and (self.P5_Mid_NEXT or not self.P_RO_HIGH_DUTY.Pump_Running),
            p5_state == 15 and (self.P5_Mid_NEXT or self.Cy_P5.MV504_TIMEOUT_TM >120), #or self.Cy_P5.MV504.Status==2),
            p5_state == 16 and (self.P5_Mid_NEXT or self.Cy_P5.MV502_TIMEOUT_TM >120), #or self.Cy_P5.MV502.Status==1),
            p5_state == 17 and (self.P5_Mid_NEXT or self.Cy_P5.MV503_TIMEOUT_TM >120), #or self.Cy_P5.MV503.Status==2),
            p5_state == 18 and (self.P5_Mid_NEXT or self.Cy_P5.MV501_TIMEOUT_TM >120), #or self.Cy_P5.MV501.Status==1),
            p5_state == 19 and (self.P5_Mid_NEXT or self.Cy_P5.RO_SD_FLUSHING_MIN>self.Cy_P5.RO_SD_FLUSHING_MIN_SP),
            p5_state == 20 and (self.P5_Mid_NEXT or not self.P_RO_FEED_Pump_Running),
        ))
        
        await self.Cy_P5._main_loop(sec_pulse, min_pulse, hrs_pulse, time_interval)
        if p5_state == 4 and (self.P5_Mid_NEXT or self.Cy_P5.FLUSHING_MIN>self.Cy_P5.FLUSHING_MIN_SP):
            self.Cy_P5.SD_FLUSHING_DONE_On = True
        elif p5_state == 6 and sec_pulse and self.Mid_P50X_AutoSpeed < self.Cy_P5.VSD_HIGH_SPEED and self.PIT502.Pv<self.PIT503.Pv and self.PIT501.Pv<250:
            self.Mid_P50X_AutoSpeed += 0.5
        elif p5_state == 12 and (self.Stop or self.Mid_Stop):
            self.Mid_Stop=0
            self.P5.State=13			
        elif p5_state == 13 and sec_pulse and self.Mid_P50X_AutoSpeed > self.Cy_P5.VSD_MIN_SPEED:
            self.Mid_P50X_AutoSpeed -= 0.5
        elif not reset_and_increment_states or (p5_state == 21 and (self.P5_Mid_NEXT or self.Cy_P5.MV503_TIMEOUT_TM >120 or self.Cy_P5.MV504_TIMEOUT_TM >120)): #or ((self.Cy_P5.MV503.Status==1 and self.Cy_P5.MV504.Status==1)))):
            self.P5.State=1
         
        if reset_and_increment_states:
            self._reset_and_increment_p5(p5_state)
        
        await asyncio.gather(
            self.tell_device(self.PLC5, ("Mid_P50X_AutoSpeed", self.Mid_P50X_AutoSpeed)),
            self._run_hmis(sec_pulse, min_pulse, hrs_pulse, time_interval,
                self.AIT501, self.AIT502, self.AIT503, self.AIT504, self.PIT501, self.PIT502,
                self.PIT503, self.FIT501, self.FIT502, self.FIT503, self.FIT504, self.MV501,
                self.MV502,  self.MV503,  self.MV504,  self.P501,   self.P502,   self.P_RO_HIGH_DUTY
            )
        )

        self.Cy_P5_RO_HPP_SD_On = self.Cy_P5.RO_HPP_SD_On
        self.AIT503_AL = self.AIT503.AL
        self.AIT503_AH = self.AIT503.AH
        self.MV501_Status = self.MV501.Status
        self.MV502_Status = self.MV502.Status
        self.MV503_Status = self.MV503.Status
        self.MV504_Status = self.MV504.Status