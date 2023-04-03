from modbus.compat.builtins import asyncio, sleep, time
from typing import Dict, Tuple, Type, cast
from logicblock import XSETD
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import SCADAStage
from .plc1 import PLC1

class SCADAS1(SCADAStage):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool         = True
        self.Auto_On: bool          = True
        self.Auto_Off: bool         = False
        self.Ready: bool            = True
        self.Stop: bool             = False
        self.Start: bool            = True
        self.PX_Ready: bool         = False
        self.LIT301_AL: bool        = False
        self.LIT301_AH: bool        = False
        self.MV201_Status: bool     = False

        dev = kwargs.get("remote_devices", {})
        def get_remote_fbd(tag: str):
            return { "FBD": dev.get(tag), "IO": dev.get(f"IO{tag}") }
        
        self.P1 = HMI_phase()

        # P1
        self.LIT101, self.MV101, self.FIT101, self.P101, self.P102 = (
            HMI_LIT(remote_devices=get_remote_fbd("LIT101")),
            HMI_mv(remote_devices=get_remote_fbd("MV101")),
            HMI_FIT(remote_devices=get_remote_fbd("FIT101")),
            HMI_pump(remote_devices=get_remote_fbd("P101")),
            HMI_pump(remote_devices=get_remote_fbd("P102"))
        )
        
        self.LIT101_AHH: bool       = self.LIT101.AHH
        
        self.P_RAW_WATER_DUTY = HMI_duty2(self.P101, self.P102, remote_devices=get_remote_fbd("DTY101"))
        self.p1_devices: Tuple[BaseHMI, ...] = self.LIT101, self.MV101, self.FIT101, self.P101, self.P102, self.P_RAW_WATER_DUTY

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PLC1 = RemoteDeviceType("PLC101")
        self.device_list = (self.PLC1, PLC1)

        kwargs.update({self.PLC1: PLC1})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),          Tag("Auto_On", bool),
            Tag("Auto_Off", bool),          Tag("Ready", bool),
            Tag("Stop", bool),              Tag("Start", bool),
            #set
            Tag("LIT101_AHH", bool),
            #get
            Tag("LIT301_AL", bool),         Tag("LIT301_AH", bool),
            Tag("MV201_Status", bool),      Tag("PX_Ready", bool),
            *tags
        )

    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started SCADA S1 at time", time())
        await asyncio.gather(*(dev.init_device_map() for dev in self.p1_devices))
        return await super().start()

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self._set_hmi_status(self.Reset_On, self.Auto_On, self.Auto_Off,
            self.MV101, self.P101, self.P102
        )

        await self.tell_device(self.PLC1, 
            ("WRIO_Enb", self.WRIO_Enb),
            ("State", self.P1.State)
        )

        self.P1.Permissive_On = self.MV101.Avl and (self.P101.Avl or self.P102.Avl)
        self.Ready = self.P1.Permissive_On and self.PX_Ready
        self.P101.Permissive[0] = self.LIT101.Hty and not self.LIT101.ALL
        self.P101.Permissive[1] = self.MV201_Status == 2

        self.P101.MSG_Permissive[1:3] = self.P101.Permissive[0:2]

        self.P102.Permissive[0] = self.LIT101.Hty and not self.LIT101.ALL
        self.P102.Permissive[1] = (self.MV201_Status == 2)

        self.P102.MSG_Permissive[1:3] = self.P102.Permissive[0:2]
        
        self.P102.SD[0] = \
            self.P101.SD[0] = self.LIT101.Hty and self.LIT101.ALL
        self.P101.SD[1] = self.P101.Status == 2 and self.MV201_Status != 2

        self.P102.SD[1] = self.P102.Status == 2 and self.MV201_Status != 2
        
        self.P101.SD[2], self.P102.SD[2] = cast(Tuple[bool, bool], 
            await self.ask_device(self.PLC1, ("TON_FIT102_P1_DN"), ("TON_FIT102_P2_DN"))
        )
        
        self._copy_shutdowns(slice(1, 4), slice(0, 3), self.P101, self.P102)

        if self.Stop:
            self.P1.Shutdown = True

        if self.P1.State == 1:
            self.P1.Ready = False
            if self.Ready and self.Start and self.P1.Permissive_On:
                self.P1.State = 2
        elif self.P1.State == 2:
            await asyncio.gather(
                self._xsetd_plc(self.PLC1,
                    XSETD(
                        self.LIT101.AL,
                        self.LIT101.AH
                    ),
                    "Mid_MV101_AutoInp"
                ),
                self._xsetd_plc(self.PLC1,
                    XSETD(
                        self.MV201_Status == 2 and self.LIT301_AL,
                        self.MV201_Status != 2 or self.LIT301_AH
                    ),
                    "Mid_P_RAW_WATER_DUTY_AutoInp"
                )
            )
            if self.P1.Shutdown and self.LIT301_AH:
                self.P1.State = 1
                self.P1.Shutdown = False
        else:
            self.P1.State = 1

        await self._run_hmis(sec_pulse, min_pulse, hrs_pulse, time_interval,
            self.LIT101, self.MV101, self.FIT101, self.P_RAW_WATER_DUTY, self.P101, self.P102
        )
        self.LIT101_AHH = self.LIT101.AHH