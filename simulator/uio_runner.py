#!../pycopy

# runs i/o devices using pycopy to reduce memory usage
# device_runner.py <type> [--connected] [--target] [--interval] [--host] [--port] 
# -> device_runner.py mv --connected
if __name__ == "__main__":
    def run_main():
        from typing import Dict, Type
        from io_plc import IO_MV, IO_PMP_UV, IO_SWITCH, IO_AIN_FIT, VSD, VSD_In, VSD_Out
        from modbus.helpers import get_remote_ips, create_micro_parser, start_device
        from modbus.base import BaseModbusDevice
        
        parser = create_micro_parser()
        parser.add_argument("--connected", "-c", action="store_true", help="\t\t\tWhether this I/O device runs its _main_loop or not.")
        
        args = parser.parse_args()

        # get device class
        DEVICE_CLASSES: Dict[str, Type[BaseModbusDevice]] = {
            'mv': IO_MV, 'uv': IO_PMP_UV, 'pmp': IO_PMP_UV, 'switch': IO_SWITCH, 'ain': IO_AIN_FIT,
            'fit': IO_AIN_FIT, 'vsd': VSD, 'vsd_in': VSD_In, 'vsd_out': VSD_Out
        }
        Device = DEVICE_CLASSES[args.type]
        
        # form device args
        device_args = { 
            arg: param for arg, param in args.__dict__.items() 
            if arg not in { 
                "device", "type", "host", "port", "remote_devices",
                "io_delay", "plc_delay", "fbd_delay", "scada_delay",
                "start_time"
            }
        }

        device = Device(
            start_time=args.start_time + args.io_delay, remote_devices=get_remote_ips(args.remote_devices), **device_args
        )
        # cleanup
        del parser, DEVICE_CLASSES

        # start device
        start_device(device, _host=args.host, _port=args.port)
    
    run_main()