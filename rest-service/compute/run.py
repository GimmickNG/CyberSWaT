from rpyc.utils.server import ThreadedServer
import onnxruntime as ort
import numpy as np
import threading
import tempfile
import rpyc
rpyc.core.protocol.DEFAULT_CONFIG['allow_pickle'] = True

class ComputeService(rpyc.Service):
    
    ALIASES = ["ComputeNode", "RemoteNode"]

    def __init__(self, timeout, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_timeout = timeout
        self.sessions = {}  # indexed by api key

    def create_timer(self, api_key, timeout):
        thread = threading.Timer(timeout, self.exposed_unregister, args=[api_key])
        self.sessions[api_key]["timeout"] = thread
        thread.start()

    def cancel_timer(self, api_key):
        if "timeout" in self.sessions[api_key]:
            self.sessions[api_key]["timeout"].cancel() # cancel timeout and start new one
    
    def exposed_unregister(self, api_key):
        if api_key in self.sessions:
            session = self.sessions[api_key]
            session["temp_file"].close()
            self.cancel_timer(api_key)
            del self.sessions[api_key]

    def exposed_register(self, api_key, model_path, timeout=None):
        if api_key not in self.sessions:
            sess_opt = ort.SessionOptions()
            temp_optim = tempfile.NamedTemporaryFile()
            sess_opt.optimized_model_filepath = temp_optim.name
            session = ort.InferenceSession(model_path, sess_opt, providers=['CPUExecutionProvider'])
            self.sessions[api_key] = {
                "options": sess_opt,
                "temp_file": temp_optim,
                "session": session,
            }
        
        self.cancel_timer(api_key)
        self.create_timer(api_key, timeout or self.default_timeout)

    def exposed_predict(self, api_key, input_array): # this is an exposed method
        result = self.sessions[api_key]["session"].run(None, {'input': np.array(input_array)} )
        return result[0].tolist()
        

if __name__ == "__main__":
    service = rpyc.ThreadedServer(ComputeService(3600), port=18861, auto_register=True, protocol_config = rpyc.core.protocol.DEFAULT_CONFIG)
    service.start()
