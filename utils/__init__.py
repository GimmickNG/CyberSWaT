from typing import Any, Dict, Iterable, Literal, Set, Type, Union
from simulator.config.device_config import generate_make, walk_devices
from simulator.config.auxiliary_config import ExecutableNode
from simulator.modbus.base import BaseModbusDevice
from simulator.modbus.types import IPString
from mininet.log import setLogLevel, output, warning
from mininet.net import Mininet
from mininet.node import Node
from datetime import datetime
from typing import overload
import time

DEFAULT_PORT = 502
KNOWN_PORTS:Set[int] = { DEFAULT_PORT }

@overload 
def get_field_devices(net: Mininet, device_list, with_config:Literal[True]) -> \
    Dict[Union[Node, IPString, str], ExecutableNode]: pass 

@overload
def get_field_devices(net: Mininet, device_list, with_config:Literal[False] = False) -> \
    Set[Union[Node, IPString, str]]: pass

def get_field_devices(net: Mininet, device_list, with_config:bool=False) -> \
    Union[Set[Union[Node, IPString, str]], Dict[Union[Node, IPString, str], ExecutableNode]]:
    """
    Devices in this function are stored as either
    Nodes, strings, ip:port strings or name:port strings.
    
    For example: {<host AIT401>:<enode>}, (reason: #1, found in net) 
                 {"IOAIT401":<enode>}, (reason: #2, not found in net, device name)
                 {"192.168.1.1:5020":<enode>}, (reason: #3, ip:port pair)
                 {"AIT401:5020":<enode>}, (reason: #4, name:port pair with parent device name)
    """
    device_dict = {}
    for device in walk_devices(device_list):
        ip_addr, dname = device.get_ip(True), device.name
        if ':' in ip_addr:
            *ip, port = ip_addr.split(":")
            ip = ':'.join(ip)
        else:
            ip, port = ip_addr, DEFAULT_PORT

        if dname in net:# and device.has_args():
            device_dict[net.getNodeByName(device.name)] = device            #1
            device_dict[f"{dname}:{port}"] = device                         #4
        else:
            parent_ip = next((
                f"{parent.name}:{port}"
                for parent in device_dict
                if isinstance(parent, Node) and parent.IP() == ip
            ), None)
            if parent_ip is not None:
                device_dict[parent_ip] = device
        device_dict[ip_addr] = device                                       #3
        device_dict[dname] = device                                         #2
    if with_config:
        return device_dict
    return set(device_dict.keys())

def get_dir(dir_name) -> str:
    from os.path import abspath, join

    return abspath(join(__file__, dir_name))

def create_makefile(device_list, all_delay, io_delay, plc_delay, fbd_delay, scada_delay) -> int:
    start_time = all_delay + time.time()
    delay_args = f"--start-time {start_time} --io-delay {io_delay} --plc-delay {plc_delay} --fbd-delay {fbd_delay} --scada-delay {scada_delay}"
    with open(get_dir("../../simulator/Makefile"), 'w') as makefile:
        makefile.write(f"# Automatically generated by {__file__} \n")
        makefile.write('\n'.join(generate_make(device_list, xargs=delay_args)))
    return start_time

def ping_devices(net, runnable_devices: Iterable[Union[Any, Node]], **kwargs) -> None:
    host_set = {host for host in runnable_devices if isinstance(host, Node)}
    estimated_time = len(host_set) * (len(host_set)-1) / (45 * 60)
    verbose = kwargs.get("verbose", True)
    if verbose:
        output(f"{datetime.now()}: Attempting to ping devices... "
               f"(takes ~{estimated_time:.0f} minutes; press ^C to stop): ")
    timeout, ping_result = kwargs.get("timeout", 0.05), 0
    try:
        setLogLevel('warning')
        total_recv, ping_result = 0, net.pingFull(host_set, timeout=timeout)
        for src, dest, (_, recv, *_) in ping_result:
            total_recv += recv
            if recv != 1:
                warning(f"\nDropped {src} -> {dest}")
        ping_result = 100 * total_recv / (len(host_set) * (len(host_set)-1))
        setLogLevel('output')
        if verbose:
            output(f"\n{datetime.now()}: Completed. Results: {ping_result:.3f}%")
    except KeyboardInterrupt:
        return
    finally:
        setLogLevel('output')
        output("\n")

def start_device(dev: Node):
    out, err = open(f"logs/{dev.name}.log", 'a'), open(f"logs/{dev.name}.err", 'a')
    popen = dev.popen(['make', dev.name], cwd=get_dir("../../simulator"), stdout=out, stderr=err)
    return popen, out, err

def gen_classlist() -> Dict[str, Type[BaseModbusDevice]]:
    from simulator import io_plc, controlblock, swat, plc
    all_classes = [
        io_plc.DI_WIFI, io_plc.IO_AIN_FIT, io_plc.IO_MV, io_plc.IO_PMP_UV,
        io_plc.IO_SWITCH, io_plc.VSD, io_plc.VSD_In, io_plc.VSD_Out, 
        controlblock.AIN_FBD, controlblock.Duty2_FBD, controlblock.FIT_FBD,
        controlblock.MV_FBD, controlblock.PMP_FBD, controlblock.SWITCH_FBD,
        controlblock.UV_FBD, controlblock.VSD_FBD, swat.Plant, swat.LivePoller,
        plc.SCADA, plc.SCADAS1, plc.SCADAS2, plc.SCADAS3, plc.SCADAS4, plc.SCADAS5,
        plc.SCADAS6, plc.PLC1, plc.PLC2, plc.PLC3, plc.PLC4, plc.PLC5, plc.PLC6
    ]
    cls_dict: Dict[str, Type[BaseModbusDevice]] = {}
    for cls in all_classes:
        cls_dict[cls.__name__] = cls
    return cls_dict

__all__ = [
    "get_field_devices", "get_dir", "create_makefile",
    "gen_classlist", "ping_devices"
]

