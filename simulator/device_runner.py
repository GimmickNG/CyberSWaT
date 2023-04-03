#!/usr/bin/env python3
import argparse
from argparse import Namespace, ArgumentParser
from typing import Any, Dict, List

def get_var_args(args:Namespace, filter_items: set) -> Dict[str, Any]:
    return { 
        arg: param for arg, param in vars(args).items() 
        if arg not in filter_items
    }

def run_generic_device(args:Namespace) -> None:
    from modbus.helpers import start_device, get_remote_ips

    device_args = get_var_args(args, { 
        "run_device", "command", "type", "device_class",
        "host", "port", "remote_devices","io_delay",
        "plc_delay", "fbd_delay", "scada_delay", "start_time"
    })

    device = args.device_class(
        start_time=args.start_time + args.plc_delay,
        remote_devices=get_remote_ips(args.remote_devices), **device_args
    )
    start_device(device, _host=args.host, _port=args.port)

def create_fbd_runners(fbd_parser: ArgumentParser, parent_parser: ArgumentParser) -> None:
    from controlblock import MV_FBD, UV_FBD, AIN_FBD, VSD_FBD, Duty2_FBD, FIT_FBD, PMP_FBD, SWITCH_FBD
    from modbus.helpers import parse_negative_float, parse_negative_int

    run_fbd = run_generic_device
    fbd_runners = fbd_parser.add_subparsers(dest='type', required=True)
    ####MV FBD
    mv_runner = fbd_runners.add_parser("mv", parents=[parent_parser], description="Motorised Valve Function Block Diagram Simulator")
    mv_runner.add_argument("--Open-TM", "-0", default=15, type=int, help="Valve open timeout. Default 15, plc3 uses 10")
    mv_runner.add_argument("--Close-TM", "-1", default=15, type=int, help="Valve close timeout. Default 15, plc3 uses 10")
    mv_runner.add_argument("--FTO", "-2", action="store_true", help="HMI FT Open. Default 0 (uninitialized/indeterminate state)")
    mv_runner.add_argument("--FTC", "-3", action="store_true", help="HMI FT Closed. Default 0 (uninitialized/indeterminate state)")
    mv_runner.add_argument("--Open", "-4", action="store_true", help="HMI Open. Default 0 (uninitialized/indeterminate)")
    mv_runner.add_argument("--Close", "-5", action="store_true", help="HMI Close. Default 0 (uninitialized/indeterminate)")
    mv_runner.set_defaults(device_class=MV_FBD, run_device=run_fbd)
    ####UV FBD
    uv_runner = fbd_runners.add_parser("uv", parents=[parent_parser], description="UV Pump Function Block Diagram Simulator")
    uv_runner.add_argument("--Start-TM", "-0", default=3, type=int, help="Pump start timeout. Default 3")
    uv_runner.add_argument("--Stop-TM", "-1", default=3, type=int, help="Pump stop timeout. Default 3")
    uv_runner.add_argument("--Disable-Avl", "-2", action="store_false", dest="Avl", help="Avl action. Default 1, use this to set to 0.")
    uv_runner.add_argument("--Fault", "-3", action="store_true", help="Fault in device. Default 0, specify this to set to 1")
    uv_runner.add_argument("--FTS", "-4", action="store_true", help="FT Stop. Default Default 0 (uninitialized/indeterminate)")
    uv_runner.add_argument("--FTR", "-5", action="store_true", help="FT Running. Default 0 (uninitialized/indeterminate)")
    uv_runner.add_argument("--RunHr", "-6", default=0.0, type=parse_negative_float, help="Runtime (hrs). Default 0.")
    uv_runner.add_argument("--Shutdown", "-7", default=0, type=int, help="Shutdown bitmask as a 32-bit integer. Default 0.")
    uv_runner.set_defaults(device_class=UV_FBD, run_device=run_fbd)
    ####LIT FBD
    ain_runner = fbd_runners.add_parser("ain", parents=[parent_parser], description="Level Transmitter Function Block Diagram Simulator")
    ain_runner.add_argument("--L-Raw-RIO", "-0", default=0, type=parse_negative_int, help="Initial value of L_Raw_RIO.")
    ain_runner.add_argument("--HEU", "-1", default=1225.0, type=parse_negative_float, help="Initial value of HEU.")
    ain_runner.add_argument("--LEU", "-2", default=0.0, type=parse_negative_float, help="Initial value of LEU.")
    ain_runner.add_argument("--Disable-Hty", "-3", action="store_false", dest="Hty", help="Whether to disable Hty or not. (Enabled by default)")
    ain_runner.add_argument("--AHH", "-4", action="store_true", help="Whether the highest alarm is enabled or not.")
    ain_runner.add_argument("--AH", "-5", action="store_true", help="Whether the high alarm is enabled or not.")
    ain_runner.add_argument("--AL", "-6", action="store_true", help="Whether the low alarm is enabled or not.")
    ain_runner.add_argument("--ALL", "-7", action="store_true", help="Whether the lowest alarm is enabled or not.")
    ain_runner.add_argument("--Wifi", "-8", dest="Wifi_Enb", action="store_true", help="Whether wifi is enabled or not. Default 0")
    ain_runner.set_defaults(device_class=AIN_FBD, run_device=run_fbd)
    ####FIT FBD
    fit_runner = fbd_runners.add_parser("fit", parents=[parent_parser], description="Flow Rate Indicator and Transmitter Function Block Diagram Simulator")
    fit_runner.add_argument("--L-Raw-RIO", "-0", default=-15, type=parse_negative_int, help="Initial value of L_Raw_RIO. Default -15")
    fit_runner.add_argument("--HEU", "-1", default=4.0, type=parse_negative_float, help="Initial value of HEU. Default 4.0")
    fit_runner.add_argument("--LEU", "-2", default=0.0, type=parse_negative_float, help="Initial value of LEU. Default 0.0")
    fit_runner.add_argument("--Hty", "-3", action="store_true", help="Whether Hty is enabled or not.")
    fit_runner.add_argument("--AHH", "-4", default="store_true", help="Whether the highest alarm is enabled or not.")
    fit_runner.add_argument("--AH", "-5", default="store_true", help="Whether the high alarm is enabled or not.")
    fit_runner.add_argument("--AL", "-6", default="store_true", help="Whether the low alarm is enabled or not.")
    fit_runner.add_argument("--ALL", "-7", default="store_true", help="Whether the lowest alarm is enabled or not.")
    fit_runner.add_argument("--Wifi", "-8", dest="Wifi_Enb", action="store_true", help="Whether wifi is enabled or not. Default 0")
    fit_runner.set_defaults(device_class=FIT_FBD, run_device=run_fbd)
    ####PMP FBD
    pmp_runner = fbd_runners.add_parser("pmp", parents=[parent_parser], description="Pump Function Block Diagram Simulator")
    pmp_runner.add_argument("--Start-TM", "-0", default=3, type=int, help="Pump start timeout. Default 3")
    pmp_runner.add_argument("--Stop-TM", "-1", default=3, type=int, help="Pump stop timeout. Default 3")
    pmp_runner.add_argument("--Disable-Avl", "-2", action="store_false", dest="Avl", help="Avl action. Default 1, use this to set to 0.")
    pmp_runner.add_argument("--Fault", "-3", action="store_true", help="Fault in device. Default 0, specify this to set to 1")
    pmp_runner.add_argument("--FTS", "-4", action="store_true", help="FT Stop. Default Default 0 (uninitialized/indeterminate)")
    pmp_runner.add_argument("--FTR", "-5", action="store_true", help="FT Running. Default 0 (uninitialized/indeterminate)")
    pmp_runner.add_argument("--RunHr", "-6", default=0.0, type=parse_negative_float, help="Runtime (hrs). Default 0.")
    pmp_runner.add_argument("--Shutdown", "-7", default=0, help="Shutdown bitmask as a 32-bit integer. Default 0.")
    pmp_runner.set_defaults(device_class=PMP_FBD, run_device=run_fbd)
    ####VSD FBD
    vsd_runner = fbd_runners.add_parser("vsd", parents=[parent_parser], description="Variable Speed Drive (Pressure Pump) Function Block Diagram Simulator")
    vsd_runner.add_argument("--Start-TM", "-0", default=20, type=int, help="VSD start timeout. Default 3")
    vsd_runner.add_argument("--Stop-TM", "-1", default=20, type=int, help="VSD stop timeout. Default 3")
    vsd_runner.add_argument("--Disable-Avl", "-2", action="store_false", dest="Avl", help="Avl action. Default True, use this to set to False.")
    vsd_runner.add_argument("--Fault", "-3", action="store_true", help="Fault in device. Default 0, specify this to set to 1")
    vsd_runner.add_argument("--FTS", "-4", action="store_true", help="FT Stop. Default Default 0 (uninitialized/indeterminate)")
    vsd_runner.add_argument("--FTR", "-5", action="store_true", help="FT Running. Default 0 (uninitialized/indeterminate)")
    vsd_runner.add_argument("--RunHr", "-6", default=0.0, type=parse_negative_float, help="Runtime (hrs). Default 0.")
    vsd_runner.add_argument("--Shutdown", "-7", default=0, type=int, help="Shutdown bitmask as a 32-bit integer. Default 0.")
    vsd_runner.add_argument("--Speed", "-8", default=0.0, type=float, help="Drive speed. Default 0.")
    vsd_runner.add_argument("--Drive_Ready", "-9", action="store_true", help="Whether the drive is ready or not. Default False, use this to set to True")
    vsd_runner.set_defaults(device_class=VSD_FBD, run_device=run_fbd)
    ####Duty2 FBD
    duty2_runner = fbd_runners.add_parser("duty", parents=[parent_parser], description="Duty2 Function Block Diagram Simulator")
    duty2_runner.set_defaults(device_class=Duty2_FBD, run_device=run_fbd)
    ####SWITCH FBD
    switch_runner = fbd_runners.add_parser("switch", parents=[parent_parser], description="Switch Function Block Diagram Simulator")
    switch_runner.add_argument("--Delay", "-0", default=-1, type=parse_negative_int, help="Switch timeout. Default -1, it appears that these switch timers run forever due to a bug.")
    switch_runner.set_defaults(device_class=SWITCH_FBD, run_device=run_fbd)

def create_io_runners(io_parser: ArgumentParser, parent_parser: ArgumentParser) -> None:
    from io_plc import IO_MV, IO_AIN_FIT, IO_PMP_UV, IO_SWITCH, VSD, VSD_In, VSD_Out

    run_io = run_generic_device
    io_runners = io_parser.add_subparsers(dest='type', required=True)
    ####IO_MV
    mv_runner = io_runners.add_parser("mv", parents=[parent_parser], description="Motorised Valve Actuator Simulator")
    mv_runner.add_argument("--connected", action="store_true", help="Whether this device runs its _main_loop or not.")
    mv_runner.set_defaults(device_class=IO_MV, run_device=run_io)
    ####IO_PMP
    pmp_runner = io_runners.add_parser("pmp", parents=[parent_parser], description="UV Pump Actuator Simulator")
    pmp_runner.add_argument("--connected", action="store_true", help="Whether this device runs its _main_loop or not.")
    pmp_runner.set_defaults(device_class=IO_PMP_UV, run_device=run_io)
    ####IO_SWITCH
    switch_runner = io_runners.add_parser("switch", parents=[parent_parser], description="Switch Actuator Simulator")
    switch_runner.set_defaults(device_class=IO_SWITCH, run_device=run_io)
    ####IO_AIN_FIT
    ain_runner = io_runners.add_parser("ain", parents=[parent_parser], description="Level Transmitter Sensor Simulator")
    ain_runner.set_defaults(device_class=IO_AIN_FIT, run_device=run_io)
    ####VSD
    vsd_runner = io_runners.add_parser("vsd", parents=[parent_parser], description="Variable Speed Drive Simulator")
    vsd_runner.set_defaults(device_class=VSD, run_device=run_io)
    ####VSD_In
    vsd_in_runner = io_runners.add_parser("vsd_in", parents=[parent_parser], description="Variable Speed Drive Input Simulator")
    vsd_in_runner.set_defaults(device_class=VSD_In, run_device=run_io)
    ####VSD_Out
    vsd_out_runner = io_runners.add_parser("vsd_out", parents=[parent_parser], description="Variable Speed Drive Output Simulator")
    vsd_out_runner.add_argument("--target", "-g", default=("localhost", "502"), nargs=2, help="Target VSD IP address and port. Default is localhost 502")
    vsd_out_runner.add_argument("--connected", action="store_true", help="Whether this device runs its _main_loop or not.")
    vsd_out_runner.set_defaults(device_class=VSD_Out, run_device=run_io)

def create_plc_runners(plc_parser: ArgumentParser, parent_parser: ArgumentParser) -> None:
    from plc import PLC1, PLC2, PLC3, PLC4, PLC5, PLC6

    run_plc = run_generic_device
    plc_runners = plc_parser.add_subparsers(dest='type', required=True)
    ####PLC1
    plc1_runner = plc_runners.add_parser("1", parents=[parent_parser], description="PLC Stage 1 Runner")
    plc1_runner.set_defaults(device_class=PLC1, run_device=run_plc)
    ####PLC2
    plc2_runner = plc_runners.add_parser("2", parents=[parent_parser], description="PLC Stage 2 Runner")
    plc2_runner.set_defaults(device_class=PLC2, run_device=run_plc)
    ####PLC3
    plc3_runner = plc_runners.add_parser("3", parents=[parent_parser], description="PLC Stage 3 Runner")
    plc3_runner.set_defaults(device_class=PLC3, run_device=run_plc)
    ####PLC4
    plc4_runner = plc_runners.add_parser("4", parents=[parent_parser], description="PLC Stage 4 Runner")
    plc4_runner.set_defaults(device_class=PLC4, run_device=run_plc)
    ####PLC5
    plc5_runner = plc_runners.add_parser("5", parents=[parent_parser], description="PLC Stage 5 Runner")
    plc5_runner.set_defaults(device_class=PLC5, run_device=run_plc)
    ####PLC6
    plc6_runner = plc_runners.add_parser("6", parents=[parent_parser], description="PLC Stage 6 Runner")
    plc6_runner.set_defaults(device_class=PLC6, run_device=run_plc)

def create_scada_runners(scada_parser: ArgumentParser, parent_parser: ArgumentParser) -> None:
    from plc import SCADA, SCADAS1, SCADAS2, SCADAS3, SCADAS4, SCADAS5, SCADAS6

    run_scada = run_generic_device
    scada_runners = scada_parser.add_subparsers(dest='type', required=True)
    ####SCADA
    scada_runner = scada_runners.add_parser("0", parents=[parent_parser], description="SCADA Runner")
    scada_runner.set_defaults(device_class=SCADA, run_device=run_scada)
    ####SCADAS1
    scadas1_runner = scada_runners.add_parser("1", parents=[parent_parser], description="PLC Stage 1 Runner")
    scadas1_runner.set_defaults(device_class=SCADAS1, run_device=run_scada)
    ####SCADAS2
    scadas2_runner = scada_runners.add_parser("2", parents=[parent_parser], description="PLC Stage 2 Runner")
    scadas2_runner.set_defaults(device_class=SCADAS2, run_device=run_scada)
    ####SCADAS3
    scadas3_runner = scada_runners.add_parser("3", parents=[parent_parser], description="PLC Stage 3 Runner")
    scadas3_runner.set_defaults(device_class=SCADAS3, run_device=run_scada)
    ####SCADAS4
    scadas4_runner = scada_runners.add_parser("4", parents=[parent_parser], description="PLC Stage 4 Runner")
    scadas4_runner.set_defaults(device_class=SCADAS4, run_device=run_scada)
    ####SCADAS5
    scadas5_runner = scada_runners.add_parser("5", parents=[parent_parser], description="PLC Stage 5 Runner")
    scadas5_runner.set_defaults(device_class=SCADAS5, run_device=run_scada)
    ####SCADAS6
    scadas6_runner = scada_runners.add_parser("6", parents=[parent_parser], description="PLC Stage 6 Runner")
    scadas6_runner.set_defaults(device_class=SCADAS6, run_device=run_scada)

def create_plant_runner(plant_parser: argparse._SubParsersAction, parent_parser: ArgumentParser) -> None:
    from swat import Plant
    from modbus.base import BaseModbusDevice
    
    def run_plant(args:Namespace) -> None:
        from modbus.helpers import start_device, get_remote_ips
        from modbus.types import IPString
        from swat import Plant, LivePoller
        
        device_args = get_var_args(args, { 
            "run_device", "command", "type", "device_class", "host", "port",
            "remote_devices", "initial_state", "duration", "start_time"
        })

        # start the plant and then the poller on the port above it
        plant = Plant(
            start_state=[0, 0] + args.initial_state, 
            start_time=args.start_time + args.scada_delay,
            duration=int(args.duration / args.interval), **device_args
        )
        poller = LivePoller(
            event=plant.exec_state, shared_data_store=plant.data_store, 
            start_time=args.start_time + args.scada_delay,
            remote_devices=get_remote_ips(args.remote_devices), **device_args
        )
        start_device(plant, poller, _host=args.host, _port=args.port)
        
        # this will execute only after polling server stops
        plant.stop()

    plant_runner = plant_parser.add_parser("plant", description="SWaT Physical Process Simulator", parents=[parent_parser])
    plant_runner.add_argument("--initial-state", "-i", nargs=5, type=float, default=[550.0, 650, 500, 200, 200], help="List of values indicating start state. Default: 550 650 500 200 200") #[0, 0, 505,890,900,200,200]
    plant_runner.add_argument("--duration", "-]", default=BaseModbusDevice.HOUR_IN_SEC, type=int, help="Duration (seconds). Specify <=0 to run forever. Default {0}".format(BaseModbusDevice.HOUR_IN_SEC))
    plant_runner.set_defaults(device_class=Plant, run_device=run_plant)


if __name__ == "__main__":
    def run_main():
        from modbus.helpers import create_full_parser
        
        socket_parser = create_full_parser(parser_desc="Auxiliary Runner", add_help=False)

        parser = ArgumentParser("SWaT Device Runner. Use this to run a number of SWaT devices, such as Function Block Diagrams, I/O devices or PLCs.")
        parser.set_defaults(device_class=None, command=None, type=None, run_device=lambda args: None)

        # device_runner.py <command> <class> -> device_runner.py fbd mv --open-tm (or) device_runner.py io pmp 
        subparsers = parser.add_subparsers(dest='command', required=True)
        
        create_fbd_runners(subparsers.add_parser("fbd"), socket_parser)
        create_io_runners(subparsers.add_parser("io"), socket_parser)
        create_plc_runners(subparsers.add_parser("plc"), socket_parser)
        create_scada_runners(subparsers.add_parser("scada"), socket_parser)
        create_plant_runner(subparsers, socket_parser)

        args = parser.parse_args()
        args.run_device(args)

    run_main()