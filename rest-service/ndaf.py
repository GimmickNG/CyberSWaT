from datetime import datetime
from marshmallow import Schema, fields, ValidationError, post_load
from io import BytesIO
import numpy as np
import base64

def serialize(value):
    xbytes = BytesIO()
    np.save(xbytes, value, allow_pickle=False)
    xbytes.seek(0)
    # since it is arbitrary data, which won't work in
    # unicode, encode to base64 first then to unicode
    zbytes = base64.b64encode(xbytes.read())
    return zbytes.decode()

def deserialize(value):
    try:
        xbytes = BytesIO()
        raw_value = base64.b64decode(value.encode())
        xbytes.write(raw_value)
        xbytes.seek(0)
        return np.load(xbytes, allow_pickle=False)
    except Exception as err:
        raise ValidationError("Failed to validate tensor") from err

class NDArrayField(fields.Field):
    def _serialize(self, value, *args, **kwargs):
        return serialize(value)
    def _deserialize(self, value, *args, **kwargs):
        return deserialize(value)

class NDArrayTx:
    def __init__(self, api_key, start_time, data_by_time):
        self.api_key = api_key
        self.start_time = start_time
        self.data_by_time = data_by_time

class NDArrayTxSchema(Schema):
    api_key = fields.Str()
    start_time = fields.Float()
    data_by_time = fields.Dict(keys=fields.Float(), values=NDArrayField())

    @post_load
    def make_array(self, data, **kwargs):
        return NDArrayTx(api_key=data['api_key'], start_time=data['start_time'], data_by_time=data['data_by_time'])
