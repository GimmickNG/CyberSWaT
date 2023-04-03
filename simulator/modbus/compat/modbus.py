from . import IS_PYCOPY

if IS_PYCOPY:
    from umodbus.asynchronous.tcp import AsyncModbusTCP as ModbusTcpServer
    from umodbus.asynchronous.tcp import AsyncTCP as ModbusClient # client is also the protocol
    def AsyncModbusClient(host, port, timeout):
        return ModbusClient(slave_ip=host, slave_port=port, timeout=timeout) 
    from .modbus_structs import ModbusServerContext, ModbusSlaveContext
    from .modbus_structs import ModbusDeviceIdentification, ModbusSparseDataBlock
    from .umodbus_functions import encode_coils, decode_coils, encode_registers, decode_registers
    from .umodbus_functions import start_tcp_server
else:
    from pymodbus.server.async_io import ModbusTcpServer
    from pymodbus.datastore import ModbusSparseDataBlock
    from pymodbus.device import ModbusDeviceIdentification
    from pymodbus.client import AsyncModbusTcpClient as AsyncModbusClient
    from pymodbus.client.base import ModbusClientProtocol as ModbusClient
    from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext
    from .pymodbus_functions import encode_coils, decode_coils, encode_registers, decode_registers
    from .pymodbus_functions import start_tcp_server
    
__all__ = [
    "ModbusServerContext", "ModbusSlaveContext", "ModbusDeviceIdentification",
    "ModbusSparseDataBlock", "ModbusClient", "encode_coils", "decode_coils",
    "AsyncModbusClient", "encode_registers", "decode_registers",
    "start_tcp_server", "ModbusTcpServer"
]