from typing import Dict, List, Tuple, Type
from modbus.base import BaseModbusDevice
from modbus.types import IPString
from random import getrandbits
from controlblock import *
from simulator.plc import plc0
from swat import Plant
import plc
import io_plc
import ipaddress as ipy

host_port = Tuple[ipy.IPv4Address, int]

def f2cmd(num):
    if num < 0:
        return "n{0}".format(-num)
    return "{0}".format(num)


class ExecutableNode:
    def __init__(self, ip, cmd_args, **kwargs):
        self.ip = ip
        self.cmd_args = cmd_args
        self._supports_micro = kwargs.get("supports_micro", False)
        self.devices: List[ExecutableNode] = kwargs.get("devices", [])
        self.name: str = kwargs.get("name", "").upper()
        self.remote_devices: Dict[str, IPString] = kwargs.get("remote_devices", {})
        self.classname: Type = kwargs.get("classname", None)

    def has_args(self) -> bool:
        return len(self.cmd_args) > 0

    def get_args(self) -> str:
        args = [str(i) for i in self.cmd_args]
        if len(self.remote_devices):
            args += ["--remote-devices", ' '.join(' '.join(arg) for arg in self.remote_devices.items())]
        if len(args):
            args += [f"--device-name {self.name}"]
        return ' '.join(args)

    def get_short_name(self) -> str:
        name: str = self.get_name()
        if len(name) > 10:
            return (name[:3]+name[-7:])
        return name
    
    def supports_micro(self) -> bool:
        return self._supports_micro

    def get_name(self) -> str:
        return self.name

    def get_ip(self, with_port=False) -> IPString:
        ip = self.ip
        if isinstance(self.ip, tuple):
            ip, *_ = self.ip
            if with_port:
                ip = "{0}:{1}".format(*self.ip)
        return IPString(str(ip))

    def get_devices(self):
        return self.devices
    
    def get_class(self) -> Type[BaseModbusDevice]:
        return self.classname


class Router(ExecutableNode):
    def __init__(self, ip: host_port, *devices: ExecutableNode, **kwargs):
        if "name" not in kwargs:
            kwargs["name"] = "rtr" + hex(getrandbits(20))[2:]
        super().__init__(ip, kwargs.pop("cmd_args", ()), devices=devices, **kwargs)

class IODevice(ExecutableNode):
    def __init__(self, ip: Tuple[str, int], base_class, cmd_args:Tuple[str, ...]=(), connected: bool = False, **kwargs):
        args = ("--host", ip[0], "--port", ip[1])
        conn_tup = ("--connected",) if connected else ()
        supports_micro = kwargs.pop("supports_micro", True)
        super().__init__(ip, ("io", base_class) + cmd_args + args + conn_tup, devices=[], supports_micro=supports_micro, **kwargs)

class Device(ExecutableNode):
    def __init__(self, ip: host_port, cmd_args=(), devices=(), **kwargs):
        super().__init__(ip, cmd_args + ("--host", ip[0], "--port", ip[1]), devices=devices, **kwargs)
        
        # monkey patches the get_name methods of the I/O devices 
        # that this Device owns, appending this Device's name to
        # it for uniquely identifying the I/O device owned by it
        for dev in devices:
            if isinstance(dev, IODevice):
                dev.name = "IO{0}".format(self.get_name().upper())

#####
class PlantNode(Router):
    def __init__(self, ip: host_port, targets=[], devices=[], **kwargs):
        remote_devices: Dict[str, IPString] = {target.get_short_name(): target.get_ip(with_port=True) for target in targets}
        super().__init__(
            ip, *devices, name=kwargs.pop("name", "plant"),
            cmd_args=("plant", "--host", ip[0], "--port", ip[1]), remote_devices=remote_devices,
            classname=Plant, **kwargs)
#####
class FBD(Device):
    def __init__(self, ip: host_port, base_class, cmd_args=(), devices=(), **kwargs):
        supports_micro = kwargs.pop("supports_micro", True)
        super().__init__(
            ip, ("fbd", base_class) + cmd_args, devices,
            supports_micro=supports_micro, **kwargs
        )
class PLC(Device):
    PLC1, PLC2, PLC3, PLC4, PLC5, PLC6 = range(1, 7)
    _CLASSES = [plc.PLC1, plc.PLC2, plc.PLC3, plc.PLC4, plc.PLC5, plc.PLC6]
    def __init__(self, name: str, ip: host_port, plc_class: int, fbds: List[ExecutableNode]):
        super().__init__(
            ip, ("plc", plc_class), fbds, 
            remote_devices={
                fbd.get_short_name(): fbd.get_ip(with_port=True)
                for fbd in fbds
            }, classname=PLC._CLASSES[plc_class - 1], name=name)

class SCADA(Device):
    MAINSCADA, SCADAS1, SCADAS2, SCADAS3, SCADAS4, SCADAS5, SCADAS6 = range(0, 7)
    _CLASSES = [plc.SCADA, plc.SCADAS1, plc.SCADAS2, plc.SCADAS3, plc.SCADAS4, plc.SCADAS5, plc.SCADAS6]
    def __init__(self, name: str, ip: host_port, scada_class: int, targets: List[ExecutableNode]):
        self.scada_class = scada_class
        super().__init__(
            ip, ("scada", scada_class), remote_devices={
                dev.get_short_name(): dev.get_ip(with_port=True)
                for dev in targets
            }, classname=SCADA._CLASSES[scada_class], name=name)
        self.devices = targets
#####
class IO_PMP(IODevice):
    def __init__(self, ip, connected: bool = False):
        super().__init__(ip, "pmp", classname=io_plc.IO_PMP_UV, connected=connected)
class PUMP(FBD):
    def __init__(self, name: str, ip, io:IO_PMP):
        super().__init__(
            ip, "pmp", ("--Start-TM", "3", "--Stop-TM", "3"), (io,), name=name,
            remote_devices={"IO": io.get_ip(with_port=True)},
            classname=PMP_FBD
        )
class UV_PUMP(FBD):
    def __init__(self, name: str, ip, io:IO_PMP):
        super().__init__(
            ip, "uv", (), (io,), name=name, 
            remote_devices={"IO": io.get_ip(with_port=True)},
            classname=UV_FBD
        )
#####
class IO_MV(IODevice):
    def __init__(self, ip, connected: bool = False):
        super().__init__(ip, "mv", classname=io_plc.IO_MV, connected=connected)
class MOTORISED_VALVE(FBD):
    def __init__(self, name: str, ip, io:IO_MV, Open_TM=15, Close_TM=15):
        super().__init__(
            ip, "mv", ("--Open-TM", Open_TM, "--Close-TM", Close_TM),
            (io,), name=name, remote_devices={"IO": io.get_ip(with_port=True)},
            classname=MV_FBD
        )
#####
class DUTY2(FBD):
    def __init__(self, name: str, ip):
        super().__init__(ip, "duty", (), (), classname=Duty2_FBD, name=name)
#####
class IO_AIN_FIT(IODevice):
    def __init__(self, ip):
        super().__init__(ip, "ain", classname=io_plc.IO_AIN_FIT)
class LEVEL_TRANSMITTER(FBD):
    def __init__(self, name: str, ip, io:IO_AIN_FIT, L_Raw_RIO, HEU, LEU):
        super().__init__(
            ip, "ain", ("--L-Raw-RIO", f2cmd(L_Raw_RIO), "--HEU", f2cmd(HEU), "--LEU", f2cmd(LEU)), 
            (io,), name=name, remote_devices={"IO": io.get_ip(with_port=True)},
            classname=AIN_FBD
        )
class FLOW_TRANSMITTER(FBD):
    def __init__(self, name: str, ip, io:IO_AIN_FIT, L_Raw_RIO, HEU, LEU):
        super().__init__(
            ip, "fit", ("--L-Raw-RIO", f2cmd(L_Raw_RIO), "--HEU", f2cmd(HEU), "--LEU", f2cmd(LEU)),
            (io,), name=name, remote_devices={"IO": io.get_ip(with_port=True)},
            classname=FIT_FBD#, supports_micro=False
        )
#####
class IO_SWITCH(IODevice):
    def __init__(self, ip):
        super().__init__(ip, "switch", classname=io_plc.IO_SWITCH)
class SWITCH(FBD):
    def __init__(self, name: str, ip, io:IO_SWITCH):
        super().__init__(
            ip, "switch", (), (io,), name=name,
            remote_devices={"IO": io.get_ip(with_port=True)},
            classname=SWITCH_FBD
        )
#####
class IO_VSD_In(IODevice):
    def __init__(self, ip):
        super().__init__(ip, "vsd_in", classname=io_plc.VSD_In)
class IO_VSD(IODevice):
    def __init__(self, ip):
        super().__init__(ip, "vsd", classname=io_plc.VSD)
class IO_VSD_Out(IODevice):
    def __init__(self, ip, vsd: IO_VSD, connected: bool = False):
        super().__init__(
            ip, "vsd_out", (), remote_devices={
                "P50X": vsd.get_ip(with_port=True)
            }, classname=io_plc.VSD_Out, connected=connected
        )

class VARIABLE_SPEED_DRIVE(FBD):
    def __init__(self, name:str, ip, vsd_in:IO_VSD_In, vsd_out:IO_VSD_Out, vsd:IO_VSD):
        super().__init__(
            ip, "vsd", (), (vsd, vsd_in, vsd_out), name=name, remote_devices={
                "VSD": vsd.get_ip(with_port=True),
                "VSD_In": vsd_in.get_ip(with_port=True),
                "VSD_Out": vsd_out.get_ip(with_port=True)
            }, classname=VSD_FBD
        )

        # special case since vsd has multiple IO devices
        vsd.name = "IO{0}".format(self.get_name().upper())
        vsd_in.name = "IO{0}I".format(self.get_name().upper())
        vsd_out.name = "IO{0}O".format(self.get_name().upper())

#####
