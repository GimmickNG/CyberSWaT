IS_UNIX_PORT: bool = False
"""
Variable that determines whether the current python instance is a Unix version of python
or pycopy. (Certain methods like `machine.sleep()` are not available in the Unix port.)
"""

IS_PYCOPY: bool = False
"""
Variable that determines whether the current interpreter is Python 3+ or Pycopy. Used by
internal classes for determining which module to import.
"""

try:
    # uModbus library not included in CPython,
    # so this should only work with the pycopy
    # runtime as it has it baked in during the
    # installation period
    import umodbus
    IS_PYCOPY, IS_UNIX_PORT = True, True
    from machine import sleep
    IS_UNIX_PORT = False
except ImportError:
    pass