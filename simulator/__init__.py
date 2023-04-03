import os
import sys

path = os.path.abspath(os.path.dirname(__file__))
if not path in sys.path:
    sys.path.append(path)
