from modbus.compat.builtins import asyncio, sleep, time
from typing import Dict, Tuple, Type
from HMI import *
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from .base_plc import PLC
from .plc0_1 import SCADAS1
from .plc0_2 import SCADAS2
from .plc0_3 import SCADAS3
from .plc0_4 import SCADAS4
from .plc0_5 import SCADAS5
from .plc0_6 import SCADAS6

class SCADA(PLC):
    def init_plc(self, *args, **kwargs) -> None:
        # set plant tags
        self.Reset_On: bool         = True
        self.Auto_On: bool          = True
        self.Auto_Off: bool         = False
        self.Ready: bool            = True
        self.Stop: bool             = False
        self.Start: bool            = True
        self.Critical_SD_On: bool   = False
        
    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        stage_classes = (SCADAS1, SCADAS2, SCADAS3, SCADAS4, SCADAS5, SCADAS6)
        self.SC1, self.SC2, self.SC3, self.SC4, self.SC5, self.SC6 = stage_names = tuple(
            RemoteDeviceType(cls.__name__) for cls in stage_classes
        )
        self.device_list = tuple(zip(stage_names, stage_classes))

        kwargs.update({
            device_name: device_class for device_name, device_class in self.device_list
        })
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Reset_On", bool),          Tag("Auto_On", bool),
            Tag("Auto_Off", bool),          Tag("Ready", bool),
            Tag("Stop", bool),              Tag("Start", bool),
            Tag("Critical_SD_On", bool),    *tags
        )

    async def start(self):
        await sleep(max(0, self.start_time + 3 - time()))
        print("started SCADA at time", time())
        return await super().start()

    async def _run_sc1(self):
        (P3_Permissive_On, LIT301_AL, LIT301_AH), \
            (P2_Permissive_On, MV201_Status), \
                P4_Permissive_On, P5_Permissive_On = await asyncio.gather(
                    self.ask_device(self.SC3, "P3_Permissive_On", "LIT301_AL", "LIT301_AH"),
                    self.ask_device(self.SC2, "P2_Permissive_On", "MV201_Status"),
                    self.ask_device(self.SC4, "P4_Permissive_On"),
                    self.ask_device(self.SC5, "P5_Permissive_On")
                )

        PX_Ready = all((
            P2_Permissive_On, P3_Permissive_On,
            P4_Permissive_On, P5_Permissive_On
        ))
        await self.tell_device(self.SC1,
            ("LIT301_AL", LIT301_AL), ("LIT301_AH", LIT301_AH),
            ("MV201_Status", MV201_Status), ("PX_Ready", PX_Ready)
        )

    async def _run_sc2(self):
        (LIT301_AL, LIT301_AH, MV301_Status), (AIT402_AL, AIT402_AH), \
            (AIT503_AL, AIT503_AH) = await asyncio.gather(
                self.ask_device(self.SC3, "LIT301_AL", "LIT301_AH", "MV301_Status"),
                self.ask_device(self.SC4, "AIT402_AL", "AIT402_AH"),
                self.ask_device(self.SC5, "AIT503_AL", "AIT503_AH"),
            )
        
        await self.tell_device(self.SC2,
            ("MV301_Status", MV301_Status),   ("LIT301_AL", LIT301_AL),
            ("LIT301_AH", LIT301_AH),         ("AIT402_AL", AIT402_AL),
            ("AIT402_AH", AIT402_AH),         ("AIT503_AL", AIT503_AL),
            ("AIT503_AH", AIT503_AH)
        )

    async def _run_sc3(self):
        (LIT401_AL, LIT401_ALL, LIT401_AH, LIT401_AHH), P602_Status = await asyncio.gather(
            self.ask_device(self.SC4, "LIT401_AL", "LIT401_ALL", "LIT401_AH", "LIT401_AHH"),
            self.ask_device(self.SC6, "P602_Status")
        )

        await self.tell_device(self.SC3,
            ("LIT401_AL", LIT401_AL),   ("LIT401_ALL", LIT401_ALL),
            ("LIT401_AH", LIT401_AH),   ("LIT401_AHH", LIT401_AHH),
            ("P602_Status", P602_Status)
        )

    async def _run_sc4(self):
        MV501_Status, MV502_Status, MV503_Status, MV504_Status, Cy_P5_RO_HPP_SD_On = \
            await self.ask_device(self.SC5,
                "MV501_Status", "MV502_Status", "MV503_Status",
                "MV504_Status", "Cy_P5_RO_HPP_SD_On"
            )

        await self.tell_device(self.SC4,
            ("Cy_P5_RO_HPP_SD_On", Cy_P5_RO_HPP_SD_On), ("MV501_Status", MV501_Status),
            ("MV502_Status", MV502_Status),             ("MV503_Status", MV503_Status),
            ("MV504_Status", MV504_Status)
        )

    async def _run_sc5(self):
        FIT401_ALL, P401_Status, P402_Status, UV401_Status, \
            P_RO_FEED_Pump_Running = await self.ask_device(self.SC4,
                "FIT401_ALL", "P401_Status", "P402_Status", "UV401_Status",
                "P_RO_FEED_Pump_Running"
            )

        await self.tell_device(self.SC5,
            ("FIT401_ALL", FIT401_ALL),     ("P401_Status", P401_Status),
            ("P402_Status", P402_Status),   ("UV401_Status", UV401_Status),
            ("P_RO_FEED_Pump_Running", P_RO_FEED_Pump_Running)
        )

    async def _run_sc6(self):
        LIT101_AHH, AIT202_Pv, Mid_P602_AutoInp = \
            await asyncio.gather(
                self.ask_device(self.SC1, "LIT101_AHH"),
                self.ask_device(self.SC2, "AIT202_Pv"),
                self.ask_device(self.SC3, "Mid_P602_AutoInp")
            )
        await self.tell_device(self.SC6,
            ("Mid_P602_AutoInp", Mid_P602_AutoInp), ("LIT101_AHH", LIT101_AHH),
            ("AIT202_Pv", AIT202_Pv),
        )

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        await asyncio.gather(
            self._run_sc1(),    self._run_sc2(),    self._run_sc3(),
            self._run_sc4(),    self._run_sc5(),    self._run_sc6(),
            *(
                self.tell_device(device, 
                    ("Reset_On", self.Reset_On),    ("Auto_On", self.Auto_On),
                    ("Auto_Off", self.Auto_Off),    
                    ("Start", self.Start)
                )
                for device in (self.SC1, self.SC2, self.SC3, self.SC4, self.SC5, self.SC6)
            ),
            *(
                self.tell_device(device, ("Stop", self.Stop))
                for device in (self.SC1, self.SC2, self.SC3, self.SC5, self.SC6)
            ),
            *(
                self.tell_device(device, ("Ready", self.Ready))
                for device in (self.SC1, self.SC4)
            ),
            *(
                self.tell_device(device, ("Critical_SD_On", self.Critical_SD_On))
                for device in (self.SC2, self.SC3, self.SC6)
            )
        )