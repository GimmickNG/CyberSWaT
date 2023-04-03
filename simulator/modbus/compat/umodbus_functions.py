from umodbus.asynchronous.tcp import AsyncModbusTCP as ModbusTcpServer
from umodbus.asynchronous.tcp import AsyncTCP as ModbusClient # client is also the protocol
from typing import List, Tuple, cast
from ..types import ModbusRegisterData, RegisterValue
from ..tag import PayloadBuilder, PayloadDecoder, Tag

async def encode_coils(client: ModbusClient, tag_values: Tuple[Tuple[Tag[bool], bool], ...], unit_id: int = 0) -> None:
    if len(tag_values) == 0:
        return
    builder: PayloadBuilder = PayloadBuilder()
    for tag, value in tag_values:
        tag.encode_with(value, builder)
    await client.write_multiple_coils(unit_id, tag_values[0][0].offset, builder.to_coils())

async def decode_coils(client: ModbusClient, tags: Tuple[Tag[bool], ...], unit_id: int = 0) -> List[bool]:
    if len(tags) == 0:
        return []
    address, count = tags[0].offset, sum(tag.data_size for tag in tags)
    bits = await client.read_coils(unit_id, address, count)
    decoder: PayloadDecoder = PayloadDecoder.from_coils(bits)
    
    result: List[bool] = []
    for tag in tags:
        value = tag.decode_with(decoder)
        if value is not None:
            result.append(value)
    return result

async def encode_registers(client: ModbusClient, tag_values: Tuple[Tuple[Tag[RegisterValue], RegisterValue], ...], unit_id: int = 0) -> None:
    if len(tag_values) == 0:
        return
    builder: PayloadBuilder = PayloadBuilder()
    for tag, value in tag_values:
        tag.encode_with(value, builder)
    await client.write_multiple_registers(unit_id, tag_values[0][0].offset, builder.to_registers())

async def decode_registers(client: ModbusClient, tags: Tuple[Tag[RegisterValue], ...], unit_id: int = 0) -> List[RegisterValue]:
    if len(tags) == 0:
        return []
    address, count = tags[0].offset, sum(tag.data_size for tag in tags)
    registers: List[int] = await client.read_holding_registers(unit_id, address, count)
    decoder: PayloadDecoder = PayloadDecoder.from_registers(registers, True)
    results: List[RegisterValue] = []
    for tag in tags:
        value = tag.decode_with(decoder)
        if value is not None:
            results.append(value)
    return results

async def start_tcp_server(device, address: Tuple[str, int] = ('127.0.0.1', 5020), **kwargs) -> ModbusTcpServer:
    from .modbus import ModbusDeviceIdentification, ModbusServerContext
    from ..base import BaseModbusDevice

    device = cast(BaseModbusDevice, device)
    context: ModbusServerContext = device.data_store
    host, port = address

    server = ModbusTcpServer()
    server._register_dict = context[0]
    # TODO implement Modbus identification 
    identity: ModbusDeviceIdentification = device.identification
    await server.bind(local_ip=host, local_port=port, max_connections=kwargs.get("backlog", 20))
    return server