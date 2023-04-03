import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set, Tuple
import pandas as pd
import base64
import time
import io
import json
import argparse
import numpy as np
import contextlib
import signal

class ICSState:
    WINDOW = 0
    SAMPLE = 1
    def __init__(self, dataset: pd.DataFrame, window_size:int, type:int = 0, frequency:float = 1):
        self.dataset = dataset
        # subtract 1 since slice indexing is inclusive range
        self.window_size = window_size #timedelta(seconds=window_size - 1)
        self.type = type
        self.frequency = frequency

    def get(self, time=None):
        if self.type == ICSState.WINDOW:
            return self.get_window(time=time)
        return self.get_sample(time=time)

    def get_time(self):
        return get_time(self.frequency) #pd.Timestamp.now().replace(microsecond=0)

    def get_window(self, time=None) -> np.ndarray:
        if time is None:
            time = self.get_time()
        arr = self.dataset.loc[1 + time - self.window_size: time].to_numpy(float)
        return np.expand_dims(arr, 1)
        
    
    def get_sample(self, time=None) -> np.ndarray:
        if time is None:
            time = self.get_time()

        try:
            return np.expand_dims(
                self.dataset.loc[time].to_numpy(float), 1
            )
        except KeyError:
            return np.zeros((1, 1, 0))

def get_time(frequency, curr_time=None) -> int:
    if curr_time is None:
        curr_time = time.time() 
    return int(curr_time * frequency)

def create_states(window_size: int, start_time:int, use_sample:bool = False, frequency:float = 1.0) -> Tuple[int, ICSState]:
    # load swat attack dataset for testing
    swat_test = pd.read_csv("hist_data.csv")
    start_time = int(get_time(frequency, curr_time=start_time))
    swat_test.index += start_time - window_size
    return start_time, ICSState(
        swat_test,
        frequency=frequency,
        window_size=window_size,
        type=ICSState.SAMPLE if use_sample else ICSState.WINDOW
    )

def create_parser():
    parser = argparse.ArgumentParser(description="Simulated Client")
    parser.add_argument("--show-sent", "-s", action="store_true", help="Prints out the sent array")
    parser.add_argument("--show-received", '-r', action="store_true", help="Prints out the received array")
    parser.add_argument("--show-loss", "-l", action="store_true", help="Prints out the loss from the most recent input (i.e. last value)")
    parser.add_argument("--sample", "-n", action="store_true", help="Sends only a single state at a time")
    parser.add_argument("--file", "-f", default="losses.csv", help="Path to save losses file")
    parser.add_argument("--rtt-file", "-e", default="rtt.csv", help="Path to save RTT info")
    return parser.parse_args()

def load_data():
    with open("../ip_list.json", "r") as ip_list, open("../server_settings.json", "r") as settings:
        remote_address = json.load(ip_list)["IP"]["rem_r"]
        settings_data = json.load(settings)
    return remote_address, settings_data

def encode_request(arr):
    xbytes = io.BytesIO()
    np.save(xbytes, arr, allow_pickle=False)
    xbytes.seek(0)
    return base64.b64encode(xbytes.read()).decode()

def decode_response(json_data) -> Dict[str, np.ndarray]:
    """Parses response data"""

    out_data = {}
    data = json_data['data']
    for active_time, value in data.items():
        xbytes = io.BytesIO()
        raw_array = base64.b64decode(value.encode())
        xbytes.write(raw_array)
        xbytes.seek(0)
        out_data[active_time] = np.squeeze(np.load(xbytes, allow_pickle=False))
    return out_data

if __name__ == "__main__":
    args = create_parser()
    remote_address, settings = load_data()
    
    api_key = settings['key']
    frequency = settings['frequency']
    start_time = settings['start_time']
    url = "http://%s/predict" % remote_address
    show_sent, iter_samples = args.show_sent, args.sample
    show_received, loss = args.show_received, args.show_loss

    with open(args.file, 'w') as losses_file:
        losses_file.write("Time (Relative),Loss\n")
    with open(args.rtt_file, 'w') as rtt_file:
        rtt_file.write("Time (Relative),RTT,% (relative to frequency)\n")
    losses_file = open(args.file, 'a', 1)
    rtt_file = open(args.rtt_file, 'a', 1)

    BASE_LOOKAHEAD = 10
    REQ_TIMEOUT = BASE_LOOKAHEAD/frequency
    TO_SEND: Dict[int, str] = {}
    TIME_BUFFER: Dict[str, np.ndarray] = {}
    
    async def start_task(delay:float, session:aiohttp.ClientSession, state_getter:ICSState, frequency:float = 1):
        await asyncio.sleep(delay)
        arr = state_getter.get()

        if len(arr) >= state_getter.window_size:
            # generate and encode data
            to_send = encode_request(arr)

            if show_sent:
                disp_arr = np.squeeze(arr)

            # send encoded data
            current_time = get_time(frequency)
            TO_SEND[current_time + BASE_LOOKAHEAD] = to_send
            for key in [time for time in TO_SEND.keys() if time < current_time]:
                del TO_SEND[key]

            json_data = {
                'api_key': api_key,
                'start_time': current_time,
                'data_by_time': TO_SEND
            }
            try:
                rtt = time.perf_counter()
                async with session.post(url, timeout=REQ_TIMEOUT, json=json_data) as response:
                    rtt = time.perf_counter() - rtt
                    pct = rtt * frequency # rtt / (1 / frequency)
                    rtt_file.write(f"{current_time},{rtt:.4f},{pct}\n")
                    
                    #TODO why is this not writing?
                    # get and decode response(s)
                    results = decode_response(await response.json())
                    for desired_time, value in results.items():
                        TIME_BUFFER[desired_time] = value
                        del TO_SEND[int(desired_time)]
            except asyncio.TimeoutError:
                return

        # pick value from time buffer every second for comparison
        current_time = str(get_time(frequency))
        if current_time in TIME_BUFFER:
            result = TIME_BUFFER.pop(current_time)
            diff = np.squeeze(arr)
            if not iter_samples:
                diff = diff[-1]
            diff = result - diff
            loss_val = (diff**2).mean()
            losses_file.write(f"{current_time},{loss_val}\n")
            
    async def shutdown(loop):
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()

    async def main():
        global start_time
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, lambda *_: asyncio.create_task(shutdown(loop)))
        try:
            async with aiohttp.ClientSession() as session:
                start_time, states = create_states(window_size=120, start_time=start_time, use_sample=args.sample, frequency=frequency)
                start_time += BASE_LOOKAHEAD
                num_workers = 4
                for i in range(0, len(states.dataset), num_workers):
                    await asyncio.gather(*[
                        start_task((sample_time - (time.time() * frequency)) / frequency, session, states, frequency)
                    for sample_time in states.dataset.index[i:i+num_workers]], return_exceptions=True)
        except aiohttp.ClientConnectorError as err:
            print(*err.args)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(main())
    losses_file.close()
    rtt_file.close()
