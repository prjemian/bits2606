# Basic ADSim HDF5 Example

This is the ophyd-async version of the apstools example
`de_0_adsim_hdf5_basic`.

## Configuration

This example configures an ADSimDetector with an image plugin and an HDF5
writer. The HDF5 files use UUID-style names and are arranged as
`example/YYYY/MM/DD` directories, matching the source example.

The shared factory and the upstream ADSim support keep detector construction
consistent with the other campaign examples. The factory is not otherwise
part of this example's subject.

A small local `ExampleDatePathProvider` preserves the source example's
`example/YYYY/MM/DD` layout without adding a device-name directory.

The default IOC prefix is `ad:`. The example follows the original directory
layout, writing below `/tmp/example/YYYY/MM/DD/` as seen by the IOC and
reading below `/local/ioc/iocad/tmp/example/YYYY/MM/DD/` as seen by the
client. Override these paths with `AD_IOC_MOUNT_PATH` and
`BLUESKY_MOUNT_PATH` when the IOC is mounted differently.

## Prerequisites

- An ADSimDetector IOC is running with prefix `ad:`.
- `bluesky`, `ophyd-async`, `tiled`, and `bluesky-tiled-plugins` are
  installed in the active Python environment.
- The client can read the HDF5 files written by the IOC.

The notebook is intended to be run from a Bluesky-capable environment after
the IOC has been started. It explicitly connects the factory-created detector
before acquisition.

## Run

Open `de_0_adsim_hdf5_basic.ipynb` for the full demonstration: configuration,
connection, acquisition, and HDF5 resource inspection through a notebook-
lifetime temporary Tiled server. The notebook inspects the external HDF5
resource URI directly because this temporary server does not proxy the
IOC-written file. It explicitly preserves the separate IOC write root and
Python client read root. Databroker is not used.

## Notes

The upstream HDF5 writer uses Area Detector stream mode. This matches the
basic example, where several frames are stored in one HDF5 resource. Custom
Area Detector file-template behavior is intentionally deferred to the next
campaign example.
