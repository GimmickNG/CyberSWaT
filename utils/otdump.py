import os
import sys
import json
import asyncio
import argparse
sys.path.insert(1, os.path.realpath(os.path.join(__file__, "../../")))

from simulator.modbus import helpers
from simulator.modbus.base import BaseModbusDevice
from simulator.modbus.compat.pymodbus_functions import decode_coils, decode_registers
from simulator.modbus.tag import SkipTag, Tag
from simulator.modbus.types.remote import ContiguousTagSet
from simulator.modbus.types import RegisterValue
from pymodbus.client import AsyncModbusTcpClient as AsyncModbusClient
from pymodbus.client.base import ModbusBaseClient
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from . import DEFAULT_PORT, gen_classlist

DeviceTagInfo = Dict[Tag, Union[str, RegisterValue]]

async def connect(ip: str, port: int, timeout: float = 1) -> Optional[ModbusBaseClient]:
    client = AsyncModbusClient(host=ip, port=port, timeout=timeout, loop=asyncio.get_running_loop())
    await client.connect()
    if client.protocol is None:
        await client.close()
        return None
    return client.protocol

async def read_tags(
    client: ModbusBaseClient,
    tag_set: ContiguousTagSet,
) -> Optional[Tuple[List[bool], List[RegisterValue]]]:
    return await asyncio.gather(
        decode_coils(client, tag_set.coils, unit_id=unit),
        decode_registers(client, tag_set.holding_registers, unit_id=unit)
    )

otdump_parser = argparse.ArgumentParser("otdump", description="Prints operational info (e.g. tags) about running devices in the OT network.")
otdump_parser.add_argument("devices", nargs='+', help="A triplet of (device name, class name, ip:port) for the devices to print info about.\n"
                                                      "Each device must be running to show its tag values.")
otdump_parser.add_argument("--unit-id", "-u", type=int, default=1, help="The unit ID to query. Default 1")
otdump_parser.add_argument("--timeout", "-t", type=float, default=1, help="The request timeout. Default 1")
args = otdump_parser.parse_args()
class_list = gen_classlist()
unit = args.unit_id

def identity_fn(x: Tag) -> Tag:
    return x

async def poll_devices(host: str, class_name: str, ip_port: str, timeout: float = 1) -> \
    Dict[str, Dict[str, Union[str, int, DeviceTagInfo]]]:
    if class_name not in class_list:
        return {}
    device_class = class_list[class_name]
    tag_values: DeviceTagInfo = {}
    tag_database = device_class.create_tag_database()
    remaining_tags = list(tag_database.values())
    for tag in tag_database.values():
        tag_values[tag] = "?"
    if ':' in ip_port:
        ip, port = ip_port.split(":")
    else:
        ip, port = ip_port, DEFAULT_PORT
    client = await connect(ip, int(port), timeout)
    while client is not None and len(remaining_tags):
        # breaks up excess tags into multiple requests
        tag_set = helpers.get_contiguous_tags(identity_fn, identity_fn, *remaining_tags)
        remaining_tags = []
        while len(tag_set.holding_registers):
            start_register = tag_set.holding_registers[0].resolve_registers()[0]
            end_register = tag_set.holding_registers[-1].resolve_registers()[-1]
            if (end_register - start_register) <= 123: #123 = max number of registers allowed
                break
            if not isinstance(tag_set.holding_registers[-1], SkipTag):
                remaining_tags.insert(0, tag_set.holding_registers[-1])
            tag_set.holding_registers = tag_set.holding_registers[:-1]
        while len(tag_set.coils):
            start_coil, end_coil = (tag_set.coils[i].resolve_registers()[i] for i in [0, -1])
            if(end_coil - start_coil) <= 2000: #2000 = max number of coils allowed
                break
            if not isinstance(tag_set.coils[-1], SkipTag):
                remaining_tags.insert(0, tag_set.coils[-1])
            tag_set.coils = tag_set.coils[:-1]

        #uncomment if using only Pymodbus, or when LSB/MSB issue for micropython-modbus is fixed
        #coil_results = await decode_coils(client, tag_set.coils, unit_id=unit)
        #register_results = await decode_registers(client, tag_set.holding_registers, unit_id=unit)
        if True: #coil_results is not None:
            for coil_tag in tag_set.coils: #, coil_value in zip(tag_set.coils, coil_results):
                if not isinstance(coil_tag, SkipTag):
                    try:
                        coil_result = await decode_coils(client, (coil_tag,), unit_id=unit)
                        tag_values[coil_tag] = coil_result[0]
                    except:
                        pass
        if True: #register_results is not None:
            for register_tag in tag_set.holding_registers: #, register_value in zip(tag_set.holding_registers, register_results):
                if not isinstance(register_tag, SkipTag):
                    try:
                        register_result = await decode_registers(client, (register_tag,), unit_id=unit)
                        tag_values[register_tag] = register_result[0]
                    except:
                        pass
    return {
        host: {
            "name": device_class.__name__,
            "tags": tag_values,
            "port": port,
            "ip": ip
        }
    }


async def run_tasks(devices):
    return await asyncio.gather(*(
        poll_devices(host, class_name, ip_port, timeout=args.timeout)
        for host, class_name, ip_port in zip(devices[0::3], devices[1::3], devices[2::3])
    ))

all_dicts = asyncio.run(run_tasks(args.devices))
device_tags: Dict[str, Dict[str, Union[str, int, DeviceTagInfo]]] = {}
for dict_obj in all_dicts:
    device_tags.update(dict_obj)

if len(device_tags):
    device_info = {
        host: {
            "device_type": info["name"],
            "ip": info["ip"],
            "port": info["port"],
            "tags": [
                {
                    "name": tag.name,
                    "value": value,
                    "dtype": tag.data_type.__name__,
                    "registers": {
                        "start": tag.offset,
                        "length": tag.data_size,
                        "end": tag.offset + tag.data_size
                    },
                    "storage_location": tag.storage_location
                }
                for tag, value in info["tags"].items()
            ]
        }
        for host, info in device_tags.items()
    }
    #remote_tags might need parsing args/remote_devices in config
    #to get full information
    #remote_tags = device_class.get_device_classes()
    print(json.dumps(device_info))
    #TODO it is not possible to have 'skipped' offsets of NoneType in a sparse data block
    #either define it as a normal (dense) datablock or pack tags tightly instead of specifying
    #offsets