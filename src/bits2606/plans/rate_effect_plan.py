"""Examine Effect of scaler RATE on T"""

import numpy as np
from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import plans as bp
from bluesky.utils import plan


@plan
def rate_effect(first=10, last=40, step=1, npts=10):
    """Measure the effect of scaler RATE on T."""
    if step <= 0:
        raise ValueError("step must be > 0")
    if int(npts) != npts or npts <= 0:
        raise ValueError("npts must be a positive integer")

    scaler1 = oregistry["scaler1"]
    span = last + step / 10 - first
    nrates = int(1 + span / step)
    for rate in np.linspace(first, first + span, nrates, endpoint=True):
        yield from bps.mv(scaler1.update_rate, rate)

        yield from bp.count(
            [scaler1],
            num=npts,
            md=dict(
                TP=np.round(scaler1.preset_time.get(), 4),
                RATE=np.round(rate, 4),
                title=f"Effect of scaler RATE on T, {rate=:.2f}",
            ),
        )
