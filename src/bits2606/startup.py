"""
Start Bluesky Data Acquisition sessions of all kinds.

Includes:

* Python script
* IPython console
* Jupyter notebook
* Bluesky queueserver
"""

# Standard Library Imports
import logging
from pathlib import Path

# Core Functions
from apsbits.core.best_effort_init import init_bec_peaks
from apsbits.core.catalog_init import init_catalog
from apsbits.core.instrument_init import init_instrument
from apsbits.core.instrument_init import make_devices
from apsbits.core.run_engine_init import init_RE
from apsbits.core.session_setup import prepare_bits

# Utility functions
from apsbits.utils.aps_functions import host_on_aps_subnet
from apsbits.utils.baseline_setup import setup_baseline_stream

# Configuration functions
from apsbits.utils.config_loaders import load_config
from apsbits.utils.helper_functions import register_bluesky_magics
from apsbits.utils.helper_functions import running_in_queueserver
from apsbits.utils.logging_setup import configure_logging

# Run first so we get better diagnostics about subsequent problems
configure_logging()
prepare_bits()

# Configuration block
# Get the path to the instrument package
# Load configuration to be used by the instrument.
instrument_path = Path(__file__).parent
iconfig_path = instrument_path / "configs" / "iconfig.yml"
iconfig = load_config(iconfig_path)

# Additional logging configuration
# only needed if using different logging setup
# from the one in the apsbits package
extra_logging_configs_path = instrument_path / "configs" / "extra_logging.yml"
configure_logging(extra_logging_configs_path=extra_logging_configs_path)


logger = logging.getLogger(__name__)
logger.info("Starting Instrument with iconfig: %s", iconfig_path)

# initialize instrument
instrument, oregistry = init_instrument("guarneri")

# Discard oregistry items loaded above.
oregistry.clear()

# Configure the session with callbacks, devices, and plans.
# aps_dm_setup(iconfig.get("DM_SETUP_FILE"))

# Command-line tools, such as %wa, %ct, ...
register_bluesky_magics()

# Bluesky initialization block

bec, peaks = init_bec_peaks(iconfig)
cat = init_catalog(iconfig)
RE, sd = init_RE(iconfig, subscribers=[bec, cat])

# Optional Nexus callback block
# delete this block if not using Nexus
if iconfig.get("NEXUS_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.nexus import nxwriter_init

    nxwriter = nxwriter_init(RE, iconfig)

# Optional SPEC callback block
# delete this block if not using SPEC
if iconfig.get("SPEC_DATA_FILES", {}).get("ENABLE", False):
    from .callbacks.spec import init_specwriter_with_RE
    from .callbacks.spec import newSpecFile  # noqa: F401
    from .callbacks.spec import spec_comment  # noqa: F401

    specwriter = init_specwriter_with_RE(RE, iconfig)  # noqa: F811

# These imports must come after the above setup.
# Queue server block
if running_in_queueserver():
    ### To make all the standard plans available in QS, import by '*', otherwise import
    ### plan by plan.
    from apstools.plans import lineup2  # noqa: F401
    from bluesky.plans import *  # noqa: F403

    logger.info("Queueserver session")
else:
    # Import bluesky plans and stubs with prefixes set by common conventions.
    # The apstools plans and utils are imported by '*'.
    from apstools.plans import *  # noqa: F403
    from apstools.utils import *  # noqa: F403
    from bluesky import plan_stubs as bps  # noqa: F401
    from bluesky import plans as bp  # noqa: F401


# Experiment specific logic, device and plan loading. # Create the devices.
#
# Workaround for apsbits >=2.0.3: apsbits.core.instrument_init.make_devices
# calls `asyncio.run(...)` unconditionally, which raises
# `RuntimeError: asyncio.run() cannot be called from a running event loop`
# when startup is imported from a Jupyter/ipykernel session (Tornado already
# owns a running loop).  Plain `ipython` has no running loop, so it works.
# Detect a running loop and, only in that case, apply `nest_asyncio` so the
# nested `asyncio.run(...)` inside apsbits becomes re-entrant.
# Track upstream fix in apsbits before removing this block.
import asyncio as _asyncio  # noqa: E402

try:
    _asyncio.get_running_loop()
except RuntimeError:
    pass  # no running loop (terminal ipython, scripts): leave asyncio alone
else:
    import nest_asyncio  # noqa: E402

    nest_asyncio.apply()
    logger.info(
        "Applied nest_asyncio.apply() to allow apsbits.make_devices() "
        "to call asyncio.run() inside a running event loop "
        "(Jupyter/ipykernel/queueserver)."
    )

make_devices(clear=False, file="devices.yml", device_manager=instrument)

if host_on_aps_subnet():
    make_devices(clear=False, file="devices_aps_only.yml", device_manager=instrument)

# Setup baseline stream with connect=False is default
# Devices with the label 'baseline' will be added to the baseline stream.
setup_baseline_stream(sd, oregistry, connect=False)

from .plans.nxm_acquire import nxm_rel_scan  # noqa: E402, F401
from .plans.sim_plans import sim_count_plan  # noqa: E402, F401
from .plans.sim_plans import sim_print_plan  # noqa: E402, F401
from .plans.sim_plans import sim_rel_scan_plan  # noqa: E402, F401

# ---------------------------
# --------------------------- local changes
# ---------------------------

# adjust the scan_id to the current catalog
# oregistry["scan_id_epics"].put(len(cat))


def on_startup():
    """Custom session initialization."""
    from bits2606.plans.gp_device_setup import gp_controls_setup

    yield from gp_controls_setup()


RE(on_startup())
