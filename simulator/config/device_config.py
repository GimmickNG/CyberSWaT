from typing import Dict, Generator, Iterable, Optional, Tuple
from .auxiliary_config import *

NETMASK = 27-1
def create_device_config(
    scenario: Optional[Scenario] = None,
    starting_networks: Optional[Iterator[ipy.IPv4Network]] = None,
    external_ip: Optional[ipy.IPv4Address] = None,
) -> Tuple[List[ExecutableNode], List[ipy.IPv4Network]]:
    if starting_networks is None:
        starting_networks = ipy.IPv4Network("192.168.0.0/24").subnets(new_prefix=NETMASK)
    conf = NetConfig(starting_networks)
    
    if scenario is None:
        scenario = Scenario(*Scenario.get_default())
    get_plc_ip, get_fbd_ip, get_io_ip = scenario()

    # commandline arguments are simplified by the fact that
    # most I/O devices are simple Modbus servers, and don't
    # need any remote device lookups - so only the PLCs and
    # FBDs can have special arguments for remote devices
    
    # the only exception is VSD_Out which is an I/O device
    # which also requires a target I/O device. Handle this
    # case separately.

    if external_ip is None:
        external_ip = next(conf.get_current_network().hosts())
    with conf.next_subnet() as sub_conf:
        with sub_conf.next_net() as hosts:
            # dummy router required because other links fail without it for some reason
            RTRDMY = Router(get_plc_ip(hosts), name="DUMMY")
        
        with sub_conf.next_net() as hosts:
            router_ip = get_plc_ip(hosts)
            PLC101 = PLC("PLC101", get_plc_ip(hosts), PLC.PLC1, fbds=[
                PUMP("P101", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                PUMP("P102", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                MOTORISED_VALVE("MV101", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True)),
                DUTY2("DTY101", get_fbd_ip(hosts)),
                LEVEL_TRANSMITTER("LIT101", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -15, 10, 0),
                FLOW_TRANSMITTER("FIT101", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 1225, 0),
                FLOW_TRANSMITTER("FIT201", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -5, 4, 0)
            ])
            RTR101 = Router(router_ip, PLC101, name="RTR101")

        with sub_conf.next_net() as hosts:
            router_ip = get_plc_ip(hosts)
            PLC201 = PLC("PLC201", get_plc_ip(hosts), PLC.PLC2, fbds=[
                MOTORISED_VALVE("MV201", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True)),
                SWITCH("LSL201", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSL202", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSL203", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSLL203", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                PUMP("P201", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P202", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P203", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P204", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P205", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P206", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P207", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P208", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                DUTY2("DTY201", get_fbd_ip(hosts)), 
                DUTY2("DTY202", get_fbd_ip(hosts)),
                DUTY2("DTY203", get_fbd_ip(hosts)),
                LEVEL_TRANSMITTER("AIT201", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 1000, 0),
                LEVEL_TRANSMITTER("AIT202", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 12, 2),
                LEVEL_TRANSMITTER("AIT203", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 800, 0)
            ])
            RTR201 = Router(router_ip, PLC201, name="RTR201")

        with sub_conf.next_net() as hosts:
            router_ip = get_plc_ip(hosts)
            PLC301 = PLC("PLC301", get_plc_ip(hosts), PLC.PLC3, fbds=[
                LEVEL_TRANSMITTER("LIT301", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 1250, 0),
                DUTY2("DTY301", get_fbd_ip(hosts)), 
                PUMP("P301", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                PUMP("P302", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                FLOW_TRANSMITTER("FIT301", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -15, 4, 0),
                SWITCH("PSH301", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("DPSH301", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                LEVEL_TRANSMITTER("DPIT301", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -30, 100, 0),
                MOTORISED_VALVE("MV301", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True), 10, 10),
                MOTORISED_VALVE("MV302", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True), 10, 10),
                MOTORISED_VALVE("MV303", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True), 10, 10),
                MOTORISED_VALVE("MV304", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True), 10, 10)
            ])
            RTR301 = Router(router_ip, PLC301, name="RTR301")

        with sub_conf.next_net() as hosts:
            router_ip = get_plc_ip(hosts)
            PLC401 = PLC("PLC401", get_plc_ip(hosts), PLC.PLC4, fbds=[
                LEVEL_TRANSMITTER("LIT401", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 1200, 0),
                DUTY2("DTY401", get_fbd_ip(hosts)),
                PUMP("P401", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                PUMP("P402", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                LEVEL_TRANSMITTER("AIT401", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 150, 0),
                FLOW_TRANSMITTER("FIT401", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 800, 0),
                LEVEL_TRANSMITTER("AIT402", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -5, 4, 0),
                UV_PUMP("UV401", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                SWITCH("LS401", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                DUTY2("DTY402", get_fbd_ip(hosts)),
                PUMP("P403", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts))),
                PUMP("P404", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts)))
            ])
            RTR401 = Router(router_ip, PLC401, name="RTR401")

        with sub_conf.next_net() as hosts:
            router_ip = get_plc_ip(hosts)
            PLC501 = PLC("PLC501", get_plc_ip(hosts), PLC.PLC5, fbds=[
                LEVEL_TRANSMITTER("AIT501", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 12, 2),
                LEVEL_TRANSMITTER("AIT502", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 800, 0),
                LEVEL_TRANSMITTER("AIT503", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 1000, 0),
                LEVEL_TRANSMITTER("AIT504", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 1200, 0),
                LEVEL_TRANSMITTER("PIT501", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 500, 0),
                LEVEL_TRANSMITTER("PIT502", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -5, 500, 0),
                LEVEL_TRANSMITTER("PIT503", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 500, 0),
                FLOW_TRANSMITTER("FIT501", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), 0, 4, 0),
                FLOW_TRANSMITTER("FIT502", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -20, 4, 0),
                FLOW_TRANSMITTER("FIT503", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -35, 4, 0),
                FLOW_TRANSMITTER("FIT504", get_fbd_ip(hosts), IO_AIN_FIT(get_io_ip(hosts)), -15, 2, 0),
                MOTORISED_VALVE("MV501", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True)),
                MOTORISED_VALVE("MV502", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True)),
                MOTORISED_VALVE("MV503", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True)),
                MOTORISED_VALVE("MV504", get_fbd_ip(hosts), IO_MV(get_io_ip(hosts), connected=True)),
                DUTY2("DTY501", get_fbd_ip(hosts))
            ])
            RTR501 = Router(router_ip, PLC501, name="RTR501")

            # VSD_In, VSD_Out and VSD all defined on same node - declare VSD a parent and make VSD_In and VSD_Out its children
            # keep fbd on plc node - acquire its host-port here
            vsd_501_fbd_ip, vsd_502_fbd_ip = get_fbd_ip(hosts), get_fbd_ip(hosts)

            vsd_501, vsd_501_in = IO_VSD(get_plc_ip(hosts)), IO_VSD_In(get_fbd_ip(hosts))
            vsd_501_out = IO_VSD_Out(get_fbd_ip(hosts), vsd=vsd_501, connected=True)
            #vsd_501_ip, vsd_501_in, vsd_501 = get_fbd_ip(hosts), IO_VSD_In(get_io_ip(hosts)), IO_VSD(hosts.next_port())
            #vsd_501_out = IO_VSD_Out(hosts.next_port(), vsd=vsd_501, connected=True)
            
            vsd_502, vsd_502_in = IO_VSD(get_plc_ip(hosts)), IO_VSD_In(get_fbd_ip(hosts))
            vsd_502_out = IO_VSD_Out(get_fbd_ip(hosts), vsd=vsd_502, connected=True)
            #vsd_502_ip, vsd_502_in, vsd_502 = get_fbd_ip(hosts), IO_VSD_In(get_io_ip(hosts)), IO_VSD(hosts.next_port())
            #vsd_502_out = IO_VSD_Out(hosts.next_port(), vsd=vsd_502, connected=True)

            new_plc501_devices: List[ExecutableNode] = [
                VARIABLE_SPEED_DRIVE("P501", vsd_501_fbd_ip, vsd_501_in, vsd_501_out, vsd_501),
                VARIABLE_SPEED_DRIVE("P502", vsd_502_fbd_ip, vsd_502_in, vsd_502_out, vsd_502),
            ]
            PLC501.devices.extend(new_plc501_devices)
            PLC501.remote_devices.update({
                device.get_short_name(): device.get_ip(with_port=True) for device in new_plc501_devices
            })

        with sub_conf.next_net() as hosts:
            router_ip = get_plc_ip(hosts)
            PLC601 = PLC("PLC601", get_plc_ip(hosts), PLC.PLC6, fbds=[
                SWITCH("LSL601", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSL602", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSL603", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSH601", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSH602", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                SWITCH("LSH603", get_fbd_ip(hosts), IO_SWITCH(get_io_ip(hosts))),
                PUMP("P601", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                PUMP("P602", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts), connected=True)),
                PUMP("P603", get_fbd_ip(hosts), IO_PMP(get_io_ip(hosts)))
            ])
            RTR601 = Router(router_ip, PLC601, name="RTR601")

        all_stages: List[ExecutableNode] = [RTRDMY, RTR101, RTR201, RTR301, RTR401, RTR501, RTR601]
        with sub_conf.next_net() as hosts:
            RTR001 = Router(get_plc_ip(hosts), SCADA(
                "SCADA", get_plc_ip(hosts), SCADA.MAINSCADA, targets=[
                    SCADA("SCADAS1", hosts.next_port(of_parent=True), SCADA.SCADAS1, targets=list(walk_devices([PLC101]))),
                    SCADA("SCADAS2", hosts.next_port(of_parent=True), SCADA.SCADAS2, targets=list(walk_devices([PLC201]))),
                    SCADA("SCADAS3", hosts.next_port(of_parent=True), SCADA.SCADAS3, targets=list(walk_devices([PLC301]))),
                    SCADA("SCADAS4", hosts.next_port(of_parent=True), SCADA.SCADAS4, targets=list(walk_devices([PLC401]))),
                    SCADA("SCADAS5", hosts.next_port(of_parent=True), SCADA.SCADAS5, targets=list(walk_devices([PLC501]))),
                    SCADA("SCADAS6", hosts.next_port(of_parent=True), SCADA.SCADAS6, targets=list(walk_devices([PLC601]))),
                ]
            ), name="RTRSCD")

    with conf.next_subnet() as hosts:
        gt_names = {
            "IOLIT101", "IOLIT301", "IOLIT401", "IOLSL601", "IOLSH601", "IOLSL602", "IOLSH602", "IOP101",
            "IOP102",   "IOP301",   "IOP302",   "IOP401",   "IOP402",   "IOP501",   "IOP502",   "IOP601",   
            "IOP602",   "IOMV101",  "IOMV201",  "IOMV301",  "IOMV302",  "IOMV303",  "IOMV304",  "IOMV501",
            "IOMV502",  "IOMV503",  "IOMV504"
        }

        # make the PlantNode its own device if the PlantNode as a Router does not work
        ground_truth = PlantNode((external_ip, 502), name="PLANT", targets=[
            device for device in walk_devices(all_stages) if device.get_short_name() in gt_names
        ], devices=all_stages + [RTR001])

    runner: str
    for device in walk_devices([ground_truth]):
        if len(device.cmd_args) and '.py' not in ''.join(device.get_args()):
            if scenario.use_micro and device.supports_micro():
                runner = MICRO_IO_RUNNER if isinstance(device, IODevice) else MICRO_FBD_RUNNER
            else:
                runner = DEVICE_RUNNER
            device.cmd_args = (runner,) + device.cmd_args

    # TODO configure routes in topo.py
    return [ground_truth], conf.get_remaining_networks()

def generate_config(device_list):
    return [
        {
            "name": dev.get_name(),
            "ip": dev.get_ip(),
            "class": dev.get_class(),
            "args": dev.get_args(),
            "devices": generate_config(dev.get_devices())
        }
        for dev in device_list
    ]

def walk_devices(device_list: List[ExecutableNode]) -> Generator[ExecutableNode, None, None]:
    for device in device_list:
        yield device
        for sub_device in walk_devices(device.get_devices()):
            yield sub_device

def get_device_mapping(config: Optional[List[ExecutableNode]] = None) -> Dict[IPString, DeviceMapping]:
    if config is None:
        config, _ = create_device_config()
    ip_map: Dict[IPString, DeviceMapping] = {}

    def sort_by_type(device: ExecutableNode):
        if isinstance(device, Router):
            factor = 0    # Routers appear first
        elif isinstance(device, Device):
            if isinstance(device, SCADA):
                factor = 2 + (device.scada_class/10)
            elif isinstance(device, PLC):
                factor = 4
            elif isinstance(device, FBD):
                factor = 6
            else:
                factor = 8    # next come Devices
        elif isinstance(device, IODevice):
            factor = 10    # next come IODevices
        else:
            factor = 12    # return generic ExecutableNodes last

        # sort in alphabetical order by importance
        return (factor * 4096) + sum(ord(char) for char in type(device).__name__)

    for device in sorted(set(walk_devices(config)), key=sort_by_type):
        device_ip = device.get_ip()
        if device_ip not in ip_map:
            ip_map[device_ip] = {
                'name': device.get_short_name(),
                'args': []
            }
        dev_args = device.get_args()
        if len(dev_args):
            ip_map[device_ip]['args'].append(dev_args)

    return ip_map

def generate_make(*args, **kwargs):
    xargs = kwargs.pop('xargs', "")
    device_mapping, make_lines = get_device_mapping(*args, **kwargs), []
    # generate make commands based on the ip address - the same
    # ip = the same machine, even if different ports are used
    for device_info in device_mapping.values():
        num_args = len(device_info['args'])
        if not num_args:
            continue
        run_bg = '&' if num_args > 1 else ''
        make_lines += [f"{device_info['name']}:"] + [f"\t{args} {xargs} {run_bg} " for args in device_info["args"]]
    
    #make_lines.append(".SILENT:")
    return make_lines
