#!../pycopy

# runs fbd devices using pycopy to reduce memory usage
# similar to fbd usage in device_runner.py for compatibility
if __name__ == "__main__":
    def run_main():
        from controlblock import AIN_FBD, Duty2_FBD, FIT_FBD, MV_FBD, UV_FBD, PMP_FBD, VSD_FBD, SWITCH_FBD, FBD
        from typing import Dict, Tuple, Union, Type
        from modbus.helpers import parse_negative_float, parse_negative_int, get_remote_ips, create_micro_parser, start_device
        
        parser = create_micro_parser()
        ####MV FBD
        parser.add_argument("--Open-TM", "-0", default=15, type=int, help="Valve open timeout. Default 15, plc3 uses 10")
        parser.add_argument("--Close-TM", "-1", default=15, type=int, help="Valve close timeout. Default 15, plc3 uses 10")
        parser.add_argument("--FTO", "-2", action="store_true", help="HMI FT Open. Default 0 (uninitialized/indeterminate state)")
        parser.add_argument("--FTC", "-3", action="store_true", help="HMI FT Closed. Default 0 (uninitialized/indeterminate state)")
        parser.add_argument("--Open", "-4", action="store_true", help="HMI Open. Default 0 (uninitialized/indeterminate)")
        parser.add_argument("--Close", "-5", action="store_true", help="HMI Close. Default 0 (uninitialized/indeterminate)")
        ####FIT FBD
        parser.add_argument("--L-Raw-RIO", "-6", type=parse_negative_int, help="Initial value of L_Raw_RIO. Default -15")
        parser.add_argument("--HEU", "-7", type=parse_negative_float, help="Initial value of HEU. Default 4.0")
        parser.add_argument("--LEU", "-8", default=0.0, type=parse_negative_float, help="Initial value of LEU. Default 0.0")
        parser.add_argument("--Hty", "-9", action="store_true", default=None, help="Whether Hty is enabled or not.")
        parser.add_argument("--Disable-Hty", "-9", action="store_false", default=None, dest="Hty", help="Whether to disable Hty or not.")
        parser.add_argument("--AHH", "-a", action="store_true", help="Whether the highest alarm is enabled or not.")
        parser.add_argument("--AH", "-c", action="store_true", help="Whether the high alarm is enabled or not.")
        parser.add_argument("--AL", "-d", action="store_true", help="Whether the low alarm is enabled or not.")
        parser.add_argument("--ALL", "-e", action="store_true", help="Whether the lowest alarm is enabled or not.")
        parser.add_argument("--Wifi", "-f", action="store_true", dest="Wifi_Enb", help="Whether wifi is enabled or not. Default 0")
        ####VSD FBD
        parser.add_argument("--Start-TM", "-g", type=int, help="Start timeout. Default 20 for VSD, 3 for UV and PMP")
        parser.add_argument("--Stop-TM", "-h", type=int, help="Stop timeout. Default 20 for VSD, 3 for UV and PMP")
        parser.add_argument("--Disable-Avl", "-i", action="store_false", dest="Avl", help="Avl action. Default True, use this to set to False.")
        parser.add_argument("--Fault", "-j", action="store_true", help="Fault in device. Default 0, specify this to set to 1")
        parser.add_argument("--FTS", "-k", action="store_true", help="FT Stop. Default Default 0 (uninitialized/indeterminate)")
        parser.add_argument("--FTR", "-l", action="store_true", help="FT Running. Default 0 (uninitialized/indeterminate)")
        parser.add_argument("--RunHr", "-m", default=0.0, type=parse_negative_float, help="Runtime (hrs). Default 0.")
        parser.add_argument("--Shutdown", "-n", default=0, type=int, help="Shutdown bitmask as a 32-bit integer. Default 0.")
        parser.add_argument("--Speed", "-o", default=0.0, type=float, help="Drive speed. Default 0.")
        parser.add_argument("--Drive-Ready", "-q", action="store_true", help="Whether the drive is ready or not. Default False, use this to set to True")
        ####SWITCH FBD
        parser.add_argument("--Delay", "-u", default=-1, type=parse_negative_int, help="Switch timeout. Default -1, it appears that these switch timers run forever due to a bug.")

        args = parser.parse_args()
        selected_type = args.type
        
        # get device class
        DEVICE_CLASSES: Dict[str, Type[FBD]] = {
            'mv': MV_FBD, 'uv': UV_FBD, 'pmp': PMP_FBD, 'switch': SWITCH_FBD,
            'ain': AIN_FBD, 'fit': FIT_FBD, 'vsd': VSD_FBD, 'duty': Duty2_FBD
        }
        Device = DEVICE_CLASSES[selected_type]

        # capture only the attributes that belong to this device
        DEVICE_FIELDS: Dict[str, Tuple[str, ...]]  = {
            "mv": ("Open_TM", "Close_TM", "FTO", "FTC", "Open", "Close"),
            "uv": ("Start_TM", "Stop_TM", "Avl", "Fault", "FTS", "FTR", "RunHr", "Shutdown"),
            "pmp": ("Start_TM", "Stop_TM", "Avl", "Fault", "FTS", "FTR", "RunHr", "Shutdown"),
            "switch": ("Delay",),
            "ain": ("L_Raw_RIO", "HEU", "LEU", "Hty", "AHH", "AH", "AL", "ALL", "Wifi_Enb"),
            "fit": ("L_Raw_RIO", "HEU", "LEU", "Hty", "AHH", "AH", "AL", "ALL", "Wifi_Enb"),
            "vsd": ("Start_TM", "Stop_TM", "Avl", "Fault", "FTS", "FTR", "RunHr", "Shutdown", "Speed", "Drive_Ready"),
            "duty": ()
        }
        device_args = { 
            arg: param for arg, param in args.__dict__.items()
            if arg in DEVICE_FIELDS[selected_type] and arg not in { 
                "device", "type", "host", "port", "remote_devices",
                "io_delay", "plc_delay", "fbd_delay", "scada_delay",
                "start_time"
            }
        }

        # set the default values for unspecified ambiguous options (i.e. those shared by multiple device types)
        DEVICE_DEFAULTS: Dict[str, Dict[str, Union[int, float, bool]]] = {
            "ain": { "L_Raw_RIO": 0, "HEU": 1225.0, "Hty": True },
            "fit": { "L_Raw_RIO": -15, "HEU": 4.0, "Hty": False },
            "uv": { "Start_TM": 3, "Stop_TM": 3  },
            "pmp": { "Start_TM": 3, "Stop_TM": 3 },
            "vsd": { "Start_TM": 20, "Stop_TM": 20 }
        }
        device_args.update({
            arg: DEVICE_DEFAULTS[selected_type][arg]
            for arg, param in args.__dict__.items()
            if param is None and selected_type in DEVICE_DEFAULTS and arg in DEVICE_DEFAULTS[selected_type]
        })

        device = Device(
            start_time=args.start_time + args.fbd_delay, remote_devices=get_remote_ips(args.remote_devices),
            device_name=args.device_name, **device_args
        )

        # cleanup
        del parser, DEVICE_CLASSES, DEVICE_DEFAULTS, DEVICE_FIELDS, Device

        # start the device
        start_device(device, _host=args.host, _port=args.port)
    
    run_main()
