"""Custom setup for gp IOC devices.

.. autosummary::

    ~_custom_controls_setup
    ~change_motor_srev
    ~change_motor_srev
    ~change_noisy_signal_parameters
    ~enable_user_calcs
    ~gp_controls_setup
    ~setup_area_detectors
    ~setup_monochromator
    ~setup_scaler1
    ~setup_shutter
    ~setup_temperature_positioner
"""

import logging
import sys

import numpy
from apsbits.core.instrument_init import oregistry
from apstools.devices import setup_lorentzian_swait
from apstools.plans import run_blocking_function
from bluesky import plan_stubs as bps
from bluesky.utils import plan as bluesky_plan
from ophydregistry.exceptions import ComponentNotFound

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


@bluesky_plan
def gp_controls_setup():
    """Initialize all the local controls (with default settings)."""
    logger.info("Starting custom controls setup.")
    functions = [  # NOTE: order is important
        # XX setup_scan_id,  (do this in startup module, needs cat)
        enable_user_calcs,
        change_motor_srev,
        setup_scaler1,
        change_noisy_signal_parameters,
        setup_shutter,
        setup_monochromator,
        setup_temperature_positioner,
        setup_area_detectors,
    ]
    for func in functions:
        try:
            yield from func()
        except (ComponentNotFound, TimeoutError) as exinfo:
            logger.warning("In setup_devices() ... %s", exinfo)
    logger.info("Local controls setup finished.")


@bluesky_plan
def change_motor_srev(srev=2_000):
    """
    Make sure the motors are mini-stepping.

    .. caution:: Define motor resolution JUST for this simulation.

        For a real instrument, the motor resolution is assigned
        when the hardware is installed.
    """
    logger.info("change_motor_srev()")

    for motor in oregistry.findall(label="motor"):
        if "steps_per_revolution" in dir(motor):
            motor.wait_for_connection()
            logger.debug("Set %r SREV to %f steps/rev", motor.name, srev)
            yield from bps.mv(motor.steps_per_revolution, srev)


@bluesky_plan
def change_noisy_signal_parameters(
    fwhm: float = 0.15,
    peak: float = 10_000,
    noise: float = 0.08,
):
    """
    Configure the simulated 'noisy' detector signal.

    Setup the swait record with new random numbers.
    """
    logger.info("change_noisy_signal_parameters()")
    m1 = oregistry["m1"]
    user_calcs = oregistry["user_calcs"]
    for obj in (m1, user_calcs):
        obj.wait_for_connection()

    yield from bps.mv(user_calcs.enable, 1)

    yield from run_blocking_function(user_calcs.calc1.reset)
    yield from run_blocking_function(
        setup_lorentzian_swait,
        user_calcs.calc1,
        m1.user_readback,
        center=2 * numpy.random.random() - 1,
        width=fwhm * numpy.random.random(),
        scale=peak * (9 + numpy.random.random()),
        noise=noise * (0.01 + numpy.random.random()),
    )


@bluesky_plan
def enable_user_calcs():
    """Enable all the user calcs, calcouts, sseqs, and transforms."""
    logger.info("enable_user_calcs()")
    for key in "user_calcouts user_calcs user_sseqs user_transforms".split():
        obj = oregistry.find(name=key, allow_none=True)
        if obj is not None:
            obj.wait_for_connection()
            logger.debug("Enable %r", key)
            yield from bps.mv(obj.enable, 1)


@bluesky_plan
def setup_area_detectors():
    """Setup the area detectors."""
    logger.info("setup_area_detectors()")
    yield from bps.null()
    ad_transform = oregistry["ad_transform"]
    adsimdet = oregistry["adsimdet"]
    for obj in (ad_transform, adsimdet):
        obj.wait_for_connection()
        logger.debug("Setup %r", obj.name)

    try:
        from .stubs import ad_peak_simulation
        from .stubs import change_ad_simulated_image_parameters
        from .stubs import dither_ad_peak_position

        yield from change_ad_simulated_image_parameters(adsimdet)
        # EPICS will dither the peak position
        yield from dither_ad_peak_position(adsimdet)

        logger.debug("Setup simulated peak image: %r", adsimdet.name)
        yield from ad_peak_simulation(adsimdet, ad_transform)

    except Exception as reason:
        print(f"Peak Dithering setup failed: {reason}")


@bluesky_plan
def setup_monochromator():
    """Setup the monochromator."""
    logger.info("setup_monochromator()")
    dcm = oregistry["dcm"]
    dcm.wait_for_connection()
    logger.debug("Setup the monochromator")

    yield from dcm.into_control_range(p_theta=2, p_y=-5, p_z=5)


@bluesky_plan
def setup_scaler1():
    """
    Setup the scaler.

    .. caution:: Define channel names JUST for this simulation.

        For a real instrument, the names are assigned when the
        detector pulse cables are connected to the scaler channels.
    """
    logger.info("setup_scaler1()")

    scaler1 = oregistry["scaler1"]
    scaler1.wait_for_connection()
    logger.debug("Setup custom scaler channels")

    if not len(scaler1.channels.chan01.chname.get()):
        logger.info(f"{scaler1.name} has no channel names.  Assigning channel names.")
        # fmt: off
        yield from bps.mv(
            scaler1.channels.chan01.chname, "timebase",
            scaler1.channels.chan02.chname, "I0",
            scaler1.channels.chan03.chname, "scint",
            scaler1.channels.chan04.chname, "diode",
            scaler1.channels.chan05.chname, "I000",
            scaler1.channels.chan06.chname, "I00",
        )
        # fmt: on
        yield from bps.sleep(1)  # wait for IOC

    # choose just the channels with EPICS names
    scaler1.select_channels()  # does not block

    # Increase RATE field to help T be TP.
    scaler1.update_rate.put(20)  # Hz

    # examples: make shortcuts to specific channels assigned in EPICS

    timebase = scaler1.channels.chan01.s
    I0 = scaler1.channels.chan02.s
    scint = scaler1.channels.chan03.s
    diode = scaler1.channels.chan04.s
    I000 = scaler1.channels.chan05.s
    I00 = scaler1.channels.chan06.s

    I0.parent.override_signal_name.put("noisy")

    for item in (timebase, I0, I00, I000, scint, diode):
        logger.debug("Custom scaler channel %r", item.name)
        labels = {"channel", "counter"}  # a set(), not a dict()
        item._ophyd_labels_ = labels

        # Add to the ophyd registry.
        oregistry.register(item, labels=labels)

        # Export to command-line (__main__) namespace.
        module = sys.modules["__main__"]
        setattr(module, item.name, item)


@bluesky_plan
def setup_shutter(delay=0.05):
    """
    Setup the shutter.

    Simulate a shutter that needs a finite recovery time after moving.
    """
    logger.info("setup_shutter()")
    yield from bps.null()  # makes it a plan (generator function)
    logger.debug("Setup shutter")

    shutter = oregistry["shutter"]
    shutter.wait_for_connection()
    shutter.delay_s = delay


@bluesky_plan
def setup_temperature_positioner():
    """Setup the temperature controller (positioner)."""
    logger.info("setup_temperature_positioner()")
    logger.debug("Setup temperature controller (positioner)")
    temperature = oregistry["temperature"]
    temperature.wait_for_connection()
    yield from run_blocking_function(
        temperature.setup_temperature,
        setpoint=25,
        noise=1,
        rate=5,
        tol=1,
        max_change=2,
        report_dmov_changes=False,
    )
