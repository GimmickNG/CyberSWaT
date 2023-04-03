from typing import Literal, Optional, Tuple
from modbus.compat.builtins import bitarray, int2ba, ba2int
import sys

def XSETD(a: bool, b: bool) -> Optional[bool]:
	# returns new SETD value without needing to know initial value.
	# n.b. set value only if return is not None
	if b: #if unset is set, must stop
		return False
	elif a:# else if set is set, can run
		return True
	return None

def ALM(in_sig: float, a_hh: float, a_h: float, a_l: float, a_ll: float) -> Tuple[bool, bool, bool, bool]:
	d = (in_sig < a_ll)
	c = (in_sig < a_l)
	b = (in_sig > a_h)
	a = (in_sig > a_hh)
	return a,b,c,d

def SCL(In: float, InRawMax: float, InRawMin: float, InEuMax: float, InEuMin: float):
	return (In - InRawMin) * float(InEuMax-InEuMin)/float(InRawMax-InRawMin) + InEuMin

class TONR:
	"""PLC On delay (retentive?) timer class"""

	def __init__(self, preset: int, frequency:int = 200):
		# multiply by `frequency` to count every `frequency`
		# times in a second (200Hz => 5 miliseconds)
		self.preset: int = preset * frequency
		self.DN: bool = False
		self.Acc: int = 0

	def tick(self, TimerEnable: bool):
		if self.Acc >= self.preset:
			self.Acc = 0
			self.DN = True
		else:		
			self.DN = False
			if TimerEnable:
				self.Acc += 1
			else:
				self.Acc = 0

def create_bitarray(size: int, default_value: Literal[0, 1]) -> bitarray:
    ba = bitarray(size, endian=sys.byteorder)
    ba.setall(default_value)
    return ba
	
def signed_integer_2_bit(value: int) -> bitarray:
	try:
		return int2ba(value, 32, endian=sys.byteorder, signed=True)
	except TypeError as err:
		raise ValueError("got value of {}".format(value)) from err
	
def bit_2_signed_integer(arr):
    return ba2int(arr, True)