#!/usr/bin/env python3

from typing import Any, Callable, Coroutine, Iterator, List, Optional, Tuple, Type, Dict, Union, cast, overload
from .helpers import get_standalone_tags, create_identification, get_contiguous_tags
from .utils import BaseCounter, RealtimeCounter, SimCounter
from .tag import PayloadBuilder, PayloadDecoder, Tag, SkipTag, T
from .compat.builtins import time, perf_counter
from .compat import IS_PYCOPY
from .types import RegisterValue, ModbusRegisterData, Registers, IPString
from .types.remote import RemoteDeviceType, RemoteDeviceMapping
from .compat.modbus import ModbusDeviceIdentification, ModbusServerContext, ModbusSlaveContext
from .compat.modbus import ModbusSparseDataBlock, AsyncModbusClient, ModbusClient
from .compat.modbus import encode_coils, decode_coils, encode_registers, decode_registers
from .compat.builtins import Event, sleep, asyncio

AsyncRecurringCall = Callable[[bool, bool, bool, float], Coroutine[None, None, Optional[bool]]]

class BaseModbusDevice:
    from . import TIME_INTERVAL, HOUR_IN_SEC

    CYCLES_TAG: str = "__debug_cycles"
    """
    Tag that measures how many times an FBD has run its `_main_loop`.
    """

    FREQ_TAG: str = "__debug_freq"
    """
    Tag that measures the frequency of this device.
    """

    DEFAULT_DEBUG_CYCLES_LOC: int = 9000
    DEFAULT_DEBUG_FREQ_LOC: int = 9004

    def __init__(self, interval: float = TIME_INTERVAL,
        time_scale: float = 1.0, duration: int = HOUR_IN_SEC, *args, **kwargs
    ):
        """
        Initializes the Modbus device with the specified parameters.

        Arguments
        ---------
        event       -   An event flag used by `__main__` to stop the device. 
                        Could be swapped out for a call to `stop()` if made internal.

        interval    -   The time interval between each `_main_loop()` call in seconds.
                        Denotes the speed of the device, e.g. 0.005s = 200Hz. If set
                        to <=0, then realtime counters are used.

        time_scale  -   The time scale of the simulation; 1.0 for realtime, anything
                        else uses a different counter and tick.

        duration    -   The number of timesteps to run for, in terms of `interval`.
                        If set to 0, this device runs forever.

        Other Parameters
        ----------------
        debug       -   Enables debug mode, the effects of which can vary from device
                        to device. For example, FBDs can run without needing a signal
                        when in debug mode.

        unit_id     -   The unit/slave id for this device. Depends on the context that
                        you are initializing; if a modbus device shares its context
                        with another modbus device, then they would share the same unit
                        id as well. However, if they are merely colocated but not
                        sharing data amongst themselves, then different unit ids can be
                        used, provided the rest of the application logic is also set up
                        to query the relevant unit IDs. By default this is 1, and also
                        assumes that other unit IDs to query will be 1.
        """

        super().__init__()
        self.logger = kwargs.get("logger")
        self.interval: float = interval
        self.unit_id: int = kwargs.get("unit_id", 1)
        self.debug: bool = kwargs.get("debug", False)
        self.exec_state: Event = kwargs.get("event", Event())
        self.identification: ModbusDeviceIdentification = self.create_identification()
        self.tag_database: Dict[str, Tag] = self.create_tag_database()
        self.data_store: ModbusServerContext = self.create_context()
        self.start_time: float = kwargs.get("start_time", time())
        self.name = kwargs.get("device_name", "")
        self._debug_prev_cycles: int = 0
        self._debug_cycles: int = 0

        Timer: Type[BaseCounter] = RealtimeCounter if time_scale == 1.0 or interval == 0 else SimCounter
        self.counter: BaseCounter = Timer(duration, self.interval)

        device_classes = self.get_device_classes()
        if len(device_classes):
            client = BaseModbusClient(
                remote_devices=kwargs.get("remote_devices"), device_classes=device_classes, parent=type(self).__name__
            )
            self._init_client = client.init_device_map
            self.ask_device = client.ask_device
            self.tell_device = client.tell_device
        else:
            self._init_client = None
        self._init_complete = True

    async def start(self):
        await sleep(max(0, self.start_time - time()))
        print("started", type(self).__name__, "at time", time())
        if self._init_client is not None:
            await self._init_client()
        await self.run()

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        """
        Creates the device classes for the modbus client to function properly.
        This is not the "true" `get_device_classes()` function, even if it does
        delegate it out to BaseModbusClient's `get_device_classes` function. 
    
        This function is rather used to make it easy for a `BaseModbusDevice` 
        (i.e. a Modbus server) to _also_ be a Modbus client, as a non-empty dict
        returned by this function will automatically signal to the constructor
        to create a delegate client as well. This means that all that a subclass
        of `BaseModbusDevice` needs to do to be a Modbus client is to override
        this function and return a name-class mapping, as `BaseModbusClient`
        expects.

        At the same time, this function is also retained in `BaseModbusClient`
        so that a class can create their own delegate client _without_ having to
        subclass `BaseModbusDevice` - e.g. if they subclass `BaseModbusClient`.

        It is done this way rather than through use of a mixin (which is easier
        and was the original implementation) so as to retain compatibility with
        Pycopy, which runs into undefined behaviour with mixins as of this
        writing.
        """
        
        return BaseModbusClient.get_device_classes(self, **kwargs)  # type: ignore

    @property
    def device_frequency(self) -> int:
        return round(1/self.interval)

    def stop(self):
        self.exec_state.set()

    def get_ticks(self) -> Iterator[Tuple[bool, bool, bool, float]]:
        # TODO: clock synchronization is easy when all the plc files use the system clock
        # but when running faster simulations, then it can become difficult due to need of
        # synchronization. How would this be done then? Would a time server be required for
        # synchronizing the plcs with the physical process? After all, ultimately it is the
        # physical process that is responsible for the speed of the clock ticks - it cannot
        # be run at e.g. 10x realtime without the clocks running at 10x realtime as well, or
        # else the plcs will not be able to control the process effectively

        # for now as PoC use realtime clock as it is the simplest
        return self.counter

    def _init_vars(self, **kwargs) -> Dict[str, Any]:
        """
        Returns a variable mapping for use in _main_loop.
        @see _main_loop
        """
        
        return kwargs

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        """
        The main loop for this device. Runs every <self.interval> seconds.
        
        Arguments
        ---------
        sec_pulse - whether a second has passed since the last tick or not
        min_pulse - whether a minute has passed since the last tick or not
        hrs_pulse - whether an hour has passed since the last tick or not

        Other Arguments
        ---------------
        function is a Dict[str, Any] which is then passed to this function
        as a set of long lived variables (that are not updated during this
        function's lifetime.)

        For example, if _init_vars returns {"HMI": self.HMI}, then this is
        passed to the function as a kwarg: HMI=self.HMI. However, this is
        not updated for each tick, so this is best used to store long-lived
        variables such as data stores.
        """

        pass

    async def run(self) -> None:
        ewma_interval, vars = 0.0, self._init_vars()

        factor = 1/4
        inv_factor = 1 - factor
        for sec_pulse, min_pulse, hrs_pulse, time_interval in self.get_ticks():
            if self.exec_state.is_set():
                break
            ewma_interval = (factor * time_interval) + (inv_factor * ewma_interval)
            await self._main_loop(sec_pulse, min_pulse, hrs_pulse, ewma_interval, **vars)
            self._debug_cycles += 1
            if sec_pulse:
                self.set_tag_value(BaseModbusDevice.FREQ_TAG, self._debug_cycles - self._debug_prev_cycles)
                self._debug_prev_cycles = self._debug_cycles
            self.set_tag_value(BaseModbusDevice.CYCLES_TAG, self._debug_cycles)
            if ewma_interval > 0:
                await sleep(max(0, self.interval - ewma_interval))

    def __setattr__(self, __name: str, __value: Any) -> None:
        if 'tag_database' in self.__dict__ and __name in self.tag_database:
            self.set_tag_value(__name, __value)
        else:
            super().__setattr__(__name, __value)

    def __getattr__(self, __name: str) -> Any:
        if 'tag_database' in self.__dict__ and __name in self.__dict__['tag_database']:
            return self.get_tag_values(__name)
        try:
            return self.__dict__[__name]
        except KeyError:
            raise AttributeError("Attribute {0} not found in {1}".format(__name, type(self).__name__))

    def resolve_tag(self, tag: str) -> Tag:
        if tag not in self.tag_database:
            raise KeyError("Key {0} not in tag database: tag database is currently {1}".format(tag, self.tag_database.keys()))
        return self.tag_database[tag]

    def get_data_store(self) -> ModbusSlaveContext:
        """
        Returns the slave context in the server at the given ID.
        The Modbus Server Context consists of 1 or more slave IDs which are
        addressable by a Modbus packet using the slave id / unit id field.

        Most devices in Modbus TCP have 1 slave ID for them all; that is, it
        does not matter which slave ID you pass to the server context, as it
        will return the same ModbusSlaveContext.

        This can be overridden to have multiple slave contexts in one device
        (for example, if you have a colocated VSD, a VSD input and output);
        if this is done, then this function should also be overridden.
        """

        return self.data_store[self.unit_id]

    def set_tag_value(self, tag_name: str, value: RegisterValue) -> None:
        """
        Sets the register(s) for this tag to the value(s) specified.
        """

        tag = self.resolve_tag(tag_name)
        if tag is None or tag.data_type is None:
            return

        casted_value = tag.data_type(value)
        builder = PayloadBuilder()
        tag.encode_with(casted_value, builder)

        registers = tag.resolve_registers()
        if tag.storage_location == Tag.COILS:
            values = builder.to_coils()
        else:
            values = builder.to_registers()
        self.get_data_store().setValues(
            tag.get_function_code, address=registers.start, values=list(values)
        )
  
    def set_tag_values(self, *tag_values: Tuple[str, RegisterValue]) -> None:
        """
        Sets multiple tag values at once. Right now, it just calls `set_tag_value`
        under the hood, but is open to optimization by writing contiguous registers
        in one call, if it is implemented.
        """

        for name, value in tag_values:
            self.set_tag_value(name, value)

    @overload
    def get_tag_values(self, tag_name: str) -> RegisterValue: 
        """
        Converts the tag to a set of registers and gets its value after decoding it.
        """
        
        pass
    @overload
    def get_tag_values(self, tag_name: Tuple[str, ...]) -> Tuple[RegisterValue, ...]:
        """
        Converts multiple tags to registers and returns their values after decoding them.
        Right now, it just calls `get_tag_value()` under the hood,but this is open to
        optimization by reading contiguous registers and using one decoder, if it is
        implemented.
        """
        
        pass
    @overload
    def get_tag_values(self, tag_name: str, *tag_names: str) -> Tuple[RegisterValue, ...]:
        """
        Converts multiple tags to registers and returns their values after decoding them.
        Right now, it just calls `get_tag_value()` under the hood, but this is open to
        optimization by reading contiguous registers and using one decoder, if it is
        implemented.
        """

        pass
    def get_tag_values(self, tag_name: Union[Tuple[str, ...], str], *tag_names: str) -> Union[RegisterValue, Tuple[RegisterValue, ...]]:
        """
        Converts the tag to register(s) and gets their value(s).
        Returns a list if it is multi-valued, or converts it to 
        the specified datatype if it is a single value.
        """

        if isinstance(tag_name, str):
            tag_name = (tag_name,)

        all_values: Dict[str, RegisterValue] = {}
        all_tag_names: Tuple[str, ...] = tag_name + tag_names
        tag_set = get_contiguous_tags(CommsUtils.identity, CommsUtils.identity,
            *(self.resolve_tag(tag_name) for tag_name in all_tag_names)
        )

        for i, (tags, decode_fn) in enumerate((
            (tag_set.coils, PayloadDecoder.from_coils), 
            (tag_set.holding_registers, PayloadDecoder.from_registers)
        )):
            if not len(tags):
                continue
            
            data_store = self.get_data_store()
            try:
                values: ModbusRegisterData = data_store.getValues(
                    tags[0].get_function_code, address=tags[0].offset,
                    count=sum(tag.data_size for tag in tags)
                )
            except KeyError as err:
                print("Caught keyerror from modbus_structs. tags index is {0}, tags are {1}".format(i, tags))
                print(type(tags).__name__, 'index:', err)
                print("context is", data_store.store["c" if i == 0 else "h"])
            decoder: PayloadDecoder = decode_fn(values)
            for tag in tags:
                all_values[tag.name] = tag.decode_with(decoder)

        ordered_values = tuple(all_values[name] for name in all_tag_names)
        if len(ordered_values) == 1:
            return ordered_values[0]
        return ordered_values

    @classmethod
    def create_tag_database(cls) -> Dict[str, Tag]:
        """
        Maps tags to registers.

        Uses `get_tags()` to create the tag database. Prefer overriding that over this
        unless there is no alternative available.
        """

        return get_standalone_tags(cls.get_tags())

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        """
        Returns a list of tags defined by each device. Usually overridden.
        """

        return tuple(tags) + (
            Tag(BaseModbusDevice.CYCLES_TAG, int, BaseModbusDevice.DEFAULT_DEBUG_CYCLES_LOC),
            Tag(BaseModbusDevice.FREQ_TAG, int)
        )

    def create_identification(self, 
        vname:str="PLC", pcode:str="", vurl:str="http://github.com/GimmickNG/modbus/", 
        pname:str="SWaT Simulated PLC, Generic", mname:str="Generic PLC", revision:str = "1.0.0"
    ) -> ModbusDeviceIdentification:
        return create_identification(
            pcode=type(self).__name__ if pcode == "" else pcode, 
            vname=vname, vurl=vurl, pname=pname, mname=mname, revision=revision
        )

    def create_context(self) -> ModbusServerContext:
        return ModbusServerContext(slaves=ModbusSlaveContext(
            co=ModbusSparseDataBlock(values={
                tag.offset: [0] * tag.data_size
                for tag in self.tag_database.values()
                if tag.storage_location == Tag.COILS
            }),
            hr=ModbusSparseDataBlock(values={
                tag.offset: [0] * tag.data_size
                for tag in self.tag_database.values()
                if tag.storage_location == Tag.HOLDING_REGISTERS
            }),
            zero_mode=True
        ))
        


class BaseModbusClient:
    """
    Adds behaviour to make a device a Modbus client. While this can
    be used with any class (and not just a `BaseModbusDevice`), extra
    functionality is present for some functions if a Modbus context
    is present.
    """

    def __init__(self, *args, **kwargs):
        """
        Creates a Modbus client.
        
        Other Parameters
        ----------------
        remote_devices  -   The list of remote devices to connect to, as a `{ name: "ip:port" }`
                            mapping, e.g. `{"P101": "192.168.0.16:503"}`. If the port is omitted,
                            then the default well-known Modbus port 502 is used.
        
        device_classes  -   The list of device classes that each device name corresponds to, as
                            a mapping of `{ name: class }`, e.g. `{ "P101": IO_PMP_UV }`. Both
                            will need to be non-empty if this client is to be used in any proper
                            capacity, as without them, remote tags cannot be properly generated.
        """
        
        device_classes: Dict[RemoteDeviceType, Type] = kwargs.get('device_classes', {})
        self.parent = kwargs.get("parent", "")

        self._remote_devices: Dict[RemoteDeviceType, IPString] = kwargs.get('remote_devices', {})
        self._device_classes = self.get_device_classes(**device_classes)

    async def init_device_map(self):        
        # device list maps names to classes
        # so in the commandline, FBD will be given --remote-devices = "MV101 192.168.0.1"
        # and the "MV101" will be taken and converted to a device class, by looking at
        # the mapping for "MV101" in the device list
        # so if MV101 => MV_FBD then it uses that for the device map
        self.device_map: Dict[RemoteDeviceType, RemoteDeviceMapping] = await self.create_device_map(
            self._remote_devices, self._device_classes
        )

    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        """
        Used to create a device map with `create_device_map()`.
        Override this function and return a dict of `{device_name: device_ip}` here.
        """
        
        return cast(Dict[RemoteDeviceType, Type], kwargs)

    async def create_device_map(self, ip_map: Dict[RemoteDeviceType, IPString], class_map: Dict[RemoteDeviceType, Type]) -> Dict[RemoteDeviceType, RemoteDeviceMapping]:
        """
        Given inputs in the form `{ device_name: { 'ip': device_ip } }` and 
        `{ device_name: device_class }`, e.g.

        `{ "LIT101":  "192.168.0.1" }` and `{ "LIT101": AIN_FBD }`

        This function populates the tags and registers for the device of the class given 
        by its type (i.e. the second parameter in the tuple). Returns a dictionary of 
        device names that correspond to IP addresses as strings, their type as a class,
        and their associated tags and registers, for example:
        
        `{
            "LIT101": {
                "ip": "192.168.0.1",
                "client": <client connected to ip>
                "tags": {
                    # contains the remote register offset after calling helpers.pack_tags
                    "Auto": Tag <object>
                    "AutoInp": Tag <object>
                }
            }
        }`

        Not to be overriden. Override `get_device_classes` instead.
        """
        
        async def set_mapping_key(device_name: RemoteDeviceType) -> Tuple[RemoteDeviceType, RemoteDeviceMapping]:
            ip_address = ip_map[device_name]
            device_class: Type[BaseModbusDevice] = class_map[device_name]
            if ip_address is None or ':' not in ip_address:
                device_ip, device_port = ip_address, 502
            else:
                device_ip, device_port = ip_address.split(':', 1)
            device_port = int(device_port)

            client = AsyncModbusClient(host=device_ip, port=device_port, timeout=300000)
            await client.connect()
            if not client.connected:
                print(perf_counter(), type(self).__name__, device_name, "@", device_ip, ":", device_port, "=>", type(client.protocol))
            mapping: RemoteDeviceMapping = {
                "ip": IPString(device_ip),
                "port": device_port,
                "client": client.protocol,
                "tags": device_class.create_tag_database()
            }
            return (device_name, mapping)

        # only connect to common devices, rather than all specified devices
        common_keys = list(filter(lambda x: x in ip_map.keys(), class_map.keys()))
        name_mapping = await asyncio.gather(
            *(set_mapping_key(device_name) for device_name in common_keys)
        )
        return {name: mapping for name, mapping in name_mapping}

    def resolve_remote_ip(self, device_alias: RemoteDeviceType) -> IPString:
        return self.device_map[device_alias]["ip"]

    def resolve_remote_tag(self, device_alias: RemoteDeviceType, tag_name: str) -> Tag:
        return self.device_map[device_alias]["tags"][tag_name]

    def resolve_remote_connection(self, device_alias: RemoteDeviceType) -> ModbusClient:
        if device_alias not in self.device_map:
            raise KeyError("Key {0} not found in {1} (parent: {2})".format(device_alias, self.device_map, self.parent))
        return self.device_map[device_alias]["client"]

    @overload
    async def ask_device(self, device_alias: RemoteDeviceType, tag_name: str, **kwargs) -> RegisterValue: pass
    @overload
    async def ask_device(self, device_alias: RemoteDeviceType, *tag_names: str, **kwargs) -> Tuple[RegisterValue, ...]: pass
    async def ask_device(self, device_alias: RemoteDeviceType, *tag_names: str, **kwargs) -> Union[RegisterValue, Tuple[RegisterValue, ...]]:
        """
        Implementation that gets multiple register values for a remote device.

        Other Parameters
        ----------------
        unit    -   The unit ID of the device to query. Default is 1.
        """

        unit, client = kwargs.get("unit", 1), self.resolve_remote_connection(device_alias)
        tag_set = get_contiguous_tags(CommsUtils.identity, CommsUtils.identity,
            *(self.resolve_remote_tag(device_alias, tag_name) for tag_name in tag_names)
        )

        coil_results, register_results = await asyncio.gather(
            decode_coils(client, tag_set.coils, unit_id=unit),
            decode_registers(client, tag_set.holding_registers, unit_id=unit)
        )
        result = tuple(coil_results) + tuple(register_results)

        if len(result) == 1:
            return result[0]
        return result

    async def tell_device(self, device_alias: RemoteDeviceType, *tag_values: Tuple[str, RegisterValue], **kwargs) -> None:
        """
        Implementation that sets multiple register values for a remote device.

        Other Parameters
        ----------------
        unit    -   The unit ID of the device to query.
        """

        unit_id = kwargs.get("unit", 1)
        client = self.resolve_remote_connection(device_alias)
        if client is None:
            raise ValueError("{0}\tKey 'client' is none for {1}. Device mapping is: {2} => {3}".format(perf_counter(), type(self).__name__, device_alias, self.device_map[device_alias]))
        tag_set = get_contiguous_tags(CommsUtils.tuple_to_tag, CommsUtils.tag_to_tuple,
            *((self.resolve_remote_tag(device_alias, tag), value) for tag, value in tag_values)
        )
        # since builder does not support skipping bytes,
        # create a new PayloadBuilder each time a SkipTag
        # is encountered to send a new request for a different section
        all_tasks: List[Coroutine[Any, Any, None]] = []
        for tags, write_values in ((tag_set.coils, encode_coils), (tag_set.holding_registers, encode_registers)):
            start_index = 0
            for index, (tag, value) in enumerate(tags):
                if isinstance(tag, SkipTag):    # end of section; start over with new accumulator
                    all_tasks.append(write_values(client, tags[start_index:index], unit_id=unit_id))
                    start_index = index + 1
            if start_index < len(tags):
                all_tasks.append(write_values(client, tags[start_index:], unit_id=unit_id))
        await asyncio.gather(*all_tasks)


class CommsUtils:
    """
    Class for utility static functions that are 
    used in communicating between Modbus devices.
    Not meant for general use outside this file.
    """

    @staticmethod
    def identity(tag: Tag) -> Tag: return tag
    @staticmethod
    def tuple_to_tag(item: Tuple[Tag[T], RegisterValue]) -> Tag[T]: return item[0]
    @staticmethod
    def tag_to_tuple(tag: Tag[T]) -> Tuple[Tag[T], RegisterValue]: return (tag, 0)
