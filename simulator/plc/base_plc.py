from typing import Tuple, Optional, Literal, Union
from modbus.base import BaseModbusClient, BaseModbusDevice
from modbus.types import RegisterValue
from modbus.types.remote import RemoteDeviceType
from controlblock import FBD, start_fbd
from datetime import datetime
from modbus.compat.builtins import asyncio
from HMI import BaseHMI, HMI_UV, HMI_VSD, HMI_mv, HMI_pump

class PLC(BaseModbusDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_plc(*args, **kwargs)
        print("{0}: {1} started".format(datetime.now(), type(self).__name__))
    
    async def run_device(self, device_alias: RemoteDeviceType) -> None:
        await start_fbd(self, device_alias)

    async def tell_and_run(self, device_alias: RemoteDeviceType, *tag_values: Tuple[str, RegisterValue]) -> None:
        await self.tell_device(device_alias, *(tag_values + ((FBD.RUN_TAG, True),)))

    def get_device_wifi(self) -> Tuple[str, RegisterValue]:
        return "WRIO_Enb", self.WRIO_Enb
        
    def init_plc(self) -> None:
        pass

class SCADAStage(PLC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.WRIO_Enb: bool = False

    async def _xsetd_plc(self, plc: RemoteDeviceType, val: Optional[bool], tag: str):
        if val is not None:
            await self.tell_device(plc, (tag, val))

    async def _run_hmis(self, sec_pulse, min_pulse, hrs_pulse, time_interval, *hmi_list: BaseHMI) -> None:
        await asyncio.gather(*(hmi_client._main_loop(sec_pulse, min_pulse, hrs_pulse, time_interval) for hmi_client in hmi_list))

    def _set_hmi_status(self, reset: bool, auto_on: bool, auto_off: bool, *hmi_list: Union[HMI_mv, HMI_pump, HMI_VSD, HMI_UV]):
        if reset or auto_off or auto_on:
            for hmi in hmi_list:
                if reset:
                    hmi.Reset = True
                if auto_off:
                    hmi.Auto = False
                elif auto_on:
                    hmi.Auto = True

    def _copy_shutdowns(self, dest_slice: slice, src_slice: slice, *pumps: Union[HMI_pump, HMI_UV, HMI_VSD]) -> None:
        for pump in pumps:
            pump.MSG_Shutdown[dest_slice] = pump.Shutdown[src_slice]
