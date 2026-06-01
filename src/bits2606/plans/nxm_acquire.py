"""
N x M area-detector acquisition plan
====================================

Outer scan with ``N`` points; the area detector is preconfigured once
for ``N * M`` total frames. Per scan point, ``M`` frames are taken via
a swappable trigger strategy and emitted as ``M`` separate Bluesky
Event documents in the ``primary`` stream.

This is a Bluesky port of the SPEC ``ccdscan`` pattern, hoisting the
per-run cam / HDF configuration out of the per-point body so the
detector is armed only once (issue 8id-bits #142).

Seam mapping
------------

=====================================  ===========================================
SPEC ccdscan                           This plan
=====================================  ===========================================
outer ``ascan``/``dscan`` + ccdscan    ``bp.rel_scan(..., per_step=...)``
``_measure0_ccd`` (per scan point)     body of ``_nxm_per_step`` before reads
``_measure2_ccd`` (per scan point)     body of ``_nxm_per_step`` after reads
``ccdtrig`` / ``ccdwait`` rdef         ``strategy.trigger_m(det)``
``ccdscan_setup`` / ``ccdscan_header`` ``stage_decorator`` + ``strategy.configure``
``ccdscan_cleanup``                    ``stage_decorator`` teardown
``_user_prescan_head_ccd``             ``pre_point=`` argument
``_user_scan_tail_ccd``                ``post_point=`` argument
``CCD_REPEATS`` (global)               ``m_per_point`` argument (per call)
``ccdhook_ad_<DET>``                   ``strategy_name`` argument
=====================================  ===========================================

.. autosummary::
    ~nxm_rel_scan
"""

import logging
from functools import partial

from apsbits.core.instrument_init import with_registry
from bluesky import plan_stubs as bps
from bluesky import plans as bp
from bluesky.utils import plan as bluesky_plan

from .nxm_hooks import default_post_point
from .nxm_hooks import default_pre_point
from .nxm_triggering import STRATEGIES

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


def _nxm_per_step(
    detectors,
    step,
    pos_cache,
    *,
    det,
    extras,
    strategy,
    m_per_point,
    pre_point,
    post_point,
):
    """
    Per-scan-point body for the N x M plan.

    Move motors, run the user pre-point hook, trigger ``M`` frames via
    the strategy, emit ``M`` Events (each with one detector read plus
    one read per non-AD extra detector), then run the user post-point
    hook.
    """
    yield from bps.move_per_step(step, pos_cache)
    yield from pre_point(det, step)

    # Acquire all M frames in one strategy-determined burst. The HDF
    # plugin is preconfigured for N*M; this call returns once those M
    # frames are captured.
    yield from strategy.trigger_m(det)

    # Emit M Events in the 'primary' stream. Each Event references one
    # frame's HDF datum plus a fresh read of the extra detectors.
    for _ in range(m_per_point):
        yield from bps.create("primary")
        yield from bps.read(det)
        for extra in extras:
            yield from bps.read(extra)
        yield from bps.save()

    yield from post_point(det, step)


@with_registry
@bluesky_plan
def nxm_rel_scan(
    oregistry,
    motor_name: str = "sim_motor",
    start: float = -1.0,
    stop: float = 1.0,
    n_points: int = 5,
    m_per_point: int = 3,
    det_name: str = "adsimdet",
    strategy_name: str = "internal_burst",
    extra_det_names: list = None,
    md: dict = None,
):
    """
    Relative N-point scan with M frames per point on one area detector.

    Emits ``N * M`` Event documents in the ``primary`` stream.
    The area detector is preconfigured once at the start of the run
    for ``n_points * m_per_point`` total frames; it is not rearmed per
    scan point.

    Parameters
    ----------
    motor_name : str
        Name (in ``oregistry``) of the motor to scan.
    start, stop : float
        Relative scan limits about the motor's current position.
    n_points : int
        Number of scan points (the outer ``N`` loop).
    m_per_point : int
        Frames per scan point (the inner ``M``).
    det_name : str
        Name (in ``oregistry``) of the area-detector device. Must have
        ``cam`` and ``hdf1`` components in the usual
        ``apstools.devices.ad_creator`` shape.
    strategy_name : str
        One of ``"internal_burst"``, ``"software_loop"``,
        ``"external_hardware"``. See :mod:`bits2511.plans.nxm_triggering`.
    extra_det_names : list of str, optional
        Additional, non-AD detectors to read once per Event (e.g.
        scalers, ion chambers).
    md : dict, optional
        Extra metadata to attach to the run.
    """
    det = oregistry[det_name]
    motor = oregistry[motor_name]
    extras = [oregistry[n] for n in (extra_det_names or [])]
    detectors = [det, *extras]

    if strategy_name not in STRATEGIES:
        raise ValueError(
            f"unknown strategy_name {strategy_name!r}; " f"valid: {sorted(STRATEGIES)}"
        )
    strategy = STRATEGIES[strategy_name]()

    pre_point = default_pre_point
    post_point = default_post_point

    per_step = partial(
        _nxm_per_step,
        det=det,
        extras=extras,
        strategy=strategy,
        m_per_point=m_per_point,
        pre_point=pre_point,
        post_point=post_point,
    )

    plan_md = {
        "plan_name": "nxm_rel_scan",
        "N": n_points,
        "M": m_per_point,
        "strategy": strategy_name,
        "detector": det_name,
        "motor": motor_name,
        "events_per_point": m_per_point,
        **(md or {}),
    }

    # Pre-stage HDF file_path / file_name. AD_EpicsFileNameHDF5Plugin
    # validates these inside stage() (before stage_sigs are applied)
    # and also checks file_path_exists on the IOC, so we must set them
    # via plain mv before bp.rel_scan triggers staging. We force-set:
    # the IOC default of '/' is non-empty but useless.
    current_path = det.hdf1.file_path.get()
    if current_path in ("", "/"):
        yield from bps.mv(det.hdf1.file_path, det.hdf1.write_path_template)
    if not det.hdf1.file_name.get():
        yield from bps.mv(det.hdf1.file_name, "nxm")
    # bits2511's stubs.ad_setup uses `create_directory = -5` so the
    # IOC will create missing directories. Apply here so the plan is
    # self-contained.
    yield from bps.mv(det.hdf1.create_directory, -5)

    # Note: bp.rel_scan already wraps the scan in stage_wrapper +
    # run_wrapper. We must NOT add an outer stage_decorator here, or
    # the detector is staged twice (RedundantStaging). To get the
    # N*M-up-front configure() to happen *after* stage() but *before*
    # the first per_step call, we use a first-call latch in per_step.
    configured = {"done": False}

    def _per_step_with_configure(detectors, step, pos_cache):
        if not configured["done"]:
            yield from strategy.configure(det, n_points, m_per_point)
            configured["done"] = True
        yield from per_step(detectors, step, pos_cache)

    yield from bp.rel_scan(
        detectors,
        motor,
        start,
        stop,
        n_points,
        per_step=_per_step_with_configure,
        md=plan_md,
    )
