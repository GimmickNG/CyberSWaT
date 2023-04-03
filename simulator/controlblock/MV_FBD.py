from typing import Dict, Optional, Tuple, Type, cast

from modbus.types.remote import RemoteDeviceType
# from HMI import HMI_mv
from .base_fbd import FBD
from logicblock import TONR
from io_plc import IO_MV
from modbus.base import BaseModbusDevice
from modbus.tag import Tag
# from io_plc import IO_MV

class MV_FBD(FBD):
    def init_fbd(self, 
        Open_TM, Close_TM, FTO: bool, FTC: bool, Open: bool, Close: bool, *args, **kwargs
    ) -> None:
        self.FTO: bool = FTO
        self.FTC: bool = FTC

        self.Cmd_Open: bool = Open
        self.Cmd_Close: bool = Close
        self.TON_Close: TONR = TONR(Close_TM, self.device_frequency)
        self.TON_Open: TONR  = TONR(Open_TM, self.device_frequency)

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.IO = RemoteDeviceType("IO")
        
        kwargs.update({self.IO: IO_MV})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Auto", bool),      Tag("Reset", bool),
            Tag("Avl", bool),       Tag("FTO", bool),
            Tag("FTC", bool),       Tag("AutoInp", bool),
            Tag("Cmd", int),        *tags
        )

    @property
    def _ft_started_at_least_once(self):
        return self.FTC or self.FTO

    def _set_ft(self, open: bool, closed: Optional[bool] = None):
        if open == closed: # resets if closed is explicitly specified and equal to open
            self.FTC = self.FTO = False
        else:
            self.FTC = not open
            self.FTO = open

    def _set_cmd(self, open: bool, closed: Optional[bool] = None):
        if open == closed: # resets if closed is explicitly specified and equal to open
            self.Cmd_Close = self.Cmd_Open = False
        else:
            self.Cmd_Close = not open
            self.Cmd_Open  = open
    
    async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        ZSC = await self.ask_device(self.IO, "DI_ZSC")

        self.TON_Close.tick(self.Cmd_Close)
        self.TON_Open.tick(self.Cmd_Open)
        
        self.Avl = self.Auto and not self._ft_started_at_least_once

        if self.Reset:
            self._set_ft(open=False, closed=False)
        
        if self.Auto:
            self.Cmd = 2 if self.AutoInp and not self._ft_started_at_least_once else 1

        if self.Cmd == 1:
            self._set_cmd(open=False)
            if self.TON_Close.DN and not ZSC:
                self._set_ft(open=False)
        elif self.Cmd == 2:
            if self.Auto or self._ft_started_at_least_once:
                self._set_cmd(open=True)
            if self.TON_Open.DN and not ZSC:
                self._set_ft(open=True)
                if not self.Auto:
                    self.Cmd = 1
        #else:
            #print ("Error, Cmd value must be 1 or 2 but received", Cmd)

        await self.tell_device(self.IO,
            ("DO_Open", self.Cmd_Open),
            ("DO_Close", self.Cmd_Close),
        )
