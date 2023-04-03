# We write plant odes here. The plant would "read" the IO from PLC and decide
# the set of ode functions it follows in the specific current 5 ms period.
from bitarray import bitarray
from modbus.tag import Tag
from modbus.base import BaseModbusDevice
from modbus.compat.builtins import asyncio
from modbus.compat.modbus import ModbusServerContext
from modbus.types.remote import RemoteDeviceType
from modbus.types import RegisterValue
from io_plc import IO_AIN_FIT, IO_SWITCH, IO_MV, IO_PMP_UV, VSD
from typing import Coroutine, Dict, List, Optional, Tuple, Type, TypeVar, Union
import scipy.integrate
import numpy as np

try:
    ODE_METHOD = scipy.integrate.DOP853.__name__    # preferred solver (python 3 / scipy 1.4+)
except ImportError:
    # available fall back solvers: LSODA, RK45, RK23, Radau, or BDF
    ODE_METHOD = scipy.integrate.LSODA.__name__     # fallback solver (python 2 / scipy <1.4)

#Yuqi, Ping-Fan
class Plant(BaseModbusDevice):
    PARAMS: Dict[str, Union[int, float]] = {
        "f_mv101":2.3e9/3600,   "f_mv201":2.0e9/3600,   "f_mv302":2.0e9/3600,   "f_mv501":2.0e9/3600,
        "f_mv502":0.00006111,   "f_mv503":0.00049,      "f_p101":2.0e9/3600,    "f_p301":2.0e9/3600,
        "f_p602":2.0e9/3600,    "f_p401":2.0e9/36001,   "f_p601":2.0e9/36001,   "omega_inlet":0.001,
        "S_t101":1.5e6,         "S_t301":1.5e6,         "S_t401":1.5e6,         "S_t601":1.5e6,
        "S_t601":1.5e6,         "S_t602":1.5e6,         "LIT101_AL":0.2,        "LIT101_AH":0.8,
        "LIT301_AL":0.2,        "LIT301_AH":0.8,        "LIT401_AL":0.2,        "LIT401_AH":0.8,
        "LIT601_AL":0.2,        "LIT601_AH":0.8,        "LIT602_AL":0.2,        "LIT602_AH":0.8,
        "cond_AIT201_AL":250,   "cond_AIT201_AH":260,   "cond_AIT503_AL":250,   "cond_AIT503_AH":260,
        "cond_AIT503_AH":260,   "orp_AIT203_AL":420,    "orp_AIT203_AH":500,    "orp_AIT402_AL":420,
        "orp_AIT402_AH":500,    "h201_AL":50,           "h202_AL":4,            "h203_AL":15,
        "ph_AIT202_AL":6.95,    "ph_AIT202_AH":7.05
    }
    """Critical plant parameters"""

    PARAMS_PC: Dict[str, float] = {
        'p1_mv':   PARAMS['f_mv101'] / PARAMS['S_t101'], 'p1_p':     PARAMS['f_p101']  / PARAMS['S_t101'],
        'p2':      PARAMS['f_mv201'] / PARAMS['S_t301'], 'p3_run':   PARAMS['f_p301']  / PARAMS['S_t301'],
        'p3_uf':   PARAMS['f_mv302'] / PARAMS['S_t401'], 'p3_ufbw':  PARAMS['f_p602']  / PARAMS['S_t602'],
        'p4_draw': PARAMS['f_p401']  / PARAMS['S_t401'], 'p4_n601':  PARAMS['f_mv501'] / PARAMS['S_t601'],
        'p4_n602': PARAMS['f_mv502'] / PARAMS['S_t602'], 'p4_flush': PARAMS['f_mv503'] / PARAMS['S_t602'],
        'p6_run':  PARAMS['f_p601']  / PARAMS['S_t601']
    }
    """Precomputed dictionary for speeding up ODE function"""

    TAG_NAMES = ("time_UF", "h_c", "h_t101", "h_t301", "h_t401", "h_t601", "h_t602")
    """List of tags for use by client thread"""

    def __init__(self, start_state, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = np.array([0.0, 0, 550, 550, 550, 200, 200] if start_state is None else start_state)
        self._last_state: Optional[bitarray] = None
        self.cumulative_time: float = 0
        #print("Remote tag names:", Comms.REMOTE_TAG_NAMES) # for debugging
        # self.result[2:5] += np.random.random(3)
        
    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        return super().get_tags(
            *(Tag(tag_name, bool) for tag_name in Comms.REMOTE_TAG_NAMES),
            *(Tag(tag_name, float) for tag_name in Plant.TAG_NAMES), 
            *tags
        )

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        """ k is the total steps counted every 5 ms   --PF """
        
        remote_tags = self.get_tag_values(Comms.REMOTE_TAG_NAMES)
        self.result = scipy.integrate.solve_ivp(
            fun=Plant.ODE, y0=self.result, t_span=(0, time_interval),
            args=remote_tags, t_eval=(time_interval,), method=ODE_METHOD
        ).y.flatten()
        self.cumulative_time += time_interval
        self.set_tag_values(*zip(Plant.TAG_NAMES, self.result))
        str_arr = ''.join((f'{int(i)}' for i in remote_tags))
        new_state = bitarray(str_arr)
        if self._last_state != new_state:
            # print out result, time interval and bool values on change
            self._last_state = new_state
            print(self.result, f"{self.cumulative_time:.5f}", f"[{str_arr}]")
        
    @staticmethod
    def ODE(y, t, 
        # DI_Run tags of remote pumps and variable speed drives
        IOP101_DI_Run: bool,  IOP102_DI_Run: bool,  IOP301_DI_Run: bool,  IOP302_DI_Run: bool,  IOP401_DI_Run: bool,
        IOP402_DI_Run: bool,  IOP601_DI_Run: bool,  IOP602_DI_Run: bool,  IOP501_DI_Run: bool,  IOP502_DI_Run: bool,
        # DI_ZSO tags of remote motors
        IOMV101_DI_ZSO: bool, IOMV201_DI_ZSO: bool, IOMV301_DI_ZSO: bool, IOMV302_DI_ZSO: bool, IOMV303_DI_ZSO: bool,
        IOMV304_DI_ZSO: bool, IOMV501_DI_ZSO: bool, IOMV502_DI_ZSO: bool, IOMV503_DI_ZSO: bool, IOMV504_DI_ZSO: bool,
        # DI_ZSC tags of remote motors. Not all of these are used, but are left to preserve order of arguments.
        IOMV101_DI_ZSC: bool, IOMV201_DI_ZSC: bool, IOMV301_DI_ZSC: bool, IOMV302_DI_ZSC: bool, IOMV303_DI_ZSC: bool,
        IOMV304_DI_ZSC: bool, IOMV501_DI_ZSC: bool, IOMV502_DI_ZSC: bool, IOMV503_DI_ZSC: bool, IOMV504_DI_ZSC: bool
    ) -> Tuple[float, float, float, float, float, float, float]:
            """ The ODEs should be reset to 0 after 1 cycle --PF Jan 25 """
            
            params_pc = Plant.PARAMS_PC
            time_UF = h_t101 = h_t301 = h_t401 = h_t601 = h_t602 = 0.0
            
            if IOMV101_DI_ZSO:
                h_t101 += params_pc['p1_mv']

            if IOP101_DI_Run or IOP102_DI_Run:
                # IOP101, drawing water from tank101
                h_t101 -= params_pc['p1_p']

            if IOMV201_DI_ZSO and IOP101_DI_Run:
                # mv201, feeding water to tank301
                h_t301 += params_pc['p2']

            p3_running = IOP301_DI_Run or IOP302_DI_Run
            if p3_running: #p301, drawing water from tank301
                h_t301 -= params_pc['p3_run']

            if IOMV301_DI_ZSC and IOMV302_DI_ZSC and IOMV303_DI_ZSC and not IOP602_DI_Run:
                # replace DI_ZSO with DO_ZSO if things go wrong - do_zso originally used in source code
                if p3_running and IOMV304_DI_ZSO: #UF flushing procedure, 30 sec
                    time_UF = (time_UF * 8) + 1 # equiv. of "y0=0"...+"1"+"1"
                elif not p3_running and IOMV304_DI_ZSO:   #UF feed tank draining procedure, 1 min
                    time_UF = (time_UF * 8) + 1 # equiv. of "y0=0"...+"1"+"1"

            if p3_running and IOMV301_DI_ZSC and IOMV302_DI_ZSO and IOMV303_DI_ZSC and IOMV304_DI_ZSC and not IOP602_DI_Run:
                #UF ultra filtration procedure, 30 min
                h_t401 += params_pc['p3_uf']
            elif not p3_running and IOMV301_DI_ZSO and IOMV302_DI_ZSC and IOMV303_DI_ZSO and IOMV304_DI_ZSC and IOP602_DI_Run:
                #UF back wash procedure, 45 sec
                h_t602 -= params_pc['p3_ufbw']

            if IOP401_DI_Run or IOP402_DI_Run:
                #IOP401, drawing water from t401
                h_t401 -= params_pc['p4_draw']
                if IOP501_DI_Run or IOP502_DI_Run:
                    if IOMV501_DI_ZSO and IOMV502_DI_ZSO and IOMV503_DI_ZSC and IOMV504_DI_ZSC:
                        #procedure for RO normal functioning with product of permeate 60% and backwash 40%
                        h_t601 += params_pc['p4_n601']
                        h_t602 += params_pc['p4_n602']
                    elif IOMV501_DI_ZSC and IOMV502_DI_ZSC and IOMV503_DI_ZSO and IOMV504_DI_ZSO:
                        #procedure for RO flushing with product of backwash 60% and drain 40%
                        h_t602 += params_pc['p4_flush']
            
            if IOP601_DI_Run:
                # Pumping water out of tank601
                h_t601 -= params_pc['p6_run']

            return time_UF, 0.0, h_t101, h_t301, h_t401, h_t601, h_t602

    ODE_T = TypeVar('ODE_T', float, np.ndarray)
    """Type variable for numerical computations"""

    # The sensors would return values not in physical unit. e.g.
    # 0.7 meter tank level would be returned by ultrasonic level
    # sensor to PLC as some value like 32940.

    @staticmethod
    def usl_w(level: ODE_T) -> ODE_T: #ultrasonic level sensor, wireless
        return (level - 0.0) * (-31208.0/1225.0) + 31208

    @staticmethod
    def usl(level: ODE_T) -> ODE_T: #ultrasonic level sensor
        return (level - 0.0) * (float(3277-16383)/1225.0) + 16383

    @staticmethod
    def fi_w(flow: ODE_T) -> ODE_T: #flow indicator, wireless
        return (flow - 0.0) * (float(-15-31208)/10.0) + 31208

    @staticmethod
    def fi(flow: ODE_T) -> ODE_T: #flow indicator
        return (flow - 0.0) * (float(3277-16383)/10.0) + 16383

class Comms:
    TRANSMITTERS: Tuple[RemoteDeviceType, ...] = tuple(
        RemoteDeviceType(dev) for dev in ("IOLIT101", "IOLIT301", "IOLIT401")
    )
    SWITCHES: Tuple[RemoteDeviceType, ...] = tuple(
        RemoteDeviceType(dev) for dev in ("IOLSL601", "IOLSH601", "IOLSL602", "IOLSH602")
    )
    PUMPS: Tuple[RemoteDeviceType, ...] = tuple(RemoteDeviceType(dev) for dev in
        ("IOP101", "IOP102", "IOP301", "IOP302", "IOP401", "IOP402", "IOP601", "IOP602")
    )
    VSDS: Tuple[RemoteDeviceType, ...] = tuple(
        RemoteDeviceType(dev) for dev in ("IOP501", "IOP502")
    )
    MOTORS: Tuple[RemoteDeviceType, ...] = tuple(RemoteDeviceType(dev) for dev in (
        "IOMV101", "IOMV201", "IOMV301", "IOMV302", "IOMV303",
        "IOMV304", "IOMV501", "IOMV502", "IOMV503", "IOMV504"
    ))
        
    REMOTE_TAG_NAMES: Tuple[str, ...] = \
        tuple("{0}_DI_Run".format(dev) for dev in PUMPS) + tuple("{0}_DI_Run".format(dev) for dev in VSDS) + \
        tuple("{0}_DI_ZSO".format(dev) for dev in MOTORS) + tuple("{0}_DI_ZSC".format(dev) for dev in MOTORS)
    """List of digital (int) tags used by the ODE function"""

class LivePoller(BaseModbusDevice):
    def __init__(self, shared_data_store, *args, **kwargs):
        self.shared_ds = shared_data_store
        self.result = np.array([0.0, 0, 550, 550, 550, 200, 200])
        super().__init__(*args, **kwargs)
        
    def create_context(self) -> ModbusServerContext:
        return self.shared_ds
        
    def get_device_classes(self, **kwargs: Type) -> Dict[RemoteDeviceType, Type]:
        return super().get_device_classes(
            **{device_name: IO_AIN_FIT  for device_name in Comms.TRANSMITTERS},
            **{device_name: IO_SWITCH   for device_name in Comms.SWITCHES    },
            **{device_name: IO_PMP_UV   for device_name in Comms.PUMPS       },
            **{device_name: IO_MV       for device_name in Comms.MOTORS      },
            **{device_name: VSD         for device_name in Comms.VSDS        },
        )

    @classmethod
    def get_tags(cls, *tags: Tag) -> Tuple[Tag, ...]:
        # delegate plant's get_tags method as they share the same tags and storage
        return Plant.get_tags(*tags)

    async def get_pump_value(self, pump):
        val = await self.ask_device(pump, "DI_Run")
        return RemoteDeviceType("{0}_DI_Run".format(pump)), val

    async def get_motor_values(self, motor):
        DI_ZSO, DI_ZSC = await self.ask_device(motor, "DI_ZSO", "DI_ZSC")
        return (
            (RemoteDeviceType("{0}_DI_ZSO".format(motor)), DI_ZSO),
            (RemoteDeviceType("{0}_DI_ZSC".format(motor)), DI_ZSC)
        )

    async def _main_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
        # converting physical value to sensor readings, get
        # plant data from plant thread via modbus datablock
        motor_tag_values, pump_values = await asyncio.gather(
            asyncio.gather(*(self.get_motor_values(motor) for motor in Comms.MOTORS)),
            asyncio.gather(*(self.get_pump_value(pump) for pump in Comms.PUMPS))
        )

        motor_values: List[Tuple[RemoteDeviceType, RegisterValue]] = []
        for tags in motor_tag_values:
            motor_values.extend(tags)

        # set tag values here for plant ODE to use
        self.set_tag_values(*pump_values, *motor_values)
        new_state = np.array(self.get_tag_values(*Plant.TAG_NAMES))

        tasks: List[Coroutine] = []
        for dev, value, w_value in zip(
            Comms.TRANSMITTERS, Plant.usl(new_state[2:5]), Plant.usl_w(new_state[2:5])
        ):
            tasks.append(self.tell_device(dev, ("AI_Value", value), ("W_AI_Value", w_value)))

        params = Plant.PARAMS
        for dev, value in zip(Comms.SWITCHES, (
            new_state[5] < params["LIT601_AL"], new_state[5] > params["LIT601_AH"], 
            new_state[6] < params["LIT601_AL"], new_state[6] > params["LIT601_AH"]
        )):
            tasks.append(self.tell_device(dev, ("DI_LS", value)))

        await asyncio.gather(*tasks)
