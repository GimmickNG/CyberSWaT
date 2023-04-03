from typing import Dict, Optional, Tuple, Type, cast

from io_plc import IO_PMP_UV
from modbus.types.remote import RemoteDeviceType
# from HMI import HMI_UV
from .base_fbd import FBD
from modbus.base import BaseModbusDevice
from modbus.tag import Tag
from logicblock import TONR
# from io_plc import IO_PMP_UV

class UV_FBD(FBD):
    def init_fbd(self, 
        Start_TM:int, Stop_TM:int, Avl: bool, Fault: bool, FTS: bool,
        FTR: bool, RunHr:int, Shutdown: int, *args, **kwargs
    ) -> None:
        self.FTS:bool = FTS
        self.FTR:bool = FTR
        self.Avl: bool = Avl
        self.Fault: bool = Fault
        self.RunHr:float  = RunHr
        self.Total_RunHr:float = RunHr
        self.Shutdown: int = Shutdown

        self.TON_Stop: TONR   = TONR(Stop_TM,  self.device_frequency)
        self.TON_Start: TONR  = TONR(Start_TM, self.device_frequency)
        self.Cmd_Start: bool = False

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.IO = RemoteDeviceType("IO")
        
        kwargs.update({self.IO: IO_PMP_UV})
        return super().get_device_classes(**kwargs)

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("FTS", bool),           Tag("FTR", bool),
            Tag("Auto", bool),          Tag("Reset", bool),
            Tag("Reset_RunHr", bool),   Tag("AutoInp", bool),
            Tag("Avl", bool),           Tag("Fault", bool),
            Tag("Permissive", int),     Tag("SD", int),
            Tag("Cmd", int),            Tag("RunHr", float),
            Tag("Total_RunHr", float),  Tag("Shutdown", int),
            *tags
        )

    def _set_ft(self, start: bool, stop: Optional[bool] = None):
        if start == stop: # resets if closed is explicitly specified and equal to open
            self.FTR = self.FTS = False
        else:
            self.FTS = not start
            self.FTR = start
            
    def _run_clock(self, hrs_pulse, Run, Rst_RunHr):
        if Run and hrs_pulse:
            self.RunHr += 1.0
            self.Total_RunHr += 1.0

        if Rst_RunHr:
            self.RunHr = 0
    
    async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval):
        Remote, Run, Trip = await self.ask_device(self.IO, "DI_Auto", "DI_Run", "DI_Fault")
        # self.a   = \
        #Permissive = bit_2_signed_integer( self.get_tag_values(None, "Permissive") )
        #Shutdown   = bit_2_signed_integer( self.get_tag_values(None, "SD") )
        # Note: here, all the bitarrays are translated back to integers before it's stored
        # that way it's easier to store in registers, even if it's not 1:1 with the code in
        # the FBD

        self.TON_Stop.tick(not self.Cmd_Start)
        self.TON_Start.tick(self.Cmd_Start)
        
        self._run_clock(hrs_pulse, Run, self.Reset_RunHr)
        
        # this code isn't present in PMP_FBD, does it need to be here?
        if self.Reset:
            if not self.TON_Start.DN:
                self.FTR = False
            if not self.TON_Stop.DN:
                self.FTS = False
            self.SD = 0
        self.Fault = bool(Trip)
        
        not_started = not self.Fault and not self.FTR and not self.FTS
        self.Avl = bool(self.Auto and Remote) and not_started and self.SD == 0
        started_at_least_once = not not_started
        if Remote:
            # fallthrough once done - Cmd set by Auto, commands executed later
            # optimized - similar to PMP_FBD
            if self.Auto:
                Cmd = 2 if self.AutoInp else 1
                if not Run or started_at_least_once:
                    self.Cmd = 1
                elif Run:
                    self.Cmd = 2
            else:
                Cmd = self.Cmd

            if Cmd == 1:
                self.Cmd_Start = False
                if self.TON_Stop.DN and Run:
                    self._set_ft(False)
            elif Cmd == 2:
                if not_started and self.Permissive == -1 and self.SD == 0:
                    self.Cmd_Start = True
                elif self.Fault or (self.AutoInp and self.Cmd_Start) or (self.Cmd_Start and self.SD != 0):
                    self.Cmd_Start = False
                    if not self.Auto:
                        self.Cmd = 1
                if self.TON_Start.DN and not Run:
                    self._set_ft(True)
                    self.Cmd_Start = False
                    # Auto check not present here in original - add it if something goes wrong
                    self.Cmd = 1
        else:
            self.Cmd = 1
            self.Cmd_Start = False
            self.FTR = False
            self.FTS  = False # was originally FTR, i.e. never reset FTS
        
        self.Shutdown = self.SD
        # self.set_tag_value("Shutdown", signed_integer_2_bit(self.SD))
        # Note: translation from signed integer to bitarray done above;
        # this is canceled and now only the integers are stored directly
        # change back if problems occur
        
        await self.tell_device(self.IO, ("Start", self.Cmd_Start))
        # ^ equivalent to IO.Start = self.Cmd_Start - but IO.Start not present in original. Change to DO_Start if things go wrong