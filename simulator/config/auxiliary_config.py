# TODO clean up the classes in this file
from typing import Callable, Dict, Iterator, List, Tuple, TypedDict, Union
from contextlib import contextmanager
from .device_defs import *
import ipaddress as ipy
import configparser
import os

def get_path(path: str) -> str:
    from os.path import abspath, join
    return abspath(join(__file__, path))

PYCOPY_PATH = get_path('../../../pycopy')
DEVICE_RUNNER = get_path("../../device_runner.py")
MICRO_IO_RUNNER = PYCOPY_PATH + ' ' + get_path("../../uio_runner.py")
MICRO_FBD_RUNNER = PYCOPY_PATH + ' ' + get_path("../../ufbd_runner.py")

class NetConfig:
    def __init__(self, starting_network: Union[Iterator[ipy.IPv4Network], List[ipy.IPv4Network]]):
        self.position = 0
        self._cached_an: List[ipy.IPv4Network] = list(starting_network)
        self.current_network = self.get_current_network()
        self.netsize = self.current_network.prefixlen
        self._last_port = self._last_parent_port = 502 #modbus well-known port
        self.local = ipy.IPv4Address("127.0.0.1")
        self._hosts = None

    def get_current_network(self):
        return self._cached_an[self.position]

    def get_next_network(self):
        self.position += 1
        return self.get_current_network()
    
    def get_remaining_networks(self) -> List[ipy.IPv4Network]:
        return self._cached_an[self.position:]

    def get_next_host(self) -> ipy.IPv4Address:
        if self._hosts is None:
            self._hosts = self.current_network.hosts()
        
        return next(self._hosts)

    def next(self, parent=False) -> host_port:
        host = self.get_next_host()
        if parent:
            self._last_parent = host
            self._last_parent_port = 502
            return self.of_parent
        else:
            self._last_host = host
            self._last_port = 502
            return self.same

    def next_port(self, of_parent=False) -> host_port:
        if of_parent:
            if self._last_parent_port == 502:
                self._last_parent_port = 5019
            self._last_parent_port += 1
            return self.of_parent
        else:
            if self._last_port == 502:
                self._last_port = 5019
            self._last_port += 1
            return self.same

    @property
    def of_parent(self) -> host_port:
        return (self._last_parent, self._last_parent_port)

    @property
    def same(self) -> host_port:
        return (self._last_host, self._last_port)

    @contextmanager
    def next_net(self):
        yield self
        del self._last_parent
        self.current_network, self._hosts = self.get_next_network(), None

    @contextmanager
    def next_subnet(self):
        def get_supernet_subnets(config: NetConfig, new_prefix: int) -> Iterator[ipy.IPv4Network]:
            subnets = list(
                ipy.collapse_addresses(config.get_remaining_networks())
            )[-1].subnets(new_prefix=new_prefix)
            lst_s = list(subnets)
            return iter(lst_s)
            
        new_config = NetConfig(get_supernet_subnets(self, self.netsize + 1))
        yield new_config
        self._cached_an, self.position = list(get_supernet_subnets(new_config, self.netsize)), 0

    @staticmethod
    def one_net(subnets:List[ipy.IPv4Network]):
        """
        Get the one IP network that covers all subnets in input,
        or None is subnets are disjoint.
        """
        if len(subnets) == 0:
            return None

        minlen = min([net.prefixlen for net in subnets])
        while subnets.count(subnets[0]) < len(subnets) and minlen > 0:
            # all subnets are not (yet) equal
            subnets = [net.supernet(new_prefix=minlen) for net in subnets]
            minlen -= 1

        # 0.0.0.0/? -> no common subnet
        if subnets[0].network_address != ipy.IPv4Address('0.0.0.0'):
            return subnets[0]

class Scenario:
    scenario_type = Callable[[NetConfig], host_port]
    scenario_callback = Tuple[scenario_type, scenario_type, scenario_type]

    def __init__(self, callable: Callable[[], scenario_callback], micro_mode: bool = True):
        self.type = callable
        self.use_micro = micro_mode
    
    def __call__(self) -> scenario_callback:
        return self.type()

    @staticmethod
    def get_default() -> Tuple[Callable[[], scenario_callback], bool]:
        """Returns the arguments for the default Scenario."""
        
        confpath = os.path.realpath(os.path.join(__file__, "../scenario.ini"))
        all_scenarios = Scenario.get_available()
        parser = configparser.ConfigParser()
        parser.read(confpath)
        
        scenario_id = parser.getint('default', 'scenario', fallback=0)
        micro_mode = parser.getboolean('default', 'micro_mode', fallback=True)
        return all_scenarios[scenario_id], micro_mode

    @staticmethod
    def get_available() -> Tuple[Callable[[], scenario_callback], ...]:
        return (Scenario.is_fip, Scenario.ps_iif, Scenario.ifps, Scenario.ifip, Scenario.monolithic)

    @staticmethod
    def is_fip() -> scenario_callback:
        """
        Returns setup functions for the scenario where the FBDs are located in 
        each PLC, and the I/O devices are located in their own node.
        (Mnemonic: [I]O [S]ingle, [F]BD [i]n [P]LC)
        """

        def get_plc_ip(hosts: NetConfig) -> host_port:
            return hosts.next(parent=True)
        def get_fbd_ip(hosts: NetConfig) -> host_port:
            return hosts.next_port(of_parent=True)
        def get_io_ip(hosts: NetConfig) -> host_port:
            return hosts.next()

        return get_plc_ip, get_fbd_ip, get_io_ip

    @staticmethod
    def ps_iif() -> scenario_callback:
        """
        Returns setup functions for the scenario where the FBDs are located
        in their own node, and the I/O devices are located on the same node
        as the FBDs. (Mnemonic: [P]LC [S]ingle, [I]O [i]n [F]BD)
        """

        def get_plc_ip(hosts: NetConfig) -> host_port:
            return hosts.next(parent=True)
        def get_fbd_ip(hosts: NetConfig) -> host_port:
            return hosts.next()
        def get_io_ip(hosts: NetConfig) -> host_port:
            return hosts.next_port()

        return get_plc_ip, get_fbd_ip, get_io_ip

    @staticmethod
    def ifps() -> scenario_callback:
        """
        Returns setup functions for the scenario where the FBDs are located in
        their own node, and the I/O devices are located in their own separate
        node. (Mnemonic: [I]O, [F]BD, [P]LC [S]ingle)
        """

        def get_plc_ip(hosts: NetConfig) -> host_port:
            return hosts.next(parent=True)
        def get_fbd_ip(hosts: NetConfig) -> host_port:
            return hosts.next()
        def get_io_ip(hosts: NetConfig) -> host_port:
            return hosts.next()

        return get_plc_ip, get_fbd_ip, get_io_ip

    @staticmethod
    def ifip() -> scenario_callback:
        """
        Returns setup functions for the scenario where the FBDs and the I/O
        devices are located on the same node. (Mnemonic: [I]O, [F]BD [i]n [P]LC)
        """

        def get_plc_ip(hosts: NetConfig) -> host_port:
            return hosts.next(parent=True)
        def get_fbd_ip(hosts: NetConfig) -> host_port:
            return hosts.next_port()
        def get_io_ip(hosts: NetConfig) -> host_port:
            return hosts.next_port()

        return get_plc_ip, get_fbd_ip, get_io_ip

    @staticmethod
    def monolithic() -> scenario_callback:
        """
        Returns setup functions for the scenario where all the PLCs, the FBDs
        and I/O devices are located on the same node.
        """

        def get_next_port(hosts: NetConfig) -> host_port:
            return hosts.next_port()
        
        return (get_next_port,) * 3

class DeviceMapping(TypedDict):
    name: str
    args: List[str]
