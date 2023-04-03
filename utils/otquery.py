from pymodbus.pdu import ExceptionResponse
from pymodbus.exceptions import ConnectionException
from pymodbus.mei_message import ReadDeviceInformationRequest, ReadDeviceInformationResponse
from pymodbus.client import ModbusTcpClient
from typing import Union
import argparse
import sys

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ip_port", type=str, help="The IP:Port address of the device to test.")
    parser.add_argument("--read-code", default=0x00, type=int, help="The read code of the device information request. (0 = basic, 1 = regular, 2 = extended, 3 = ")
    parser.add_argument("--timeout", default=0.5, type=float, help="The timeout. Default 0.5")

    args = parser.parse_args()
    host_port = args.ip_port
    if ':' not in host_port:
        host_port += ":502"
    host, port = host_port.split(":", 1)
    try:
        client = ModbusTcpClient(host, int(port), timeout=args.timeout)
        for oid in range(3):
            request = ReadDeviceInformationRequest(read_code=args.read_code, object_id=oid)
            response: Union[ExceptionResponse, ReadDeviceInformationResponse] = \
                client.execute(request) # type: ignore
            if isinstance(response, ExceptionResponse):
                break # device not supported (i.e. umodbus) but active
        print(f"Success: {host_port}")
    except:
        print(f"Failure: {host_port}")
        sys.exit(1)