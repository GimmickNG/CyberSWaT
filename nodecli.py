import os
import re
import sys
import time
import tqdm
import json
import shlex
import utils
import argparse
import configparser
from topo import ICSTopo
from base_cli import NewCLI
from cmd2 import Cmd2ArgumentParser, with_argparser
from mininet.net import Mininet
from mininet.node import Node
from mininet.link import Link
from mininet.log import output, error, warn, debug, setLogLevel
from simulator.config.device_defs import ExecutableNode
from simulator.config.auxiliary_config import Scenario
from simulator.config.device_config import get_device_mapping
from simulator.modbus.types import IPString
from simulator.modbus.tag import Tag
from typing import DefaultDict, Dict, List, overload
from typing import Literal, Optional, Set, Tuple, TextIO, Union
from collections import defaultdict
from rich import print as print_tree
from rich.tree import Tree
from termcolor import colored
from subprocess import Popen, TimeoutExpired
from datetime import datetime
from cmd2.utils import categorize
from cmd2.plugin import CommandFinalizationData
from terminaltables import SingleTable

def to_floatstr(x):
    return str(float(x))

class NodeCLI(NewCLI):
    def __init__(self, mininet: Mininet, stdin=sys.stdin, script=None, **kwargs):
        net_topo: Optional[ICSTopo] = mininet.topo
        if net_topo is None:
            raise Exception("Unspecified: net.topo")
        self.runnable_devices = utils.get_field_devices(
            mininet, net_topo.device_list, with_config=True)
        self.started_devices: Dict[str, Tuple[Popen, TextIO, TextIO]] = \
            kwargs.pop("started_devices", {})
        self.last_operational_devices: Dict[str, bool] = {}
        self.last_operational_links: Dict[Tuple[Node, int, Node, int], Optional[bool]] = {}
        self._exit_hooks = [self.stop_devices_on_exit]

        self._setup_link_status()
        super().__init__(mininet, stdin, script, **kwargs)

    def stop_devices_on_exit(self, data: CommandFinalizationData) -> CommandFinalizationData:
        if data.stop:
            for dev in self.started_devices:
                self._force_stop(
                    self.mn.get(dev), 
                    *self.started_devices[dev],
                    dry_run=False
                )
        return data

    def ot_complete(self, text, *args) -> List[str]:
        """Host completion. Does not include device IP/port support."""
        return [
            node.name for node in self.runnable_devices
            if isinstance(node, Node) and node.name.lower().startswith( text.lower() )
        ]

    def runnable_complete(self, text, *args) -> List[str]:
        """Host/IP completion with port support."""
        return [
            ip_port for ip_port in self.runnable_devices.keys()
            if isinstance(ip_port, str) and ip_port.lower().startswith( text.lower() )
        ]

    def basic_device_complete(self, text, *args) -> List[str]:
        """Generic node completion."""
        return self.get_node_names(text.lower())

    def functions_complete(self, text, *args) -> List[str]:
        """Returns names of functions."""
        return [fn[3:] for fn in dir(self) if fn.startswith("do_" + text.lower())]

    def basic_complete(self, text, *args) -> List[str]:
        """Generic node completion."""
        return self.basic_device_complete(text) + \
            self.functions_complete(text)

    recompile_parser = Cmd2ArgumentParser(add_help=False)
    recompile_parser.add_argument("--all-delay", "-a", default=0, type=float, help="How long to wait (in s) before starting all devices. This is in addition to device-specific delays.")
    recompile_parser.add_argument("--io-delay", "-i", default=2, type=float, help="How long to wait (in s) before starting each I/O device in the OT network. Mainly used to ensure all device runners have finished parsing and are ready to run.")
    recompile_parser.add_argument("--fbd-delay", "-b", default=4, type=float, help="How long to wait (in s) before starting each FBD in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    recompile_parser.add_argument("--plc-delay", "-p", default=8, type=float, help="How long to wait (in s) before starting each PLC in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")
    recompile_parser.add_argument("--scada-delay", "-s", default=12, type=float, help="How long to wait (in s) before starting each SCADA stage in the OT network. Mainly used to ensure that all device runners have finished parsing and are ready to run.")

    treevis_parser = Cmd2ArgumentParser("treevis", description="Visualizes the network as a tree.")
    treevis_parser.add_argument("device", nargs="?", default="PLANT", help="The root device to center the resulting tree at. Default PLANT", completer=basic_device_complete)
    treevis_parser.add_argument("--exclude", "-e", nargs="*", help="Excludes these nodes and those directly connected to it from appearing in the tree.", completer=basic_device_complete)
    treevis_parser.add_argument("--ot-network", "-o", action='store_true', help="Restricts nodes in the tree to only those directly connected to a device in the OT network.")
    @with_argparser(treevis_parser)
    def do_treevis( self, args ):
        device = args.device
        ot_network = args.ot_network
        excludes = args.exclude or []
        try:
            root_device = self.mn.get(device)
        except KeyError:
            root_device = None
        
        if root_device is None:
            try:
                root_device = next(
                    node for node in self.mn.hosts if node.name == device
                )
            except StopIteration:
                output(f"Skipped: {device}\n")
                return
        
        link: Link
        node_links: DefaultDict[Node, Set[Node]] = defaultdict(lambda: set())
        for link in self.mn.links:
            nodes = [
                intf.node for intf in [link.intf1, link.intf2]
                if intf is not None
            ]
            if any(node.name in excludes for node in nodes):
                continue
            if ot_network and not any(node in self.runnable_devices for node in nodes):
                continue
            for node in nodes:
                for other_node in nodes:
                    node_links[node].add(other_node)

        def get_label(device_name: str) -> str:
            colour = self._get_running_color(device_name)
            if "IO" in device_name:
                colour = f"dark_{colour}"
            return f"[{colour}]" + device_name

        visited: Set[Node] = set()
        tree = Tree(get_label(root_device.name))
        stack: List[Tuple[Node, Tree]] = [(root_device, tree)]
        while len(stack):
            curr_device, curr_tree = stack.pop()
            if curr_device in visited:
                continue
            visited.add(curr_device)
            for node in node_links[curr_device]:
                if node in visited:
                    continue
                new_tree = curr_tree.add(get_label(node.name))
                stack.append((node, new_tree))

        print_tree(tree)
        

    def help_ping( self ):
        self.ping_parser.print_help(sys.stdout)

    def complete_ping( self, text, line, begidx, endidx) -> List[str]:
        all_devices = self.get_node_names(text.lower())
        if 'all'.startswith(text):
            all_devices.append('all')
        return all_devices

    ping_parser = Cmd2ArgumentParser("ping", description="Pings devices in the network.")
    ping_parser.add_argument("devices", nargs="+", help="The devices to ping.", completer=basic_device_complete)
    ping_parser.add_argument("--regex", "-r", action='store_true', help="Use regex flags (e.g. AIT.+).")
    ping_parser.add_argument("--timeout", "-t", type=float, default=0.05, help="The timeout. Default 0.05")
    ping_parser.add_argument("--ot-network", "-o", action='store_true', help="Restricts search to only those in the OT network.")
    ping_parser.add_argument("--include-children", "-c", action='store_true', help="Pings the field devices that are queried by this device. Implies -o.")
    ping_parser.add_argument("--include-parents", "-p", action='store_true', help="Pings the field devices that query this device. Implies -o.")
    ping_parser.add_argument("--locally-started", "-l", action='store_true', help="Only search in devices that have been started in this session.")
    @with_argparser(ping_parser)
    def do_ping( self, args ):
        timeout: float = args.timeout
        locally_started = args.locally_started
        all_devices, use_regex = args.devices, args.regex
        include_parents, include_children = args.include_parents, args.include_children
        ot_network = args.ot_network or (include_parents or include_children)
        if locally_started:
            search_devices = {
                self.mn.get(dev) for dev, _ in self.started_devices.items()
            }
        elif ot_network:
            search_devices = {
                h for h in self.runnable_devices.keys()
                if isinstance(h, Node)
            }
        else:
            search_devices = self.mn.hosts

        if 'all' in all_devices:
            node_set = set(search_devices)
        else:
            node_set = {
                node
                for node in search_devices for device in all_devices
                if node.name == device or (use_regex and re.match(device, node.name, flags=re.IGNORECASE))
            }

        if include_children or include_parents:
            output(f"{datetime.now()}: Attempting to ping devices...\n")
            format_name = lambda dev: ("*" if dev in parents else "") + dev.name
            for node in node_set:
                all_devices, parents = { node }, set()
                if node not in self.runnable_devices:
                    all_devices = node_set #ping between all devices
                else:
                    config = self.runnable_devices[node]
                    if include_children:
                        for device_ip in config.remote_devices.values():
                            device = self._get_device_from_ip(device_ip)
                            if device is not None and device != node:
                                all_devices.add(device)
                    if include_parents:
                        for host, hconfig in self.runnable_devices.items():
                            if host != node and isinstance(host, Node) and any(
                                config.get_ip(True) == ip for ip in hconfig.remote_devices.values()
                            ):
                                all_devices.add(host)
                                parents.add(host)

                succeeded = set()
                for device in all_devices:
                    try:
                        setLogLevel('warning')
                        for _, dest, (_, recv, *_) in self.mn.pingFull({node, device}, timeout=timeout):
                            if recv == 1 and dest != node:
                                succeeded.add(dest)
                    except KeyboardInterrupt:
                        break
                    finally:
                        setLogLevel('output')
                all_devices.remove(node)
                if len(all_devices):
                    failed = all_devices.difference(succeeded)
                    ping_result = 100 * len(succeeded) / len(all_devices)
                    ping_result = colored(
                        f"{ping_result:.3f}%", "red" if ping_result < 100 else "green"
                    )
                    output(f"\n{colored(node.name + ':', 'green')} {ping_result}")
                    results = [
                        colored(format_name(dev), color="green")
                    for dev in succeeded if not dev.name.startswith("IO")] + [
                        colored(format_name(dev), color="green", attrs=("dark",))
                    for dev in succeeded if dev.name.startswith("IO")] + [
                        colored(format_name(dev), color="red")
                    for dev in failed if not dev.name.startswith("IO")] + [
                        colored(format_name(dev), color="red", attrs=("dark",))
                    for dev in failed if dev.name.startswith("IO")]
                    output(':', '\t' if len(results) < 5 else '\n')
                    self.columnize(results, 140-1)
                else:
                    output(f"Skipped: {node}\n")
        else:
            utils.ping_devices(self.mn, node_set, verbose=True, timeout=timeout)

    otlinks_parser = Cmd2ArgumentParser("otlinks", description="Prints info about device-level links in the network.")
    otlinks_parser.add_argument("devices", nargs="*", help="The devices to print links of.", completer=basic_device_complete)
    otlinks_parser.add_argument("--regex", "-r", action='store_true', help="Use regex flags (e.g. AIT.+).")
    otlinks_parser.add_argument("--separate-results", "-s", action='store_true', help="Separate links by direction. Useful for diagnosing combined servers+clients that do not respond to requests.")
    @with_argparser(otlinks_parser)
    def do_otlinks( self, args ):
        devices = args.devices
        use_regex = args.regex
        search_space = self.last_operational_links
        if use_regex:
            search_space = {
                (src, sport, dest, dport): status 
                for (src, sport, dest, dport), status in search_space.items() if any(
                    any(
                        re.match(search_term, str(node.name), re.IGNORECASE)
                        for node in (src, dest)
                    ) for search_term in devices
                )
            }
        elif len(devices):
            search_space = {
                (src, sport, dest, dport): status
                for (src, sport, dest, dport), status in search_space.items()
                if str(src.name) in devices or str(dest.name) in devices
            }

        output_set: Dict[Tuple[Node, int, Node, int], str] = {}
        combine_results = not args.separate_results
        for (src, sport, dest, dport), status in search_space.items():
            #no need to check reverse since that only happens once
            if combine_results and (dest, dport, src, sport) in output_set:
                continue
            # darken links involved with IO devices
            link_attrs = ["dark"] if any(
                node.name.startswith("IO") for node in (src, dest)
            ) else None
            sport_str = f":{sport}" if sport not in utils.KNOWN_PORTS else ""
            dport_str = f":{dport}" if dport not in utils.KNOWN_PORTS else ""
            output_set[(src, sport, dest, dport)] = colored( 
                f"{src}{sport_str}->{dest}{dport_str}", attrs=link_attrs,
                color="white" if status is None else "green" if status else "red"
            )
        self.columnize(list(output_set.values()), 140-1)

    def link_complete(self, text, *args) -> List[str]:
        return [str(link) for link in self.mn.links() if str(link).lower().startswith( text.lower() )]

    links_parser = Cmd2ArgumentParser("links", description="Prints info about links in the network.")
    links_parser.add_argument("links", nargs="*", help="The links to print info about.", completer=link_complete)
    links_parser.add_argument("--regex", "-r", action='store_true', help="Use regex flags (e.g. AIT.+).")
    links_parser.add_argument("--ot-network", "-o", action='store_true', help="Limit devices to only those in the OT network.")
    @with_argparser(links_parser)
    def do_links( self, args ):
        links = args.links
        use_regex = args.regex
        ot_network = args.ot_network
        search_space = self.mn.links
        if use_regex:
            search_space = {
                link for link in search_space
                if any(
                    re.match(search_link, str(link), re.IGNORECASE)
                    for search_link in links
                )
            }
        elif len(links):
            # searching for links between two devices is
            # too cumbersome; use exact match for now
            search_space = {
                link for link in search_space
                if str(link) in links
            }
        if ot_network:
            search_space = {
                link for link in search_space
                if any(
                    node in self.runnable_devices
                    for node in [link.intf1.node, link.intf2.node]
                )
            }

        for link in search_space:
            link_attrs = ["dark"] if any(
                node.name.startswith("IO")
                for node in (link.intf1.node, link.intf2.node)
            ) else None
            result = colored(
                f"{link} {link.status()}",
                color="white", attrs=link_attrs
            )
            output(result, '\n')

    scenario_parser = Cmd2ArgumentParser("scenario", description="Scenario handler.")
    scenario_read_parser = scenario_parser.add_subparsers(required=True, dest='action')
    load_scenario_parser = scenario_read_parser.add_parser("load", help="Loads the specified scenario")
    show_scenario_parser = scenario_read_parser.add_parser("show", help="Shows all the scenarios available")
    recompile_scenario_parser = scenario_read_parser.add_parser("recompile", parents=[recompile_parser], help="Remakes the `make` script for the current scenario")

    show_scenario_parser.add_argument("--describe", "-v", action='store_true', help="Displays the documentation of each scenario.")
    load_scenario_parser.add_argument("--use-full", "-f", action='store_true', help="Uses the CPython interpreter (instead of Pycopy) to launch device scripts.")
    load_scenario_parser.add_argument(
        "name", type=str, help="The scenario to load.",
        choices=[func.__name__ for func in Scenario.get_available()]
    )
    @with_argparser(scenario_parser)
    def do_scenario( self, args ):
        if args.action == 'load':
            scenario = 0
            for i, scn in enumerate(Scenario.get_available()):
                if scn.__name__ == args.name:
                    scenario = i
            with open('simulator/config/scenario.ini', 'w') as write_config:
                parser = configparser.ConfigParser()
                parser['default'] = {'scenario': scenario, 'micro_mode': not args.use_full}
                parser.write(write_config)
            output(f"Scenario {scenario} set as default; restart to apply changes.\n")
        elif args.action == 'show':
            describe = args.describe
            default_scenario, _ = Scenario.get_default()
            for i, scenario in enumerate(Scenario.get_available(), start=1):
                output(f"{i}. {scenario.__name__}")
                if scenario == default_scenario:
                    output(" (active)")
                if describe:
                    output(f": {scenario.__doc__}")
                output("\n")
        elif args.action == 'recompile':
            start_time = utils.create_makefile(
                self.mn.topo.device_list, args.all_delay, 
                args.io_delay, args.plc_delay, args.fbd_delay, args.scada_delay
            )
            timestamp = datetime.fromtimestamp(start_time)
            output(f"Scenario recompiled (new start time: {timestamp}); restart all devices in the OT network.\n")

    otping_parser = Cmd2ArgumentParser("otping", description="Determines link status of a device in the OT network using an industrial protocol (e.g. Modbus).")
    otping_parser.add_argument("device_port", type=str, help="The device to test, with an optional port address (default 502), e.g. AIT401:502", completer=runnable_complete)
    otping_parser.add_argument("--timeout", "-t", type=to_floatstr, default="0.5", help="The timeout. Default 0.5")        
    otping_parser.add_argument("--from", "-f", dest="faddr", default="PLANT", help="The device address to ping from, e.g. AIT402. Default 'PLANT'")
    otping_parser.add_argument("--xargs", "-x", nargs=argparse.REMAINDER, help="Additional arguments to the ping script.")
    @with_argparser(otping_parser)
    def do_otping( self, args ) -> None:
        #TODO use "special get device by ip" here
        
        device_port = args.device_port
        timeout = args.timeout
        xargs = args.xargs or []
        if ':' not in device_port:
            device_port += ":502"
        (target, port), source = device_port.split(":", 1), args.faddr
        try:
            dev_source = self.mn.get(source)
        except KeyError:
            # probably an IP - should be a device name
            error(f"Error: Could not find device {source}. If it is an IP address, pass the device name instead.\n")
            return
        try:
            dev_target = self.mn.get(target)
            dev_name = dev_target.name
            host = dev_target.IP()
        except KeyError:
            # probably an IP - doesn't need to be a device name
            host = dev_name = target

        popen: Popen = dev_source.popen([
            'python3', '-m', 'utils.otquery', f"{host}:{port}", "--timeout", timeout
        ] + xargs)
        failed = popen.wait()
        status_str = "Failed" if failed else "Success"
        self.last_operational_devices[dev_name] = not failed
        coloured_str = colored(
            f"{status_str}: ({dev_name}:{port})\n",
            "red" if failed else "green",
            attrs=["dark"] if "IO" in dev_name else None
        )
        output(coloured_str)

    errdump_parser = Cmd2ArgumentParser("errdump", description="Displays error logs for a set of devices.")
    errdump_parser.add_argument("devices", type=str, nargs="+", help="The devices whose error logs will be displayed.", completer=basic_device_complete)
    @with_argparser(errdump_parser)
    def do_errdump( self, args ):
        for dev in args.devices:
            if dev in self.started_devices:
                _, _, err = self.started_devices[dev]
                path = os.path.realpath(err.name)

                with open(path, 'r') as read_log:
                    output(self._read_file(dev, read_log))

    logdump_parser = Cmd2ArgumentParser("logdump", description="Displays running logs for a set of devices.")
    logdump_parser.add_argument("devices", type=str, nargs="+", help="The devices whose running logs will be displayed.", completer=basic_device_complete)
    @with_argparser(logdump_parser)
    def do_logdump( self, args ) -> None:
        for dev in args.devices:
            if dev in self.started_devices:
                _, log, _ = self.started_devices[dev]
                path = os.path.realpath(log.name)

                with open(path, 'r') as read_log:
                    output(self._read_file(dev, read_log))

    dump_parser = Cmd2ArgumentParser("dump", description="Prints info about devices in the network.")
    dump_parser.add_argument("devices", nargs="*", help="The devices to print info about.", completer=basic_device_complete)
    dump_parser.add_argument("--regex", "-r", action='store_true', help="Use regex flags (e.g. AIT.+).")
    dump_parser.add_argument("--ot-network", "-o", action='store_true', help="Limit devices to only those in the OT network.")
    dump_parser.add_argument("--show-children", "-c", action='store_true', help="Also display the field devices that are queried by this device.")
    dump_parser.add_argument("--show-parents", "-p", action='store_true', help="Also display the field devices that query this device (prepended with an asterisk, e.g. *SCADA).")
    @with_argparser(dump_parser)
    def do_dump( self, args ):
        show_children, show_parents = args.show_children, args.show_parents
        all_devices, use_regex = args.devices, args.regex
        ot_network = args.ot_network
        node_set: Set[Node] = set()
        if ot_network:
            search_devices = {
                h for h in self.runnable_devices
                if isinstance(h, Node)
            }
        else:
            search_devices = self.mn.values()

        if len(all_devices):
            node_set = {
                node
                for node in search_devices for device in all_devices
                if node.name == device or (use_regex and re.match(device, node.name, flags=re.IGNORECASE))
            }
        else:
            node_set = set(search_devices)

        # keep track of unique devices
        uniques: Dict[str, IPString] = {}
        for node in node_set:
            bold_attr = ["dark"]
            if node not in self.runnable_devices or not node.name.startswith("IO"):
                bold_attr = None
            node_repr = colored(
                repr(node), color=self._get_running_color(node.name),
                attrs=bold_attr
            )
            output(node_repr)
            if node in self.runnable_devices:
                output_list = []
                config = self.runnable_devices[node]
                if show_children:
                    all_remote_devices = []
                    for target, device_ip in config.remote_devices.items():
                        if target not in uniques:
                            all_remote_devices.append(target)
                            uniques[target] = device_ip
                        elif uniques[target] != device_ip:
                            all_remote_devices.append(f"{target} @ {device_ip}")

                    results = self._get_colored_device(all_remote_devices, io=True) + \
                        self._get_colored_device(all_remote_devices, io=False)
                    if len(results):
                        output_list.extend(results)

                if show_parents:
                    all_parent_devices = []
                    for host, hconfig in self.runnable_devices.items():
                        if not isinstance(host, Node):
                            continue
                        if any(config.get_ip(True) == ip for ip in hconfig.remote_devices.values()):
                            device_ip = config.get_ip(True)
                            if host.name not in uniques:
                                all_parent_devices.append(f"*{host.name}")
                                uniques[host.name] = device_ip
                            elif uniques[host.name] != device_ip:
                                all_parent_devices.append(f"*{host.name} @ {device_ip}")

                    results = self._get_colored_device(all_parent_devices, io=True) + \
                        self._get_colored_device(all_parent_devices, io=False)
                    if len(results):
                        output_list.extend(results)

                if len(output_list):
                    output(':', '\t' if len(output_list) < 5 else '\n')
                    self.columnize(output_list, 140-1)
            output('\n')

    otdump_parser = Cmd2ArgumentParser("otdump", description="Prints operational info (e.g. tags) about running devices in the OT network.")
    otdump_parser.add_argument("devices", nargs="*", completer=basic_device_complete, help="The devices to print info about. "
                                                                                           "Must be running to show device tag values.")
    otdump_parser.add_argument("--from", "-f", dest="faddr", default="PLANT", help="The device address to ping from, e.g. AIT402. Default 'PLANT'", completer=basic_device_complete)
    otdump_parser.add_argument("--regex", "-r", action='store_true', help="Use regex flags (e.g. AIT.+).")
    otdump_parser.add_argument("--unit-id", "-u", type=int, default=1, help="The unit ID to query. Default 1")
    otdump_parser.add_argument("--timeout", "-t", type=float, default=1, help="The request timeout. Default 1")
    otdump_parser.add_argument("--show-children", "-c", action='store_true', help="Also display info for the field devices that are queried by this device.")
    otdump_parser.add_argument("--show-parents", "-p", action='store_true', help="Also display info for the field devices that query this device (prepended with an asterisk, e.g. *SCADA).")
    @with_argparser(otdump_parser)
    def do_otdump( self, args ):
        show_children, show_parents = args.show_children, args.show_parents
        all_devices, use_regex = args.devices, args.regex
        config_list: Set[ExecutableNode]

        #config_list -> (host, class_name, ip_port)
        all_runnables = set(self.runnable_devices.values())
        if len(all_devices):
            config_list = set()
            for dev in all_devices:
                data = self._get_config_from_device(dev, use_regex=use_regex)
                if data is None:
                    self.pwarning("Skipped: data")
                elif use_regex:
                    config_list.update(data)
                else:
                    config_list.add(data)
        else:
            config_list = all_runnables.copy()

        def get_params(self: NodeCLI, ip_port):
            if ip_port in self.runnable_devices:
                config = self.runnable_devices[ip_port]
                device = self._get_device_from_ip(ip_port, True)
                if device is None:
                    device_name = ip_port
                else:
                    device_name = device.name
                class_name = config.get_class().__name__
                return (device_name, class_name, ip_port)
        
        output_list: Set[Tuple[str, str, IPString]] = set()
        for config in config_list:
            res = get_params(self, config.get_ip(True))
            if res is not None:
                output_list.add(res)

        for config in config_list:
            if show_children:
                for ip_port in config.remote_devices.values():
                    res = get_params(self, ip_port)
                    if res is not None:
                        output_list.add(res)

            if show_parents:
                for hconfig in all_runnables:
                    if any(
                        config.get_ip(True) == ip
                        for ip in hconfig.remote_devices.values()
                    ):
                        ip_port = hconfig.get_ip(True)
                        res = get_params(self, ip_port)
                        if res is not None:
                            output_list.add(res)
        
        output_args, source = [], args.faddr
        for items in output_list:
            output_args.extend(items)
        dev_source = self._get_device_by_name(source)
        if dev_source is None:
            error(f"Error: Could not find device {source}. If it is an IP address, pass the device name instead.\n")
            return

        output(f"Querying...")
        json_str = dev_source.cmd([
            "python3", "-m", "utils.otdump", 
            *output_args, "--unit-id", args.unit_id,
            "--timeout", args.timeout
        ])
        output("\r")
        if not json_str:
            output("No tag information available.\n")
            return
        elif json_str.lstrip()[0] != '{':
            self.pwarning(json_str)
            return

        def get_value(value: Union[bool, float, int, str]) -> str:
            if value == "?":
                return colored("?", color="white", attrs=["dark"])
            if isinstance(value, bool):
                if value:
                    return colored("True", color="green")
                return colored("False", color="red")
            if isinstance(value, float):
                res = f"{value:.3f}"
                if value == 0:
                    res = colored(res, color="white", attrs=["dark"])
                return res
            return str(value)

        try:
            json_data = json.loads(json_str)
            for host, data in json_data.items():
                table_data = [["Name", "Type", "Start", "Length", "End", "Location", "Values"]]
                table_data.extend(([
                    tag['name'], tag['dtype'], str(tag['registers']['start']),
                    str(tag['registers']['length']), str(tag['registers']['end']),
                    "Coil" if tag['storage_location'] == Tag.COILS else "Register",
                    get_value(tag['value'])
                ] for tag in data['tags']))
                device_type = colored(data['device_type'], color="green", attrs=['dark'])
                table = SingleTable(table_data, title=f"{host}: {device_type} (at {data['ip']}:{data['port']})")
                self.poutput(table.table)
        except json.JSONDecodeError as err:
            self.perror(f"For JSON: {json_str}")
            self.perror(f"Error parsing returned JSON data. Err: {err}")

        cmd_arg = colored("client.command args=params", attrs=["bold"])
        self.pfeedback(f"Call the Pymodbus REPL with the format {cmd_arg}.\n")

    otset_parser = Cmd2ArgumentParser("otset", description="Sets tag values for a given field device.")
    otset_parser.add_argument("device", help="The device whose tags to modify.", completer=runnable_complete)
    otset_parser.add_argument("tag_values", nargs="+", help="A tag=value pair (e.g. Hty=False); tags are case sensitive, whereas values are not.")
    otset_parser.add_argument("--from", "-f", dest="faddr", default="PLANT", help="The device address to ping from, e.g. AIT402. Default 'PLANT'")
    otset_parser.add_argument("--unit-id", "-u", type=int, default=1, help="The unit ID to query. Default 1")
    @with_argparser(otset_parser)
    def do_otset( self, args ):        
        target = args.device
        dev_source = self._get_device_by_name(args.faddr)
        if dev_source is None:
            error(f"Error: Could not find device {dev_source}. If it is an IP address, pass the device name instead.\n")
            return
        
        config = self._get_config_from_device(target, use_regex=False)
        if config is None:
            error("Error: Could not find device at {target}. Please verify the spelling and try again.")
            return

        self.poutput("Sending query...", end='\r')
        res_output = dev_source.cmd([
            "python3", "-m", "utils.otset", config.get_ip(True),
            config.get_class().__name__, *args.tag_values,
            "--unit-id", str(args.unit_id)
        ])

        if res_output:
            self.poutput(res_output.strip())
            self.poutput("Use `otdump` to verify the respective values have been set.")
        else:
            self.poutput("Failed to update device data.")

    def do_shell( self, line ):
        """Executes a shell command."""

        return super().do_sh( line )

    def do_clear( self, line ):
        """Clears the screen."""

        super().do_sh( 'clear' )

    def complete_stop( self, text, *args ) -> List[str]:
        if not len(self.started_devices):
            return []
        all_devices = [ 
            i for i in self.basic_device_complete( text, *args )
            if i in self.started_devices
        ]
        if 'all'.startswith(text):
            all_devices.append('all')
        return all_devices
    
    def _force_stop( self, 
        device: Node, popen: Popen, out: TextIO,
        err: TextIO, dry_run: bool = False
    ) -> List[str]:
        pids = device.cmd('ss -tlp | grep -oE "pid=([0-9]+)"')
        if pids is None:
            return []
        pids = pids.strip().split("\n")
        pid_list = [pid[4:].strip() for pid in pids] + [popen.pid]
        if not dry_run:
            for pid in pid_list:
                device.cmd(f"kill -KILL {pid}")
            popen.terminate()
            out.close()
            err.close()
        return pid_list

    device_stop_parser = Cmd2ArgumentParser("stop", description="Attempts to stop a device in the OT network.")
    device_stop_parser.add_argument("devices", type=str, nargs="+", help="The device(s) to stop, e.g. PLC101", completer=complete_stop)
    device_stop_parser.add_argument("--dry-run", "-d", action='store_true', help='Preview which process IDs will be killed.')
    @with_argparser(device_stop_parser)
    def do_stop( self, args ):
        pid_list = []
        all_devices, dry_run = args.devices, args.dry_run
        if 'all' in all_devices:
            all_devices = [dev for dev in self.started_devices]
        for dev in all_devices:
            if dev in self.started_devices:
                device = self.mn.get(dev)
                popen, out, err = self.started_devices[dev]
                pid_list.extend(self._force_stop(device, popen, out, err, dry_run=dry_run))
                if not dry_run:
                    del self.started_devices[dev]
            elif not dry_run:
                warn(f"Skipped: {dev}\n")

        if dry_run:
            self.columnize(pid_list, 140-1)

    def help_start( self ):
        self.device_start_parser.print_help(sys.stdout)

    def complete_start( self, text, line, begidx, endidx) -> List[str]:
        all_devices = [
            name for name in self.get_node_names(text.lower())
            if name not in self.started_devices
        ]
        if 'all'.startswith(text):
            all_devices.append('all')
        return all_devices
    
    device_start_parser = Cmd2ArgumentParser("start", parents=[recompile_parser], description="Starts a device in the OT network.")
    device_start_parser.add_argument("devices", type=str, nargs="+", help="The device(s) to start, e.g. PLC101", completer=runnable_complete)
    device_start_parser.add_argument("--force", "-f", action='store_true', help="Force restarts the device if it has already been started.")
    device_start_parser.add_argument("--include-children", "-c", action='store_true', help="Includes the children of the specified device(s) in the list of devices to start.")
    device_start_parser.add_argument("--dry-run", "-d", action='store_true', help='Preview the commands used to start a device.')
    device_start_parser.add_argument("--no-recompile", "-n", action='store_false', dest="recompile", help='Does not recompile the makefile.')
    @with_argparser(device_start_parser)
    def do_start( self, args ):
        start_children = args.include_children
        all_devices:List[str] = args.devices
        dry_run = args.dry_run
        if 'all' in all_devices:
            all_devices = [
                dev.name for dev in self.runnable_devices
                if isinstance(dev, Node) and dev.name not in self.started_devices
            ]

        filtered_devices: Set[Node] = set()
        for dev in all_devices:
            device = self.mn.get(dev)
            if dev in self.started_devices:
                if not args.force:
                    warn("One or more devices specified have already been started. Pass the --force flag to restart it.\n")
                    return
                elif not dry_run:
                    popen, out, err = self.started_devices[dev]
                    self._force_stop(device, popen, out, err, dry_run=False)
                    del self.started_devices[dev]
            try:
                if device not in self.runnable_devices:
                    raise KeyError(dev)
                filtered_devices.add(device)
                if start_children:
                    # restart children
                    config = self.runnable_devices[device]
                    for _, device_ip in config.remote_devices.items():
                        target_dev = self._get_device_from_ip(device_ip, True) or \
                            self._get_device_from_ip(device_ip, False)
                        if target_dev is None:
                            continue
                        filtered_devices.add(target_dev)
                        if dry_run or target_dev not in self.started_devices or not args.force:
                            continue
                        popen, out, err = self.started_devices[target_dev.name]
                        self._force_stop(target_dev, popen, out, err, dry_run=False)
                        del self.started_devices[target_dev.name]
            except KeyError as err:
                print("Skipped:", err)
                continue

        if dry_run:
            total_processes, total_devices = 0, 0
            configs = [self.runnable_devices[dev] for dev in filtered_devices]
            for device_info in get_device_mapping(configs).values():
                if not len(device_info['args']):
                    continue
                output(f"{device_info['name']}:\n")
                for args in device_info["args"]:
                    output(f"\t{args}\n")
                total_devices += 1
                total_processes += len(device_info["args"])
            output(f"{total_processes} process{'es' if total_processes != 1 else ''} "
                f"will be started across {len(filtered_devices)} device"
                f"{'s' if total_devices != 1 else ''}.\n")
        else:
            if not args.recompile:
                start_time = time.time()
            else:
                start_time = utils.create_makefile(
                    [self.runnable_devices[host] for host in filtered_devices],
                    args.all_delay, args.io_delay, args.plc_delay, args.fbd_delay,
                    args.scada_delay
                )

            for device in filtered_devices:
                self.started_devices[device.name] = utils.start_device(device)

            output("Started {0} device(s); these should begin at {1} (in {2:.2f} seconds.)\n".format(
                len(filtered_devices), datetime.fromtimestamp(start_time).time(), 
                max(0, start_time + args.scada_delay - time.time())
            ))

    query_parser = Cmd2ArgumentParser("query", description="Opens up a REPL for querying an OT device from another.")
    query_parser.add_argument("device_port", type=str, help="The device to test, with an optional port address (default 502), e.g. AIT401:502", completer=runnable_complete)
    query_parser.add_argument("--from", "-f", dest="faddr", default="PLANT", help="The device to ping from, e.g. AIT402. Default 'PLANT'", completer=ot_complete)
    @with_argparser(query_parser)
    def do_query( self, args ):
        device_port = args.device_port
        if ':' not in device_port:
            device_port += ":502"
        (target, port), source = device_port.split(":", 1), args.faddr
        try:
            dev_source = self.mn.get(source)
        except KeyError:
            # probably an IP - should be a device name
            error(f"Error: Could not find device {source}. If it is an IP address, pass the device name instead.\n")
            return
        try:
            dev_target = self.mn.get(target)
            host = dev_target.IP()
        except KeyError:
            # probably an IP - doesn't need to be a device name
            host = dev_target = target
        # TODO this should run pymodbus.console in the CLI
        # if no external window available
        popen: Popen
        pymodbus_args = [
            'pymodbus.console', 'tcp', 
            '--host', f'{host}', '--port', f'{port}'
        ]
        popen = dev_source.popen(['xterm', '-e', *pymodbus_args])

        # wait for 2 seconds; if return code available by then
        # then it has probably failed
        try:
            if popen.wait(2):
                warn("Error starting xterm. If this issue persists, "
                     "use the noninteractive version (see --help for more details).\n")
        except TimeoutExpired as err:
            pass
            
    
    otstat_parser = Cmd2ArgumentParser("otstat", description="Prints socket info about devices in the OT network.")
    otstat_parser.add_argument("devices", nargs="*", help="The devices to print info about.", completer=ot_complete)
    otstat_parser.add_argument("--regex", "-r", action='store_true', help="Use regex flags (e.g. AIT.+).")
    otstat_parser.add_argument("--locally-started", "-l", action='store_true', help="Only search in devices that have been started in this session.")
    @with_argparser(otstat_parser)
    def do_otstat( self, args ):
        all_devices, use_regex = args.devices, args.regex
        locally_started = args.locally_started
        if locally_started:
            search_devices = {
                self.mn.get(dev) for dev, _ in self.started_devices.items()
            }
        else:
            search_devices = {
                h for h in self.runnable_devices.keys()
                if isinstance(h, Node)
            }

        if len(all_devices):
            node_set = {
                node
                for node in search_devices for device in all_devices
                if node.name == device or (use_regex and re.match(device, node.name, flags=re.IGNORECASE))
            }
        else:
            node_set = search_devices

        server_table_data = [["Name", "State", "Recv-Q", "Send-Q", "Local Address:Port", "Peer Address:Port", "Process"]]
        client_table_data = [["Name", "State", "Local Address", "Process"]]
        for dev in node_set:
            dev_name: str = dev.name
            self.last_operational_devices[dev_name] = False
            result: Optional[str] = dev.cmd(f'ss -Htlpn')
            if result is not None:
                result = result.strip()
                if len(result):
                    results = result.split("\n")
                    for line in results:
                        server_table_data.append([dev_name] + [data.strip() for data in line.split(" ") if len(data.strip())])
                    self.last_operational_devices[dev_name] = True
            else:
                for process in ['python3', 'pycopy']:
                    search_cmd = shlex.join(["pgrep", "--list-full", process]) + " | " + \
                        shlex.join(["grep", dev_name])
                    result = dev.cmd(search_cmd)
                    if result is not None:
                        client_table_data.append([dev_name, "RUNNING", dev.IP(), process])

        if len(server_table_data) > 1:
            self.poutput(SingleTable(server_table_data, title="Running Servers").table)
        if len(client_table_data) > 1:
            self.poutput(SingleTable(client_table_data, title="Running Clients").table)
        if len(server_table_data) == 1 and len(client_table_data) == 1:
            warn("No running devices.\n")

    otpingall_parser = Cmd2ArgumentParser("otpingall", description="Determines link status of all devices in the OT network using an industrial protocol (e.g. Modbus).")
    otpingall_parser.add_argument("timeout", nargs="?", type=to_floatstr, default="0.5", help="The timeout. Default 0.5")
    otpingall_parser.add_argument("--locally-started", "-l", action="store_true", help="Only test links involving devices started in this session.")
    otpingall_parser.add_argument("--show-down", "-s", action="store_true", help="Shows links that are down.")
    otpingall_parser.add_argument("--hide-up", "-u", action="store_true", help="Hides links that are up. Implies -s.")
    otpingall_parser.add_argument("--chunk-size", "-c", type=int, default=5, help="The number of devices to poll at a time. Default 5")
    otpingall_parser.add_argument("--xargs", "-x", nargs=argparse.REMAINDER, help="Additional arguments to the ping script.")
    @with_argparser(otpingall_parser)
    def do_otpingall( self, args ):
        # get options
        chunk_size = args.chunk_size
        locally_started = args.locally_started
        timeout, xargs = args.timeout, args.xargs or []
        hide_up, show_down = args.hide_up, args.show_down
        device_infos: List[Tuple[Node, Node, IPString]] = []
        
        # if locally started, then get all devices which are both source and destination
        # runnable devices contains all devices in OT network
        # each device has a config which contains remote devices (name and IP)
        # remote device names do not map to a Node, so look up Node based on IP
        for dev, config in self.runnable_devices.items():
            if not isinstance(dev, Node):
                continue
            for target, device_ip in config.remote_devices.items():
                target_dev = self._get_device_from_ip(device_ip, True) or \
                    self._get_device_from_ip(device_ip, False)
                        # fallback if IO is on the same device
                if target_dev is None:
                    debug(f"Skipped: {dev} -> {target} @ {device_ip}\n")
                else:
                    is_started = locally_started and any(
                        d.name in self.started_devices
                        for d in [dev, target_dev]
                    )
                    if not locally_started or is_started:
                        device_infos.append((dev, target_dev, device_ip))

        total_devices = len(device_infos)
        if total_devices == 0:
            warn("No running devices.\n")
            return

        queried = 0
        with tqdm.tqdm(total=total_devices, leave=False) as progress:
            up_links, down_links = [], []
            time_taken:float = time.time()
            try:
                for i in range(0, len(device_infos), chunk_size):
                    chunk_pings: List[Tuple[Node, Node, str, Popen]] = [
                        (dev, target, ip, dev.popen(['python3', '-m', 'utils.otquery', ip, "--timeout", timeout] + xargs))
                        for dev, target, ip in device_infos[i:i+chunk_size]
                    ]

                    for dev, target, target_ip, dev_popen in chunk_pings:
                        exit_code = dev_popen.wait()
                        target_port = int(target_ip.split(':')[-1])
                        dev_port = int(self.runnable_devices[dev].get_ip(True).split(':')[-1])
                        self.last_operational_devices[target.name] = \
                            self.last_operational_links[(dev, dev_port, target, target_port)] = \
                                self.last_operational_links[(target, target_port, dev, dev_port)] = \
                                    not exit_code
                        target_port = f":{target_port}" if target_port not in utils.KNOWN_PORTS else ""
                        dev_port = f":{dev_port}" if dev_port not in utils.KNOWN_PORTS else ""
                        result = colored(
                            f"{dev.name}{dev_port}->{target.name}{target_port}",
                            attrs=["dark"] if dev.name.startswith("IO") else None
                        )
                        if exit_code:
                            down_links.append(colored(result, 'red'))
                        else:
                            up_links.append(colored(result, 'green'))
                        progress.set_description(result)
                        progress.update(1)
                        queried += 1
            except KeyboardInterrupt:
                pass

        display_out = []
        time_taken = time.time() - time_taken
        percentage = 100*len(up_links)/queried
        if not hide_up:
            display_out += up_links
        if show_down or not hide_up:
            display_out += down_links
        if len(display_out):
            self.columnize(display_out, 140-1)
        output(f"{len(up_links)}/{queried} OT links up ({percentage:.1f}%) "
            f"in {time_taken:.1f} seconds.\n")

    def complete_dump(self, text, line, begidx, endidx) -> List[str]:
        return self.get_node_names(line[begidx:endidx].lower())

    def get_node_names(self, start) -> List[str]:
        return [node.name for node in self.mn.values() if node.name.lower().startswith( start )]
    
    def _get_colored_device( self, device_list: List[str], io=False ) -> List[str]:
        dark = ["dark"]
        return [
            colored(dev, self._get_running_color(dev), attrs=dark if io else None)
            for dev in device_list if io == ("IO" in dev)
        ]
    
    def _get_running_color( self, device: str ) -> str:
        status = self.last_operational_devices.get(device, None)
        if status is not None:
            return "green" if status else "red"
        return "white"

    def _get_device_from_ip( self, ip, with_port=False ) -> Optional[Node]:
        # quick search
        if ip in self.runnable_devices:
            config = self.runnable_devices[ip]
            ip_base = config.get_ip(False)
            for host, conf in self.runnable_devices.items():
                if isinstance(host, Node) and conf.get_ip(False) == ip_base:
                    return host

        # slower search
        for device, conf in self.runnable_devices.items():
            if not isinstance(device, Node):
                continue
            req_ip = ip
            dev_ip, dev_port = conf.get_ip(True).split(":")
            if ':' not in ip:
                req_ip += ":502"
            req_ip, req_port = req_ip.split(":")
            if (with_port and (dev_ip, dev_port) == (req_ip, req_port)) or \
                (not with_port and dev_ip == req_ip):
                return device
        return None

    def _setup_link_status( self ) -> None:
        for dev, config in self.runnable_devices.items():
            if not isinstance(dev, Node):
                continue
            for device_ip in config.remote_devices.values():
                target_dev = self._get_device_from_ip(device_ip, True) or \
                    self._get_device_from_ip(device_ip, False)
                        # fallback if IO is on the same device
                if target_dev is not None:
                    target_port = int(device_ip.split(':')[1])
                    dev_port = int(self.runnable_devices[dev].get_ip(True).split(':')[1])
                    self.last_operational_links[(dev, dev_port, target_dev, target_port)] = None

    def _get_device_by_name( self, name ) -> Optional[Node]:
        try:
            return self.mn.get(name)
        except KeyError:
            # probably an IP - should be a device name
            if ':' in name:
                name, *_ = name.split(":")
            return self._get_device_from_ip(name, False)

    def _read_file( self, dev, read_file ):
        out_str = ""
        if read_file.read(1):
            read_file.seek(0)
            out_str += f"{dev}:\n"
            for line in read_file:
                out_str += f"\t{line.rstrip()}\n"
        return out_str

    @overload
    def _get_config_from_device( self, dev, use_regex:Literal[False] = False ) -> \
        Optional[ExecutableNode]: pass

    @overload
    def _get_config_from_device( self, dev, use_regex:Literal[True] = True ) -> \
        Set[ExecutableNode]: pass
        
    def _get_config_from_device( self, dev, use_regex:bool = False ) -> \
        Union[Optional[ExecutableNode], Set[ExecutableNode]]:
        if dev in self.runnable_devices:
            return self.runnable_devices[dev]
        if ':' in dev:
            *ip, port = dev.split(":")
            ip = ':'.join(ip)
        else:
            ip, port = dev, utils.DEFAULT_PORT
        ip_port = f"{ip}:{port}"
        if use_regex:
            ip_list = set()
            for config in self.runnable_devices.values():
                conf_ip = config.get_ip(True)
                if (use_regex and re.match(ip_port, conf_ip, flags=re.IGNORECASE)):
                    ip_list.add(config)
            return ip_list
        for config in self.runnable_devices.values():
            conf_ip = config.get_ip(True)
            if ip_port.lower() == conf_ip.lower():
                return config
        return None

    def default( self, line ):
        """Called on an input line when the command prefix is not recognized.
           Overridden to run shell commands when a node is the first
           CLI argument.  Past the first CLI argument, node names are
           automatically replaced with corresponding IP addrs."""

        first, args = line.command, line.args
        if first in self.mn:
            if not args:
                error( '*** Please enter a command for node: %s <cmd>\n'
                       % first )
                return
            node = self.mn[ first ]
            rest = args.split( ' ' )
            # Substitute IP addresses for node names in command
            # If updateIP() returns None, then use node name
            rest = [ self.mn[ arg ].defaultIntf().updateIP() or arg
                     if arg in self.mn else arg
                     for arg in rest ]
            rest = ' '.join( rest )
            # Run cmd on node:
            node.sendCmd( rest )
            self.waitForNode( node )
        else:
            super().default( line.command_and_args )

    categorize((
        do_query, do_otset, do_otdump,
        do_otpingall, do_errdump, do_logdump,
        do_otlinks, do_otstat, do_scenario,
        do_start, do_stop, do_treevis, do_otping
    ), "OT Utilities")
