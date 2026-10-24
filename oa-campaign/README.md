# Ophyd-Async Area Detector Campaign

This directory is a working area for creating ophyd-async versions of the
area-detector examples from the apstools documentation. The campaign
emphasizes how to configure different detector drivers, plugins, writers,
paths, filenames, and triggering modes. A simple shared factory supplies the
common construction mechanism; it is an implementation detail of the demos,
not the subject of the campaign.

The directory name intentionally contains a hyphen. Its contents are demos,
experiments, and supporting modules for this campaign; they are not a Python
package and must not become an importable dependency of another project.

## Goals

- Recreate the behavior demonstrated by each apstools example using the
  current upstream `ophyd-async` interfaces where practical.
- Add small, local support modules only when an example needs behavior that is
  not supplied upstream.
- Keep each example independently runnable and easy to compare with its
  apstools source notebook or guide.
- Record detector, writer, plugin, path, and triggering assumptions next to
  the example that uses them.
- Verify examples against the available EPICS Area Detector IOCs when
  possible, including the ADSimDetector IOC with prefix `ad:`.

## Examples

Work through these examples one at a time:

- `de_0_adsim_hdf5_basic`
- `de_1_adsim_hdf5_custom_names`
- `de_2_adsim_hdf5_single_mode`
- `de_ad_pe`
- `de_ad_pilatus`

Each example may receive a notebook, a Python companion module, and focused
support code in its own subdirectory. Use names derived from the source
example so the relationship remains obvious.

## Starting Points

Upstream `ophyd-async` currently provides useful building blocks including:

- `ophyd_async.epics.adsimdetector.SimDetector`
- `ophyd_async.epics.adpilatus.PilatusDetector`
- `ophyd_async.epics.adcore.AreaDetector`
- `ophyd_async.epics.adcore.SingleTriggerDetector`
- `ophyd_async.epics.adcore.ADHDFWriter`
- `ophyd_async.epics.adcore.ADJPEGWriter`
- `ophyd_async.epics.adcore.ADTIFFWriter`
- Area Detector path and filename providers from `ophyd_async.core`

The shared area-detector factory and local writer modules may be used as
implementation details when they provide capabilities needed by a demo, such
as configurable file templates or IOC-to-client path mapping. Example
narratives should focus on detector configuration and observed behavior, not
on the factory internals. Production device code should remain outside this
campaign directory unless a separate change explicitly promotes support.

## Checklist

- [x] Create the campaign directory and this README.
- [x] Implement `de_0_adsim_hdf5_basic` with upstream ADSim and HDF5 support.
- [x] Verify basic acquisition, HDF5 resources, and image readback.
- [ ] Implement `de_1_adsim_hdf5_custom_names`.
- [ ] Verify caller-controlled filenames and file-template behavior.
- [ ] Implement `de_2_adsim_hdf5_single_mode`.
- [ ] Verify single-image acquisition and determine the required single-file
      writer support.
- [ ] Implement `de_ad_pe`, or document the missing Perkin-Elmer support and
      a reproducible substitute if the driver is unavailable.
- [ ] Implement `de_ad_pilatus` with the upstream Pilatus driver/controller.
- [ ] Verify detector-specific triggering and HDF5 readback for Pilatus.
- [ ] Add focused tests or executable smoke checks for each completed example.
- [ ] Record IOC requirements, environment assumptions, and known limitations.
- [ ] Review the campaign for accidental imports from the hyphenated directory.

## Working Conventions

- Approach the examples in the listed order.
- Prefer upstream `ophyd-async` classes over reimplementing equivalent logic.
- Keep demo-specific code local to the example directory.
- Use explicit path providers for IOC write paths and client read paths.
- Do not add `oa-campaign` to the package source tree or import it from
  production modules.
- Mark a checklist item complete only after the corresponding demo has been
  run or its limitation has been documented.
