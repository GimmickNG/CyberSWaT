from typing import Tuple
from .compat.builtins import perf_counter

class BaseCounter(object):
    def __init__(self, length, *args, **kwargs):
        self.run_forever = length <= 0
        self.length = length

    def __iter__(self):
        self.init_vars()
        return self

    def next(self):
        self.update()
        return self.get_pulse()

    def __next__(self):
        return self.next()

    def is_over(self) -> bool:
        return not self.run_forever and self.elapsed_time > self.length

    def init_vars(self) -> None:
        self.elapsed_time = 0
    
    def get_elapsed(self) -> float:
        return self.elapsed_time

    def update(self) -> None:
        pass

    def get_pulse(self) -> Tuple[bool, bool, bool, float]:
        return (False, False, False, 0)

class RealtimeCounter(BaseCounter):
    def init_vars(self):
        super(RealtimeCounter, self).init_vars()
        self.last_time = self.curr_time = self.init_time = self.last_sec_pulse = self.last_min_pulse = self.last_hour_pulse = perf_counter()
    
    def update(self) -> None:
        # TODO determine if counter that includes sleep time should be used or not
        self.last_time, self.curr_time = self.curr_time, perf_counter()
        self.elapsed_time = self.curr_time - self.init_time

    def get_pulse(self) -> Tuple[bool, bool, bool, float]:
        curr_time = self.curr_time
        sec_pulse = (curr_time - self.last_sec_pulse) > 1
        min_pulse = (curr_time - self.last_min_pulse) > 60
        hrs_pulse = (curr_time - self.last_hour_pulse) > 3600
        if sec_pulse:
            self.last_sec_pulse = curr_time
        if min_pulse:
            self.last_min_pulse = curr_time
        if hrs_pulse:
            self.last_hour_pulse = curr_time
        return sec_pulse, min_pulse, hrs_pulse, (curr_time - self.last_time)

class SimCounter(BaseCounter):
    def __init__(self, length, time_interval, *args, **kwargs):
        super(SimCounter, self).__init__(int(length / time_interval))
        self.time_interval = time_interval
    
    def update(self) -> None:
        self.elapsed_time += self.time_interval

    def get_pulse(self) -> Tuple[bool, bool, bool, float]:
        time, time_interval = self.elapsed_time, self.time_interval
        return not bool(time%(1/time_interval)), not bool(time%(60/time_interval)), not bool(time%(3600/time_interval)), time_interval