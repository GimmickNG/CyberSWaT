from pymodbus.pdu import ExceptionResponse
from pymodbus.bit_read_message import ReadCoilsResponse
from pymodbus.register_read_message import ReadRegistersResponseBase
from pymodbus.client.base import ModbusClientProtocol as ModbusClient
from typing import List, Tuple, Union, cast
from ..types import ModbusRegisterData, RegisterValue
from ..tag import PayloadBuilder, PayloadDecoder, Tag

async def encode_coils(client: ModbusClient, tag_values: Tuple[Tuple[Tag[bool], bool], ...], unit_id: int = 0) -> None:
    if len(tag_values) == 0:
        return
    builder: PayloadBuilder = PayloadBuilder()
    for tag, value in tag_values:
        tag.encode_with(value, builder)
    await client.write_coils(tag_values[0][0].offset, builder.to_coils(), slave=unit_id)

async def decode_coils(client: ModbusClient, tags: Tuple[Tag[bool], ...], unit_id: int = 0) -> List[bool]:
    if len(tags) == 0:
        return []
    #client, address, count, coils
    address, count = tags[0].offset, sum(tag.data_size for tag in tags)
    response: ReadCoilsResponse = await client.read_coils(address, count, slave=unit_id)
    if isinstance(response, ExceptionResponse):
        print("Coils Exception: ", address, count, client.params.host, client.params.port)
    decoder: PayloadDecoder = PayloadDecoder.from_coils(response.bits)
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
        tag.encode_with(value, builder) # calls builder.add_data_type to populate it
    await client.write_registers(tag_values[0][0].offset, values=builder.to_registers(), slave=unit_id)

async def decode_registers(client: ModbusClient, tags: Tuple[Tag[RegisterValue], ...], unit_id: int = 0) -> List[RegisterValue]:
    if len(tags) == 0:
        return []
    address, count = tags[0].offset, sum(tag.data_size for tag in tags)
    response: ReadRegistersResponseBase = await client.read_holding_registers(address, count, slave=unit_id)
    if isinstance(response, ExceptionResponse):
        print("Coils Exception: ", address, count, client.params.host, client.params.port)
    decoder: PayloadDecoder = PayloadDecoder.from_registers(response.registers, True)
    results: List[RegisterValue] = []
    for tag in tags:
        value = tag.decode_with(decoder)
        if value is not None:
            results.append(value)
    return results

async def start_tcp_server(device, address: Tuple[str, int] = ('127.0.0.1', 5020), **kwargs):
    from pymodbus.server import StartAsyncTcpServer
    from ..base import BaseModbusDevice

    device = cast(BaseModbusDevice, device)
    return await StartAsyncTcpServer(context=device.data_store, identity=device.identification, address=address, **kwargs)