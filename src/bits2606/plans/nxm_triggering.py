"""
N x M trigger strategies
========================

Per-point trigger strategies for the N x M acquisition plan.
Each class implements two plan stubs:

* ``configure(det, n_points, m_per_point)`` -- once-per-run configuration
  of cam and HDF plugin (analogue of SPEC ``ccdscan_setup`` plus the
  per-detector ``ccdhook_ad_*`` rebinding).
* ``trigger_m(det)`` -- per-scan-point: arrange for exactly
  ``m_per_point`` frames to be acquired and captured into the HDF
  plugin. Returns once those M frames have been written
  (``hdf1.num_captured`` advanced by M).

These are the Bluesky analogue of the SPEC ``ccdtrig`` / ``ccdwait``
``rdef`` seam, swappable per detector / per acquisition mode.

.. autosummary::
    ~InternalBurst
    ~SoftwareLoop
    ~ExternalHardware
"""

import logging

from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


# How long to wait between polls of hdf1.num_captured (seconds).
_POLL_PERIOD = 0.01


def _wait_for_captured(det, target):
    """Block (in plan-message terms) until hdf1.num_captured >= target."""
    while det.hdf1.num_captured.get() < target:
        yield from bps.sleep(_POLL_PERIOD)


class InternalBurst:
    """
    Per point: one ``cam.Acquire`` produces M frames.

    Uses ``cam.ImageMode = Multiple`` and ``cam.NumImages = M``. The
    HDF plugin is preconfigured for ``N*M`` total captures and runs in
    Stream mode.
    """

    name = "internal_burst"

    def configure(self, det, n_points, m_per_point):
        """Configure cam for M-frame bursts and HDF for N*M total captures."""
        self._m = m_per_point
        # fmt: off
        yield from bps.mv(
            det.cam.image_mode, "Multiple",
            det.cam.num_images, m_per_point,
            det.cam.trigger_mode, "Internal",
            det.hdf1.file_write_mode, "Stream",
            det.hdf1.num_capture, n_points * m_per_point,
        )
        # fmt: on

    def trigger_m(self, det):
        """Fire one cam.Acquire producing M frames; wait for HDF to capture them."""
        target = det.hdf1.num_captured.get() + self._m
        yield from bps.trigger(det, group="nxm_m", wait=False)
        yield from bps.wait(group="nxm_m")
        # Don't return until the file plugin has actually written
        # all M frames (cam.Acquire returning early is plausible).
        yield from _wait_for_captured(det, target)


class SoftwareLoop:
    """
    Per point: ``M`` separate single-frame triggers.

    Closest analogue of the SPEC ``ccdtrig CCD_REPEATS`` loop pattern.
    """

    name = "software_loop"

    def configure(self, det, n_points, m_per_point):
        """Configure cam for single-frame acquires and HDF for N*M total captures."""
        self._m = m_per_point
        # fmt: off
        yield from bps.mv(
            det.cam.image_mode, "Single",
            det.cam.num_images, 1,
            det.cam.trigger_mode, "Internal",
            det.hdf1.file_write_mode, "Stream",
            det.hdf1.num_capture, n_points * m_per_point,
        )
        # fmt: on

    def trigger_m(self, det):
        """Issue M sequential single-frame triggers; wait for HDF to capture them."""
        target = det.hdf1.num_captured.get() + self._m
        for _ in range(self._m):
            yield from bps.trigger(det, wait=True)
        yield from _wait_for_captured(det, target)


class ExternalHardware:
    """
    Per point: external pulses drive M frames; detector armed once for ``N*M``.

    The cam is set to External trigger and ``NumImages = N*M`` so a
    single ``cam.Acquire`` covers the entire scan. Per point, the
    site-specific ``_fire_external_pulses`` plan stub fires M trigger
    pulses to the detector; this strategy then waits for the HDF
    plugin to confirm M new frames captured.

    For the bits2511 / ADSim development phase, ``_fire_external_pulses``
    is a no-op. The real implementation lives wherever the
    softGlue / shutter / delay-generator wiring lives at the beam line
    (analogue of SPEC ``Start_SoftGlue_Trigger`` / ``pvDELAY_A/B``).
    """

    name = "external_hardware"

    def configure(self, det, n_points, m_per_point):
        """Configure cam for External trigger mode and arm once for N*M frames."""
        self._m = m_per_point
        # fmt: off
        yield from bps.mv(
            det.cam.image_mode, "Multiple",
            det.cam.num_images, n_points * m_per_point,
            det.cam.trigger_mode, "External",
            det.hdf1.file_write_mode, "Stream",
            det.hdf1.num_capture, n_points * m_per_point,
        )
        # fmt: on
        # Arm the detector once. It will sit waiting for external pulses
        # until N*M frames have been collected.
        yield from bps.mv(det.cam.acquire, 1)

    def trigger_m(self, det):
        """Fire M external trigger pulses; wait for HDF to capture them."""
        target = det.hdf1.num_captured.get() + self._m
        yield from _fire_external_pulses(self._m)
        yield from _wait_for_captured(det, target)


def _fire_external_pulses(n):
    """
    Site-specific external trigger.

    No-op for the bits2511 / ADSim development environment. Replace
    at the beam line with the real plan stub that issues N hardware
    pulses (softGlue / shutter / delay generator).
    """
    yield from bps.null()


STRATEGIES = {
    InternalBurst.name: InternalBurst,
    SoftwareLoop.name: SoftwareLoop,
    ExternalHardware.name: ExternalHardware,
}
