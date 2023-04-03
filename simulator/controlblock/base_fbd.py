from typing import List, Tuple, Type, Union
from modbus.base import BaseModbusDevice, BaseModbusClient
from modbus.types.remote import RemoteDeviceType
from modbus.tag import Tag
from logicblock import TONR

class FBD(BaseModbusDevice):

    RUN_TAG: str = "Run_FBD"
    """
    Tag that decides whether an FBD's `_main_loop` is executed or not. All
    FBDs run in a passive mode, and only run their `_main_loop` when their
    Run_FBD tag value is set to a truthy (i.e. non-zero) value.
    """
    
    DEFAULT_RUN_TAG_LOC: int = 9000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug: bool = kwargs.get("debug", False)
        self.init_fbd(*args, **kwargs)

    def init_fbd(self, *args, **kwargs) -> None:
        pass
    
    @classmethod
    def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
        debug_tags = (
            Tag(FBD.RUN_TAG, bool, FBD.DEFAULT_RUN_TAG_LOC),
        )
        return super().get_tags(*(tags + debug_tags))
    
    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        if self.debug or self.get_tag_values(FBD.RUN_TAG):
            await self._fbd_loop(sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs)

    async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs):
        pass
    
async def start_fbd(source: Union[BaseModbusDevice, BaseModbusClient], remote_fbd: RemoteDeviceType):
    """
    Convenience method which has the source tell the destination FBD to start executing. The
    source is the modbus client instance whose `tell_device` method will be called here; the
    `remote_fbd` is the FBD defined as a remote tag (i.e. IP address) / endpoint instance.

    As a result, the `remote_fbd` supplied has to exist in the `source`'s remote device map;
    if it is not found, a KeyError may occur.
    """

    await source.tell_device(remote_fbd, (FBD.RUN_TAG, True))