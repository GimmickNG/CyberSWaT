from typing import Dict, Tuple, Type
from modbus.base import BaseModbusDevice
from modbus.compat.builtins import sleep, time
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
# from io_plc import IO_PMP_UV

class VSD(BaseModbusDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.DI_Auto: bool = True
        self.DI_Run: bool  = False
        self.DI_VSD_PB: bool = False

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("DI_Auto", bool),   Tag("DI_Run", bool),
            Tag("DI_VSD_PB", bool), *tags
        )

class VSD_In(BaseModbusDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.Faulted: bool = False
        self.Active: bool  = False
        self.Ready: bool   = False
        self.OutputFreq: float = 0.0

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("Faulted", bool),   Tag("Active", bool),
            Tag("Ready", bool),     Tag("OutputFreq", float),
            *tags
        )

class VSD_Out(BaseModbusDevice):
    def __init__(self, connected: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connected = connected
        self.ClearFaults: bool = False
        self.Start: bool = False
        self.Stop: bool  = False
        self.FreqCommand: float = 0.0

    #async def start(self):
    #    delay = (time() - self.start_time) * 0.5
    #    print("In VSD_Out, waiting an additional {0} seconds:".format(delay))
    #    await sleep(delay)
    #    return await super().start()

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        self.P50X = RemoteDeviceType("P50X")

        kwargs.update({self.P50X: VSD})
        return super().get_device_classes(**kwargs)
        
    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        if self.connected:
            await self.tell_device(self.P50X, ("DI_Run", self.Start or not self.Stop))

    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            Tag("ClearFaults", bool),   Tag("Start", bool),
            Tag("Stop", bool),          Tag("FreqCommand", float),
            *tags
        )
