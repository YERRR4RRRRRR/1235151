# This file now acts as a compatibility wrapper to preserve the original
# public API while splitting core logic into exporter_core.py and
# spawnable_diagnostics.py as requested.

try:
    from exUE5.exporter_core import *
except ModuleNotFoundError:
    from exporter_core import *

try:
    from exUE5.spawnable_diagnostics import *
except ModuleNotFoundError:
    from spawnable_diagnostics import *
