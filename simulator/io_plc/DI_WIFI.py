from typing import Literal, Tuple

class DI_WIFI: # self.RIO represents a switch, if it's 1`, then PLC processes wireless signal.
	def __init__(self):
		self.RIO: Tuple[int, int, int, int, int, int] = (0,) * 6
	def get(self, id: Literal[1,2,3,4,5,6]) -> bool:
		return bool(self.RIO[id - 1])