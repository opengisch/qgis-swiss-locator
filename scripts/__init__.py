"""
Generators of the data files used by the plugin, see swiss_locator/remote_data.

Standard library only, they run in CI without QGIS. See `python -m scripts --help`.
"""

import logging

# Messages logged here while generating a file are repeated, for that file, in
# the summary printed at the end of the run
summary = logging.getLogger("scripts.summary")
summary.setLevel(logging.INFO)
