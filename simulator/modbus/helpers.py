from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Type, Union, overload
from .compat.modbus import ModbusSlaveContext, ModbusServerContext, ModbusTcpServer
from .compat.modbus import ModbusDeviceIdentification, start_tcp_server
from .types.remote import ContiguousTagSet, RemoteDeviceType
from .compat.builtins import Event, abspath, sort, asyncio
from .tag import Tag, SkipTag, T
from .types import IPString
import argparse
import signal


def start_device(
    *devices: "BaseModbusDevice", _host: str="localhost", _port: int=5020, _backlog: int=20
) -> None:
    """
    Starts a Modbus device. Also starts a Modbus TCP server instance at
    the specified socket info (`(_host, _port)`).
    """

    from .base import BaseModbusDevice
    
    class ServerStarter:
        def __init__(self, *devices: BaseModbusDevice):
            self.devices: Tuple[BaseModbusDevice, ...] = devices
            self.tcp_server: Optional[ModbusTcpServer] = None
            loop = asyncio.get_event_loop()
            stop_device = lambda signame: asyncio.create_task(self.stop_device(signame))
            loop.add_signal_handler(signal.SIGTERM, stop_device)
            loop.add_signal_handler(signal.SIGINT, stop_device)
            self.tasks: List[Coroutine[Any, Any, Any]] = [
                device.start() for device in devices
            ]
            self.tasks.append(self.start_server())

        async def start_server(self):
            server: Optional[ModbusTcpServer] = await start_tcp_server(
                device=self.devices[0], address=(_host, _port), 
                defer_start=True, backlog=_backlog
            )
            if not server:
                raise RuntimeError("Error starting server at ({0}:{1})".format(
                    _host, _port
                ))
            self.tcp_server = server
            await server.serve_forever()

        async def stop_device(self, *args):
            for device in self.devices:
                device.exec_state.set()
            
            if self.tcp_server is not None:
                await self.tcp_server.server_close()
        
        async def run_tasks(self):
            await asyncio.gather(*self.tasks)

    try:
        asyncio.run(ServerStarter(*devices).run_tasks())
    except asyncio.CancelledError:
        pass

    # Warning: The way this is currently done, Pycopy does not support running multiple devices,
    # as there is a 1:1 mapping for servers:devices, and multithreading is unsupported. While it
    # is possible to refactor the BaseModbusDevice class so that 1 `run()` runs the callbacks for
    # all the devices, this is not done at the moment. As a workaround, the secondary devices can
    # be configured (manually) to have their _main_loop added as a callback to the primary Modbus
    # device's `recurring_calls` list, which will then execute it in sequence. However, it cannot
    # be done within `start_device()`, as this function has no knowledge of which devices will be
    # started before or after it has been called.

def create_identification(vname:str, pcode:str, vurl:str, pname:str, mname:str, revision:str) -> ModbusDeviceIdentification:
    identity = ModbusDeviceIdentification()
    identity.VendorName = vname
    identity.ProductCode = pcode
    identity.VendorUrl = vurl
    identity.ProductName = pname
    identity.ModelName = mname
    identity.MajorMinorRevision = revision
    
    return identity

def create_context() -> ModbusServerContext:
    return ModbusServerContext(slaves=ModbusSlaveContext(zero_mode=True))

def parse_negative_float(parse_item: str) -> float:
    if parse_item.startswith("n"):
        return -1 * float(parse_item[1:])
    return float(parse_item)

def parse_negative_int(parse_item: str) -> int:
    return int(parse_negative_float(parse_item))
    
def get_remote_ips(device_list: List[str]) -> Dict[RemoteDeviceType, IPString]:
    """
    Converts a list of strings, e.g.
    
    `'MV101', '192.168.0.1:5020', 'MV_FBD', 'MV201', '192.168.0.17', 'MV_FBD'`
    
    to a dictionary of {name: ip}, e.g.:
    
    `{
        'MV101': '192.168.0.1:5020',
        'MV201': '192.168.0.17'
    }`
    """

    # take two steps at a time; generate pair by staggering second by 1 step
    # ensure type is list, as Pycopy does not support multiple step slicing
    # for tuples
    device_list = list(device_list)
    return {
        RemoteDeviceType(alias): IPString(ip) for alias, ip in zip(
            device_list[0::2], device_list[1::2]
        )
    }
    
def create_full_parser(parser_desc: str, **kwargs) -> argparse.ArgumentParser:
    from . import TIME_INTERVAL
    parser = argparse.ArgumentParser(description=parser_desc, **kwargs)
    parser.add_argument("--device-name", default="", type=str, help="The device name. Optional; only used in debugging, to identify devices.")
    parser.add_argument("--host", "-s", default="127.0.0.1", type=str, help="The server host. Default is localhost (127.0.0.1)")
    parser.add_argument("--port", "-p", default=502, type=int, help="The server port. Default is the well-known Modbus port 502.")
    parser.add_argument("--remote-devices", "-r", default=(), nargs='+', help="A list of remote devices in the format [[ALIAS IP[:PORT]] ], e.g. MV101 192.168.0.1:5020. If no port is provided, the default well-known Modbus port 502 is used.")
    parser.add_argument("--debug", "-x", action="store_true", help="Turns on debug mode, the effects of which are dependent on the device. Most usually involves an increase in logging, although certain devices can behave differently. For example, FBDs can start without needing an external signal when in debug mode.")
    parser.add_argument("--io-delay", "-d", default=0, type=float, help="How long to wait (in s) before starting each I/O device in the OT network. Mainly used to ensure all device runners have finished parsing and are ready to run.")
    parser.add_argument("--plc-delay", "-y", default=0, type=float, help="How long to wait (in s) before starting each PLC in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    parser.add_argument("--scada-delay", default=0, type=float, help="How long to wait (in s) before starting each SCADA stage in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    parser.add_argument("--fbd-delay", "-z", default=0, type=float, help="How long to wait (in s) before starting each FBD in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    parser.add_argument("--start-time", default=0, type=float, help="The time at which to start at.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--interval", "-v", default=TIME_INTERVAL, type=float, help="Time period (1/f) of this device. Default: 0.005 s (200Hz)")
    group.add_argument("--frequency", "-f", dest='interval', type=lambda x: 1/float(x), help="Frequency of device in Hz. Default 200 Hz (0.005 s)")
    return parser

def create_micro_parser() -> argparse.ArgumentParser:
    from . import TIME_INTERVAL
    parser = argparse.ArgumentParser(description="Pycopy-based I/O device runner")
    parser.add_argument("device", "-b", default="io", type=str.lower, choices={"io", "fbd"}, help="Base type, for compatibility with device_runner. Specify 'io' or 'fbd' - other devices are not written for pycopy.")
    parser.add_argument("type", "-t", type=str.lower, choices={'mv', 'pmp', 'switch', 'ain', 'fit', 'vsd', 'vsd_in', 'vsd_out'}, help="The I/O device type. Acceptable values are {mv,pmp,switch,ain,fit,vsd,vsd_in,vsd_out}")
    parser.add_argument("--device-name", default="", type=str, help="The device name. Optional; only used in debugging, to identify devices.")
    parser.add_argument("--debug", "-x", action="store_true", help="Turns on debug mode, the effects of which are dependent on the device. Most usually involves an increase in logging, although certain devices can behave differently. For example, FBDs can start without needing an external signal when in debug mode.")
    parser.add_argument("--remote-devices", "-r", default=(), nargs='+', help="\tA list of remote devices in the format [[ALIAS IP[:PORT]] ], e.g. MV101 192.168.0.1:5020. If no port is provided, the default well-known Modbus port 502 is used.")
    parser.add_argument("--interval", "-v", default=TIME_INTERVAL, type=float, help="\t\tTime period (1/f) of this device. Default: 0.005 s (200Hz)")
    parser.add_argument("--host", "-s", default="127.0.0.1", type=str, help="\t\t\tThe server host. Default is localhost (127.0.0.1)")
    parser.add_argument("--port", "-p", default=502, type=int, help="\t\t\tThe server port. Default is the well-known Modbus port 502.")
    parser.add_argument("--io-delay", "-d", default=0, type=float, help="How long to wait (in s) before starting each I/O device in the OT network. Mainly used to ensure all device runners have finished parsing and are ready to run.")
    parser.add_argument("--plc-delay", "-y", default=0, type=float, help="How long to wait (in s) before starting each PLC in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    parser.add_argument("--fbd-delay", "-z", default=0, type=float, help="How long to wait (in s) before starting each FBD in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    parser.add_argument("--scada-delay", default=0, type=float, help="How long to wait (in s) before starting each SCADA stage in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    parser.add_argument("--start-time", default=0, type=float, help="The time at which to start at.")
    return parser
    
def get_contiguous_tags(key: Callable[[T], Tag], inverse_key: Callable[[Tag], T], *tag_data: T) -> ContiguousTagSet[T]:
    coils: List[T] = []
    holding_registers: List[T] = []
    for item in sort(tag_data, key=lambda x: key(x).offset):
        tag = key(item)
        if tag.storage_location == Tag.COILS:
            coils.append(item)
        elif tag.storage_location == Tag.HOLDING_REGISTERS:
            holding_registers.append(item)

    hr_results: List[T] = []
    coil_results: List[T] = []
    for tag_set, result in ((coils, coil_results), (holding_registers, hr_results)):
        if not len(tag_set):
            continue
        result.append(tag_set[0])
        for first_item, next_item in zip(tag_set[:-1], tag_set[1:]):
            first_registers, next_registers = (
                key(i).resolve_registers() for i in (first_item, next_item)
            )
            if first_registers.end < next_registers.start:
                result.append(inverse_key(SkipTag(first_registers.end, next_registers.start)))
            elif first_registers.end > next_registers.start:
                raise ValueError("End of first register must be less than start " 
                                 "address of second register, but received ({0} > {1})"
                                 .format(first_item, next_item))
            result.append(next_item)
    return ContiguousTagSet(tuple(coil_results), tuple(hr_results))

def pack_tags(*tags: Tag) -> Dict[str, Tag]:
    """
    Gets a list of tags and builds a packed dictionary of tags
    and corresponding register values based on the supplied sizes.
    """

    # tags sorted by increasing order of starting offset
    coils: List[Tag] = []
    holding_registers: List[Tag] = []
    for tag in tags:
        if tag.storage_location == Tag.COILS:
            coils.append(tag)
        elif tag.storage_location == Tag.HOLDING_REGISTERS:
            holding_registers.append(tag)

    get_offset = lambda tag: tag.offset
    coils = sort(coils, key=get_offset)
    holding_registers = sort(holding_registers, key=get_offset)
    for increasing_offsets in (coils, holding_registers):    
        for i, (first_tag, next_tag) in enumerate(zip(increasing_offsets[:-1], increasing_offsets[1:])):
            if i == 0:
                first_tag.offset = 0    # reset for each memory location as offsets are based on location
            first_registers, next_start = first_tag.resolve_registers(), next_tag.resolve_registers().start
            if first_registers.end > next_start:
                # first ending register overlaps with second starting register; move
                # second starting register up to end of first tag's ending register.
                next_tag.offset = first_registers.end
    return { tag.name: tag for tag in tags }

def get_standalone_tags(tags: Tuple[Tag, ...]) -> Dict[str, Tag]:
    """
    Travels up the inheritance chain to get tags of the superclasses where possible.
    This is primarily used to get tags of devices for whom there is no direct object
    reference available, e.g. when calling the static `get_tags()` method to get the
    tags for a device.
    """

    return pack_tags(*tags)

def create_contiguous_states(start, stop, states):
    """
    Creates a contiguous state dict where undefined states are
    replaced with the last encountered state. That is, if the
    state dict looks like:
    
    `{ 1: <state>, 2: <state>, 5: <state>, 8: <state> }`

    then states (3, 4) will be identical to state 2, and states
    (6, 7) will be identical to state 5.
    """

    # duplicate states are continuous, i.e. state 3 == 4 == 5
    # gaps in states resolve to lowest existing state
    state_dict = {}
    last_found_key = start
    for key in range(start, stop):
        if key in states:
            last_found_key = key
        state_dict[key] = states[last_found_key]
    return state_dict

def split_tags_on_empty(array: List[Tag]) -> List[List[Tag]]:
    sub_arrays, start_point = [], 0
    for i, tag in enumerate(array):
        if isinstance(tag, SkipTag):
            sub_arrays.append(array[start_point:i])
            start_point = i + 1
    if start_point < len(array):
        sub_arrays.append(array[start_point:])
    return sub_arrays
