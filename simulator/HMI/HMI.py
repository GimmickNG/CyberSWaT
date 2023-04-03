from modbus.compat.builtins import bitarray
from .base_hmi import BaseHMI
from modbus.helpers import create_contiguous_states

# these three belong mainly to scada / plc rather than fbd
class HMI_phase:
    def __init__(self):
        self.Permissive_On: bool = True
        self.Shutdown: bool = True
        self.State: int    = 1
        self.Ready: bool    = False
        self.TMP_High: bool = False

class HMI_Ultrafiltration_Cycle(BaseHMI):
    STATES = create_contiguous_states(1, 20, {
        1: bitarray('00000'),
        4: bitarray('10000'),
        5: bitarray('00000'),
        7: bitarray('01000'),
        8: bitarray('00000'),
        12: bitarray('00100'),
        13: bitarray('00000'),
        16: bitarray('00001'),
        17: bitarray('00000'),
        18: bitarray('00010'),
        99: bitarray('00000')
    })

    def init_hmi(self, *args, **kwargs):
        self.UF_REFILL_SEC: int = 0
        self.UF_FILTRATION_MIN: int = 0
        self.BACKWASH_SEC: int = 0
        self.CIP_CLEANING_SEC: int = 0
        self.DRAIN_SEC: int = 0
        self.UF_FILTRATION_MIN: int = 0

        self.UF_FILTRATION_MIN_SP: int = 3 # original value is 30 min, lets put it shorter so to cater test time budget
        self.BACKWASH_SEC_SP: int = 30
        self.DRAIN_SEC_SP: int = 30
        self.UF_REFILL_SEC_SP: int = 30
        self.BW_CNT: int = 0
        self.CIP_CLEANING_SEC_SP: int = 0
        
        self._state: int = 0

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        if self._state in HMI_Ultrafiltration_Cycle.STATES:
            state_vars = (
                self.UF_REFILL_SEC, self.UF_FILTRATION_MIN, 
                self.BACKWASH_SEC, self.CIP_CLEANING_SEC, self.DRAIN_SEC
            )
            
            self.UF_REFILL_SEC, self.UF_FILTRATION_MIN, self.BACKWASH_SEC, \
                self.CIP_CLEANING_SEC, self.DRAIN_SEC = \
                    (val * state_vars[i] for i, val in enumerate(
                        HMI_Ultrafiltration_Cycle.STATES[self._state])
                    )
            
            if not sec_pulse:
                return
            elif self._state == 4:
                self.UF_REFILL_SEC += 1
            elif self._state == 12:
                self.BACKWASH_SEC += 1
            elif self._state == 16:
                self.DRAIN_SEC += 1
            elif self._state == 18:
                self.CIP_CLEANING_SEC += 1
        else:
            self._state = 1


class HMI_ReverseOsmosis_Cycle(BaseHMI):
    STATES = create_contiguous_states(1, 22, {
         1: bitarray('000000000'),
         4: bitarray('010010000'),
         5: bitarray('000000000'),
        15: bitarray('000000001'),
        16: bitarray('000000100'),
        17: bitarray('000000010'),
        18: bitarray('000001000'),
        19: bitarray('001000000'),
        20: bitarray('100000000'),
        21: bitarray('000000011')
    })

    def init_hmi(self, *args, **kwargs):
        self.RO_TMP: float = 0.0
        self.HPP_Q_MAX_M3H: float = 0.0
        self.HPP_Q_SET_M3H: float = 0.0
        self.MIN_RO_VSD_SPEED: float = 0.0
        self.RAMPING_RATE_PER_SEC: float = 0.0
        self.VSD_MIN_SPEED: float = 0.0
        self.VSD_HIGH_SPEED: float = 0.0
        self.MV501_TIMEOUT_TM: int = 0
        self.MV502_TIMEOUT_TM: int = 0
        self.MV503_TIMEOUT_TM: int = 0
        self.MV504_TIMEOUT_TM: int = 0
        self.RO_SD_FLUSHING_MIN: int = 0
        # setpoint is undefined in original; set to 0 as default
        self.RO_SD_FLUSHING_MIN_SP: int = 0
        self.FLUSHING_MIN: int = 0
        self.FLUSHING_MIN_SP: int = 2 # temporarily set to this value
        self.RO_HPP_SD_On: bool = False
        self.RO_HIGH_PUMP_Shutdown: bool = False
        self.SD_FLUSHING_DONE_On: bool = False
        self._state = 0

    async def _main_loop(self, sec_pulse: bool, min_pulse: bool, hrs_pulse: bool, time_interval: float) -> None:
        if self._state in HMI_ReverseOsmosis_Cycle.STATES:
            state_data = HMI_ReverseOsmosis_Cycle.STATES[self._state]
            self.RO_HPP_SD_On = bool(state_data[0])
            self.FLUSHING_MIN *= state_data[1]
            self.RO_SD_FLUSHING_MIN *= state_data[2]
            self.RO_HIGH_PUMP_Shutdown &= bool(state_data[3])
            self.SD_FLUSHING_DONE_On &= bool(state_data[4])
            self.MV501_TIMEOUT_TM *= state_data[5]
            self.MV502_TIMEOUT_TM *= state_data[6]
            self.MV503_TIMEOUT_TM *= state_data[7]
            self.MV504_TIMEOUT_TM *= state_data[8]

            if min_pulse:
                if self._state == 4:
                    self.FLUSHING_MIN += 1
                elif self._state == 19:
                    self.RO_SD_FLUSHING_MIN += 1
            if sec_pulse:
                if self._state == 15:
                    self.MV504_TIMEOUT_TM += 1
                elif self._state == 16:
                    self.MV502_TIMEOUT_TM += 1
                elif self._state == 17:
                    self.MV503_TIMEOUT_TM += 1
                elif self._state == 21:
                    self.MV503_TIMEOUT_TM += 1
                    self.MV504_TIMEOUT_TM += 1
        else:
            self._state = 1
