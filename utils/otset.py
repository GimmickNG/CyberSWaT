import os
import sys
import asyncio
import argparse
sys.path.insert(1, os.path.realpath(os.path.join(__file__, "../../")))

from simulator.modbus import helpers
from simulator.modbus.tag import SkipTag, Tag
from simulator.modbus.types import RegisterValue
from simulator.modbus.compat.pymodbus_functions import encode_coils, encode_registers
from pymodbus.client import AsyncModbusTcpClient as AsyncModbusClient
from pymodbus.client.base import ModbusClientProtocol
from typing import Any, Coroutine, List, Tuple
from . import DEFAULT_PORT, gen_classlist

otset_parser = argparse.ArgumentParser("otset", description="Sets tag values for a given field device.")
otset_parser.add_argument("device", help="An IP:Port pair of the field device whose tags to modify.")
otset_parser.add_argument("class_name", help="The class name of the device.")
otset_parser.add_argument("tag_values", nargs="+", help="Pairs of name=value to set, e.g Hty=False. "
                                                        "Pass negative numbers by swapping the `-` for an `n`, e.g. n5.3 for -5.3.")
otset_parser.add_argument("--unit-id", "-u", type=int, default=1, help="The unit ID to query. Default 1")
args = otset_parser.parse_args()
class_list = gen_classlist()
unit = args.unit_id

def tag_to_tuple(x: Tag) -> Tuple[Tag, RegisterValue]:
    return (x, 0)

def tuple_to_tag(x: Tuple[Tag, RegisterValue]) -> Tag:
    return x[0]

async def tell_device(client: ModbusClientProtocol,
                      unit_id: int,
                      *tag_values: Tuple[Tag, RegisterValue],
                      **kwargs) -> None:
    """
    Implementation that sets multiple register values for a remote device.

    Other Parameters
    ----------------
    unit    -   The unit ID of the device to query.
    """

    tag_set = helpers.get_contiguous_tags(tuple_to_tag, tag_to_tuple, *tag_values)
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

def parse_value(tag: Tag, value: str) -> Any:
    dtype = tag.data_type
    lvalue = value.lower()
    if dtype == bool:
        if lvalue == "false":
            return False
        if lvalue == "true":
            return True
        return None
    if dtype == float:
        return float(lvalue)
    if dtype == int:
        return int(lvalue)
    return None

async def run_tasks(address, class_name, tag_values) -> bool:
    if ':' in address:
        ip, port = address.split(":")
    else:
        ip, port = address, DEFAULT_PORT
    client = AsyncModbusClient(host=ip, port=port, timeout=1, loop=asyncio.get_running_loop())
    await client.connect()
    
    if client.protocol is not None and class_name in class_list:
        device_class = class_list[class_name]
        tag_database = device_class.create_tag_database()
        parsed_tag_values: List[Tuple[Tag, RegisterValue]] = []
        for tag_value in tag_values:
            if '=' not in tag_value:
                continue
            tag, value = tag_value.split("=")
            tag_type = tag_database[tag]
            new_value = parse_value(tag_type, value)
            if new_value is not None:
                parsed_tag_values.append((tag_type, new_value))
        if len(parsed_tag_values):
            await tell_device(client.protocol, args.unit_id, *parsed_tag_values)
            return True
    return False

if asyncio.run(run_tasks(args.device, args.class_name, args.tag_values)):
    print("Successfully updated tags.")
