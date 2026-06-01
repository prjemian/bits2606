"""
Per-point user hooks for the N x M acquisition plan
===================================================

Bluesky analogues of SPEC ``_user_prescan_head_ccd`` (pre-point) and
the tail of ``_measure2_ccd`` (post-point). The defaults are no-ops.
Override by passing ``pre_point=`` / ``post_point=`` to
``nxm_rel_scan``.

Signature::

    def my_hook(det, step):
        yield from bps.null()

where ``det`` is the area-detector device and ``step`` is the
``{motor: target_value}`` dict the scan engine passes to ``per_step``.

.. autosummary::
    ~default_pre_point
    ~default_post_point
"""

import logging

from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


def default_pre_point(det, step):
    """No-op default pre-point hook."""
    yield from bps.null()


def default_post_point(det, step):
    """No-op default post-point hook."""
    yield from bps.null()
