from modbus.base import BaseModbusClient

class BaseHMI(BaseModbusClient):
    """
    Tag mixin to denote a HMI object. If the `get_device_classes()`
    function is overridden, then this class also acts as a Modbus
    client.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_hmi(*args, **kwargs)

    def init_hmi(self, *args, **kwargs):
        pass
    
    async def _main_loop(self, sec_pulse:bool, min_pulse:bool, hrs_pulse:bool, time_interval: float) -> None:
        pass

