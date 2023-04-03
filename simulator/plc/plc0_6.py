from modbus.compat.builtins import asyncio, sleep, time
from typing import Dict, Tuple, Type
from io_plc import DI_WIFI
from logicblock import XSETD
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import SCADAStage
from .plc6 import PLC6

class SCADAS6(SCADAStage):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool         = True
        self.Auto_On: bool          = True
        self.Auto_Off: bool         = False
        self.Stop: bool             = False
        self.Start: bool            = True
        self.Critical_SD_On: bool   = False
        self.Mid_P601_AutoInp: bool = False
        self.Mid_P602_AutoInp: bool = False
        self.Mid_P603_AutoInp: bool = False
        self.LIT101_AHH: bool       = False
        self.AIT202_Pv: float       = 0.0
        dev = kwargs.get("remote_devices", {})
        def get_remote_fbd(tag: str):
            return { "FBD": dev.get(tag), "IO": dev.get(f"IO{tag}") }
        
        self.IO_DI_WIFI = DI_WIFI()
        self.P6 = HMI_phase()

        # self.P6
        self.LSL601, self.LSL602, self.LSL603 = (
            HMI_LSL(remote_devices=get_remote_fbd(f"LSL60{i + 1}")) for i in range(3)
        )
        self.LSH601, self.LSH602, self.LSH603 = (
            HMI_LSH(remote_devices=get_remote_fbd(f"LSH60{i + 1}")) for i in range(3)
        )
        p6_switches = (self.LSL601, self.LSL602, self.LSL603, self.LSH601, self.LSH602, self.LSH603)
        self.P601, self.P602, self.P603 = p6_pumps = tuple(
            HMI_pump(remote_devices=get_remote_fbd(f"P60{i + 1}")) for i in range(3)
        )
        #self.FIT601 = HMI_FIT(remote_devices=get_remote_fbd("FIT601"))
        self.p6_devices: Tuple[BaseHMI, ...] = p6_pumps + p6_switches# + (self.FIT601,)
        
        self.LSH601_Alarm: bool     = self.LSH601.Alarm
        self.LSL601_Alarm: bool     = self.LSL601.Alarm
        self.P602_Status: int       = self.P602.Status

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.PLC6 = RemoteDeviceType("PLC601")
        self.device_list = (self.PLC6, PLC6)

        kwargs.update({self.PLC6: PLC6})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),          Tag("Auto_On", bool),
            Tag("Auto_Off", bool),          Tag("Stop", bool),
            Tag("Start", bool),             Tag("Critical_SD_On", bool),
            # get
            Tag("Mid_P602_AutoInp", bool),  Tag("LIT101_AHH", bool),
            Tag("AIT202_Pv", float),
            # set
            Tag("LSL601_Alarm", bool),      Tag("LSH601_Alarm", bool),
            Tag("P602_Status", int),        *tags
        )

    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started SCADA S6 at time", time())
        await asyncio.gather(*(dev.init_device_map() for dev in self.p6_devices))
        return await super().start()

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        self._set_hmi_status(self.Reset_On, self.Auto_On, self.Auto_Off,
            self.P601, self.P602, self.P603
        )

        self.P6.Permissive_On = self.P601.Avl and self.P602.Avl
        await self.tell_device(self.PLC6, 
            ("WRIO_Enb", self.WRIO_Enb),
            ("P602_Status", self.P602.Status)
        )

        self.P601.MSG_Permissive[0] = \
            self.P601.Permissive[0] = not self.LSL601.Alarm

        self.P602.MSG_Permissive[0] = \
            self.P602.Permissive[0] = not self.LSL602.Alarm

        self.P603.MSG_Permissive[0] = \
            self.P603.Permissive[0] = not self.LSL603.Alarm

        self.P601.SD[0] 	= self.LSL601.Alarm
        self.P602.SD[0] 	= 0
        self.P603.SD[0] 	= self.LSL603.Alarm

        self._copy_shutdowns(
            slice(1, 6), slice(0, 5), self.P601, self.P602, self.P603
        )

        if self.Stop or self.Critical_SD_On:
            self.P6.State=1

        Mid_P601_AutoInp, Mid_P602_AutoInp, Mid_P603_AutoInp = \
            self.Mid_P601_AutoInp, self.Mid_P602_AutoInp, self.Mid_P603_AutoInp

        if self.P6.State == 1:
            self.Mid_P601_AutoInp = False
            self.Mid_P602_AutoInp = False
            self.Mid_P603_AutoInp = False
            if self.P6.Permissive_On and self.Start:
                self.P6.State = 2 
        elif self.P6.State == 2:
            xsetd = XSETD(
                self.LSH601.Alarm and self.AIT202_Pv >= 7 and not self.LIT101_AHH,
                self.LIT101_AHH or self.LSL601.Alarm or self.AIT202_Pv < 7
            )
            if xsetd is not None:
                Mid_P601_AutoInp = xsetd
            Mid_P602_AutoInp, Mid_P603_AutoInp = self.Mid_P602_AutoInp, self.Mid_P603_AutoInp
        else:
            self.P6.State=1

        await asyncio.gather(
            self.tell_device(self.PLC6, 
                ("Mid_P601_AutoInp", Mid_P601_AutoInp), ("Mid_P602_AutoInp", Mid_P602_AutoInp),
                ("Mid_P603_AutoInp", Mid_P603_AutoInp)
            ),
            self._run_hmis(sec_pulse, min_pulse, hrs_pulse, time_interval,
                self.LSL601, self.LSL602, self.LSL603, self.LSH601, self.LSH602,
                self.LSH603, self.P601,   self.P602,   self.P603
            )
        )

        self.LSH601_Alarm = self.LSH601.Alarm
        self.LSL601_Alarm = self.LSL601.Alarm
        self.P602_Status = self.P602.Status