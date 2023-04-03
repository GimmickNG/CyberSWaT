from typing import List, Optional, Tuple, Type, Union
from .base_fbd import FBD
from modbus.base import BaseModbusClient, BaseModbusDevice
from modbus.tag import Tag

class Duty2_FBD(FBD):
	def init_fbd(self, *args, **kwargs) -> None:
		self.Start_Pmp1: bool = False
		self.Start_Pmp2: bool = False
		self.Pump_Running: bool = False
		
	def _set_pumps(self, p1: Union[bool, int], p2: Union[bool, int], avl: Optional[Union[bool, int]] = None):
		self.Start_Pmp1 = bool(p1)
		self.Start_Pmp2 = bool(p2)
		if avl is not None:
			self.Selected_Pmp_Not_Avl = avl

	@classmethod
	def get_tags(cls: Type[BaseModbusDevice], *tags: Tag) -> Tuple[Tag, ...]:
		# rewrite wherever Duty2FBD appears in PLCs to 
		# send PMP1_avl values to duty2 instead of duty2 "asking"
		# PMP1 and 2 as these are HMIs and not IO devices
		# n.b. appears to be done; TODO check if done correctly

		return super().get_tags(
			Tag("PMP1_Avl", bool),				Tag("PMP1_Status", int),
			Tag("PMP2_Avl", bool),  			Tag("PMP2_Status", int),
			Tag("Selection", bool),				Tag("Start_Pmp1", bool),
			Tag("Start_Pmp2", bool),			Tag("Selected_Pmp_Not_Avl", bool),
			Tag("Pump_Running", bool),			Tag("AutoInp", bool), 
			*tags
		)

	async def _fbd_loop(self, sec_pulse, min_pulse, hrs_pulse, time_interval, **kwargs) -> None:
		self.Pump_Running = (self.PMP1_Status == 2 or self.PMP2_Status == 2)
		
		if self.AutoInp:
			pump_avls = [int(self.PMP1_Avl and not self.PMP2_Avl), int(self.PMP2_Avl and not self.PMP1_Avl)]
			self._set_pumps(*pump_avls, avl=not pump_avls[int(self.Selection)])
		else:
			self._set_pumps(False, False)
