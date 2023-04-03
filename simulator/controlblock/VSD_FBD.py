from typing import Dict, Optional, Tuple, Type, cast
from logicblock import TONR
from modbus.types.remote import RemoteDeviceType
from modbus.compat.builtins import asyncio
from .base_fbd import FBD
from io_plc import VSD, VSD_In, VSD_Out
from modbus.base import BaseModbusDevice
from modbus.tag import Tag
# from io_plc import VSD_In, VSD_Out
# from HMI import HMI_VSD

class VSD_FBD(FBD):
    def init_fbd(self, 
        Start_TM:int, Stop_TM:int, Avl: bool, Fault: bool, FTS: bool, 
        FTR: bool, RunHr:int, Shutdown: int, Speed:float,
        Drive_Ready: bool, *args, **kwargs
    ) -> None:
        self.SD:int = Shutdown
        self.Avl: bool = Avl
        self.Fault: bool = Fault
        self.FTS:int = FTS
        self.FTR:int = FTR
        self.RunHr:float  = RunHr
        self.Speed:float = Speed
        self.Drive_Ready:bool = Drive_Ready
        self.Total_RunHr:float = RunHr
        self.Shutdown = Shutdown
        
        self.TON_Stop: TONR  = TONR(Stop_TM, self.device_frequency)
        self.TON_Start: TONR = TONR(Start_TM, self.device_frequency)
        self.Total_RunMin:float = 0.0
        self.RunMin:float = 0.0

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.VSD_In, self.VSD_Out, self.VSD = (
            RemoteDeviceType(dev) for dev in ("VSD_In", "VSD_Out", "VSD")
        )
        
        kwargs.update({self.VSD_In: VSD_In, self.VSD_Out: VSD_Out, self.VSD: VSD})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("AutoInp", bool),       Tag("Auto", bool),
            Tag("Reset", bool),         Tag("Reset_RunHr", bool),
            Tag("Avl", bool),           Tag("Fault", bool),
            Tag("FTS", bool),           Tag("FTR", bool),           
            Tag("Drive_Ready", bool),   Tag("AutoSpeed", float),
            Tag("Speed_Command", int),  Tag("Permissive", int),
            Tag("SD", int),             Tag("Cmd", int),
            Tag("RunHr", float),        Tag("Speed", float),        
            Tag("Total_RunHr", float),  Tag("Shutdown", int),
            *tags
        )

    def _set_ft(self, start: bool, stop: Optional[bool] = None):
        if start == stop: # resets if closed is explicitly specified and equal to open
            self.FTR = self.FTS = False
        else:
            self.FTS = not start
            self.FTR = start

    async def _set_vout(self, Start: bool, Stop: Optional[bool] = None):
        """
        Sets VSD_Out Start and Stop to the desired value. If both values are
        specified and are the same, then it is set to Indeterminate (both 0)
        """

        if Start == Stop:
            Start = Stop = False

        await self.tell_device(self.VSD_Out,
            ("Start", Start), ("Stop", not Start if Stop is None else Stop)
        )

    async def _set_vsd_speed(self, speed: float) -> None:
        await self.tell_device(self.VSD_Out, ("FreqCommand", speed))

    def _run_clock(self, min_pulse, Run, Rst_RunHr) -> None:
        if Run and min_pulse:
            self.RunMin += 1.0
            self.Total_RunMin += 1.0

        self.RunHr = self.RunMin/60.0
        self.Total_RunHr = self.Total_RunMin/60.0

        if Rst_RunHr:
            self.RunMin = 0

    async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        (Remote, Run, Start_PB), (Trip, Active, Drive_Ready, self.Speed), (vout_start, vout_stop) = \
            await asyncio.gather(
                self.ask_device(self.VSD, "DI_Auto", "DI_Run", "DI_VSD_PB"),
                self.ask_device(self.VSD_In, "Faulted", "Active", "Ready", "OutputFreq"),
                self.ask_device(self.VSD_Out, "Start", "Stop")
            )

        self.Drive_Ready = bool(Drive_Ready)
        #Permissive = bit_2_signed_integer( self.get_tag_values(None, "Permissive") )
        #Shutdown   = bit_2_signed_integer( self.get_tag_values(None, "SD") )
        # Note: here, all the bitarrays are translated back to integers before it's stored
        # that way it's easier to store in registers, even if it's not 1:1 with the code in
        # the FBD
        
        self.TON_Start.tick(bool(vout_start))
        self.TON_Stop.tick(bool(vout_stop))
        
        self._run_clock(min_pulse, Run or Active, self.Reset_RunHr)
        
        not_started = not self.Fault and not self.FTR and not self.FTS
        vsd_stopped = not Trip and (not self.FTR or self.FTS)
        self.Avl = bool(self.Auto and Remote) and not_started and self.SD == 0
        if self.Reset:
            await self.tell_device(self.VSD_Out, ("ClearFaults", True))
            if not self.TON_Stop.DN:
                self.FTS = 0
            if not self.TON_Start.DN:
                self.FTR = 0
            self.SD = 0

        if Remote:
            if self.Auto:
                if not Active or Trip or self.FTR or self.FTS:
                    self.Cmd = 1
                elif Active:
                    self.Cmd = 2 # Cmd or HMI.Cmd, the original code is realy ambiguous 
                speed, Cmd = (self.AutoSpeed, 2) if self.AutoInp else (self.Speed_Command, 1)
            else:
                speed, Cmd = self.Speed_Command, self.Cmd

            if Cmd == 1:
                await self._set_vout(False)
                if not self.AutoInp:
                    await self._set_vsd_speed(speed)
                if self.TON_Stop.DN and Active:
                    self._set_ft(False)
            elif Cmd == 2:
                if vsd_stopped and self.Permissive == -1 and self.SD == 0:
                    await asyncio.gather(
                        self._set_vout(True), self._set_vsd_speed(speed * 100)
                    )
                elif vout_start or self.SD != 0 or self.Fault:
                    self.SD = int(self.SD)
                    if self.AutoInp:
                        await self._set_vout(False, False)
                        # self.Cmd = 1
                    else:
                        await asyncio.gather(
                            self._set_vout(False), self._set_vsd_speed(speed * 100)
                        )
                        self.Cmd = 1
                if self.TON_Start.DN:
                    if not (self.AutoInp or Run):
                        self._set_ft(True)
                        self.Cmd = 1
                    elif self.AutoInp and not Active:
                        await asyncio.gather(
                            self._set_vout(False), self._set_vsd_speed(speed * 100)
                        )
                        # self.Cmd = 1
        else:
            await asyncio.gather(
                self._set_vout(bool(Start_PB)), self._set_vsd_speed(self.Speed_Command * 110)
            )
            if not (Run and not_started):
                self.Cmd = 1 
            elif Run:
                self.Cmd = 2

        self.Shutdown = self.SD
        # self.set_tag_value("Shutdown", signed_integer_2_bit(self.SD))
        # Note: translation from signed integer to bitarray done above;
        # this is canceled and now only the integers are stored directly
        # change back if problems occur