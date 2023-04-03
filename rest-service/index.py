#from datetime import timedelta
from flask import Flask, jsonify, request, make_response
from .ndaf import *
import json
import numpy as np
import pandas as pd
import time
import random

with open("lookaheads.csv", "w") as lookaheads_used:
    lookaheads_used.write("Time,Lookahead\n")
lookaheads_used = open("lookaheads.csv", "a", 1)

with open("../server_settings.json", "r") as settings:
    data = json.load(settings)
    API_KEY = data['key']
    START_TIME = data['start_time']
    FREQUENCY = data['frequency']

def get_time(frequency, curr_time=None):
    if curr_time is None:
        curr_time = time.time()
    return int(curr_time * frequency)

def load_lookahead(window_size, lookahead, start_time, frequency):
    try:
        df = pd.read_hdf("./compute/precomputed.hdf", key=str(lookahead))
        df.index += (start_time - window_size) + lookahead - 1
        return df
    except:
        # user has not replaced precomputed.hdf
        raise ValueError("Incorrect precomputed.hdf - replace with HDF file.")

RESULTS = {
    API_KEY: {
        key: load_lookahead(
            window_size=120, lookahead=key, frequency=FREQUENCY,
            start_time=get_time(FREQUENCY, START_TIME)
        ) for key in (1, 2, 4, 8, 10)
    }
}

app = Flask(__name__)

@app.route("/")
def status():
    return make_response(("If you are seeing this, the remote endpoint is running properly.\n", 200))

@app.route("/predict", methods=['POST'])
def run_prediction():
    request_data = NDArrayTxSchema().load(request.get_json())
    api_key, start_time = request_data.api_key, request_data.start_time
    data_by_time = request_data.data_by_time

    data = {}
    lookaheads = []
    for desired_time, _ in data_by_time.items():
        lookahead = int(desired_time - start_time)
        if api_key not in RESULTS or lookahead not in RESULTS[api_key]:
            continue
        lookaheads_used.write("%i,%i\n" % (int(start_time), lookahead))
        #output = RESULTS[api_key][lookahead].loc[desired_time].to_numpy(float)

        # simulate running inference on gpu by waiting for the time taken
        # since it's more consistent and can be run on cpu as well
        time.sleep(random.normalvariate(0.0139, 0.0007))

        lookaheads.append(lookahead)
        #data[int(desired_time)] = serialize(output)
    status = 200 if len(data) else 400
    return jsonify({
        "timestamp": time.time(),
        "lookahead": lookaheads,
        "data": data
    }), status