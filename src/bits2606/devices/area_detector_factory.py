"""Local support for area detectors in ophyd-async."""

from collections.abc import Sequence
from functools import reduce
from importlib import import_module
from typing import Annotated as A
from typing import TypedDict

from apstools.utils import dynamic_import
from .area_detector_writers import hdf as configurable_hdf
from .area_detector_writers import jpeg as configurable_jpeg
from .area_detector_writers import tiff as configurable_tiff
from ophyd_async import core
from ophyd_async.core import SignalR, SignalRW
from ophyd_async.epics import adcore
from ophyd_async.epics import adsimdetector
from ophyd_async.epics.core import PvSuffix

try:
    from ophyd_async.epics.adcore._io import NDProcessIO
except ImportError:
    NDProcessIO = None


class NDAttributeIO(adcore.NDPluginBaseIO):
    """AreaDetector attribute plugin interface."""

    reset: A[SignalRW[bool], PvSuffix("Reset")]


class NDBadPixelIO(adcore.NDPluginBaseIO):
    """AreaDetector bad-pixel plugin interface."""

    file_name: A[SignalRW[str], PvSuffix("FileName")]


class NDColorConvIO(adcore.NDPluginBaseIO):
    """AreaDetector color conversion plugin interface."""

    color_mode_out: A[SignalRW[int], PvSuffix.rbv("ColorModeOut")]
    false_color: A[SignalRW[int], PvSuffix.rbv("FalseColor")]


class NDCodecIO(adcore.NDPluginBaseIO):
    """AreaDetector codec plugin interface."""

    mode: A[SignalRW[int], PvSuffix.rbv("Mode")]
    compressor: A[SignalRW[int], PvSuffix.rbv("Compressor")]
    compression_factor: A[SignalR[float], PvSuffix("CompFactor_RBV")]
    jpeg_quality: A[SignalRW[int], PvSuffix.rbv("JPEGQuality")]
    blosc_compressor: A[SignalRW[int], PvSuffix.rbv("BloscCompressor")]
    blosc_level: A[SignalRW[int], PvSuffix.rbv("BloscCLevel")]
    blosc_shuffle: A[SignalRW[int], PvSuffix.rbv("BloscShuffle")]
    blosc_num_threads: A[SignalRW[int], PvSuffix.rbv("BloscNumThreads")]
    codec_status: A[SignalR[int], PvSuffix("CodecStatus")]
    codec_error: A[SignalR[str], PvSuffix("CodecError")]


class NDFFTIO(adcore.NDPluginBaseIO):
    """AreaDetector FFT plugin interface."""

    time_per_point: A[SignalRW[float], PvSuffix.rbv("FFTTimePerPoint")]
    time_axis: A[SignalR[Sequence[float]], PvSuffix("FFTTimeAxis")]
    frequency_axis: A[SignalR[Sequence[float]], PvSuffix("FFTFreqAxis")]
    direction: A[SignalRW[bool], PvSuffix.rbv("FFTDirection")]
    suppress_dc: A[SignalRW[bool], PvSuffix.rbv("FFTSuppressDC")]
    num_average: A[SignalRW[int], PvSuffix.rbv("FFTNumAverage")]
    num_averaged: A[SignalR[int], PvSuffix("FFTNumAveraged")]
    reset_average: A[SignalRW[bool], PvSuffix("FFTResetAverage")]
    name_: A[SignalRW[str], PvSuffix("Name")]
    time_series: A[SignalR[Sequence[float]], PvSuffix("FFTTimeSeries")]
    real: A[SignalR[Sequence[float]], PvSuffix("FFTReal")]
    imaginary: A[SignalR[Sequence[float]], PvSuffix("FFTImaginary")]
    absolute_value: A[SignalR[Sequence[float]], PvSuffix("FFTAbsValue")]


class NDGatherIO(adcore.NDPluginBaseIO):
    """AreaDetector gather plugin interface."""


class NDOverlayIO(adcore.NDPluginBaseIO):
    """AreaDetector overlay plugin interface."""

    max_size_x: A[SignalR[int], PvSuffix("MaxSizeX_RBV")]
    max_size_y: A[SignalR[int], PvSuffix("MaxSizeY_RBV")]


class NDScatterIO(adcore.NDPluginBaseIO):
    """AreaDetector scatter plugin interface."""

    scatter_method: A[SignalRW[int], PvSuffix.rbv("ScatterMethod")]


class NDTransformIO(adcore.NDPluginBaseIO):
    """AreaDetector transform plugin interface."""

    transform_type: A[SignalRW[int], PvSuffix.rbv("Type")]


class PluginSpec(TypedDict):
    suffix: str
    type: str | type | None


RECOGNIZED_PLUGINS: dict[str, PluginSpec] = {
    "attr1": {"suffix": "Attr1:", "type": NDAttributeIO},
    "badpix1": {"suffix": "BadPix1:", "type": NDBadPixelIO},
    "cb1": {"suffix": "CB1:", "type": adcore.NDCircularBuffIO},
    "cc1": {"suffix": "CC1:", "type": NDColorConvIO},
    "cc2": {"suffix": "CC2:", "type": NDColorConvIO},
    "codec1": {"suffix": "Codec1:", "type": NDCodecIO},
    "codec2": {"suffix": "Codec2:", "type": NDCodecIO},
    "fft1": {"suffix": "FFT1:", "type": NDFFTIO},
    "gather1": {"suffix": "Gather1:", "type": NDGatherIO},
    "image": {"suffix": "image1:", "type": adcore.NDPluginBaseIO},
    "over1": {"suffix": "Over1:", "type": NDOverlayIO},
    "proc1": {"suffix": "Proc1:", "type": NDProcessIO},
    "pva": {"suffix": "Pva1:", "type": adcore.NDPluginBaseIO},
    "roi1": {"suffix": "ROI1:", "type": adcore.NDROIIO},
    "roi2": {"suffix": "ROI2:", "type": adcore.NDROIIO},
    "roi3": {"suffix": "ROI3:", "type": adcore.NDROIIO},
    "roi4": {"suffix": "ROI4:", "type": adcore.NDROIIO},
    "roistat1": {"suffix": "ROIStat1:", "type": adcore.NDROIStatNIO},
    "scatter1": {"suffix": "Scatter1:", "type": NDScatterIO},
    "stats1": {"suffix": "Stats1:", "type": adcore.NDStatsIO},
    "stats2": {"suffix": "Stats2:", "type": adcore.NDStatsIO},
    "stats3": {"suffix": "Stats3:", "type": adcore.NDStatsIO},
    "stats4": {"suffix": "Stats4:", "type": adcore.NDStatsIO},
    "stats5": {"suffix": "Stats5:", "type": adcore.NDStatsIO},
    "trans1": {"suffix": "Trans1:", "type": NDTransformIO},
}


WRITER_DEFAULTS = {
    "hdf": {
        "type": configurable_hdf,
        "writer_suffix": "HDF1:",
    },
    "jpeg": {
        "type": configurable_jpeg,
        "writer_suffix": "JPEG1:",
    },
    "tiff": {
        "type": configurable_tiff,
        "writer_suffix": "TIFF1:",
    },
}


def import_object(path: str):
    """Resolve ``module.object`` or ``module:object`` notation."""
    if ":" in path:
        module_name, object_name = path.split(":", 1)
        if not module_name or not object_name:
            raise ValueError(f"Invalid import path: {path!r}")
        return reduce(
            getattr,
            object_name.split("."),
            import_module(module_name),
        )
    return dynamic_import(path)


def plugins_factory(
    prefix: str,
    plugin_list: Sequence[str | dict[str, dict]],
) -> dict[str, adcore.NDPluginBaseIO]:
    """Construct plugins from names or named configuration overrides.

    Parameters
    ----------
    prefix:
        Detector PV prefix prepended to default plugin suffixes.
    plugin_list:
        Plugin names or one-key dictionaries containing per-plugin overrides.

    Examples
    --------
    ``plugins_factory("ad:", ["image", "pva"])`` uses the built-in
    plugin definitions. A YAML-friendly override is::

        plugins_factory(
            "ad:",
            [{"roi1": {"type": "ophyd_async.epics.adcore.NDROIIO"}}],
        )


    A string selects the defaults in ``RECOGNIZED_PLUGINS``. A dictionary has
    one plugin name as its key and overrides its defaults, for example::

        [{"roi1": {"suffix": "ROI5:", "type": adcore.NDROIIO}}, "stats1"]

    A plugin configuration may also provide ``args`` and ``kwargs`` for the
    plugin constructor. By default, the constructor receives the configured
    PV prefix as its first positional argument.
    """
    specifications = []
    unrecognized = []
    malformed = []
    unsupported = []
    import_errors = []
    for spec in plugin_list:
        if isinstance(spec, str):
            key = spec
            overrides = {}
        elif isinstance(spec, dict) and len(spec) == 1:
            key, overrides = next(iter(spec.items()))
            if not isinstance(key, str) or not isinstance(overrides, dict):
                malformed.append(spec)
                continue
        else:
            malformed.append(spec)
            continue

        defaults = RECOGNIZED_PLUGINS.get(key)
        if defaults is None:
            unrecognized.append(key)
            continue
        configuration = {**defaults, **overrides}
        plugin_type = configuration.get("type")
        if isinstance(plugin_type, str):
            try:
                plugin_type = import_object(plugin_type)
            except (ImportError, AttributeError, ValueError) as exc:
                import_errors.append((key, plugin_type, str(exc)))
                continue
            configuration["type"] = plugin_type
        if plugin_type is None or not callable(plugin_type):
            unsupported.append(key)
            continue
        specifications.append((key, configuration))

    if malformed:
        raise ValueError(f"Malformed plugin specifications: {malformed!r}")
    if unrecognized:
        raise ValueError(f"Unrecognized plugin names: {unrecognized!r}")
    if unsupported:
        raise ValueError(f"Unsupported plugin names: {unsupported!r}, no support class")
    if import_errors:
        raise ValueError(f"Could not import plugin types: {import_errors!r}")

    plugins = {}
    for key, configuration in specifications:
        args = list(configuration.get("args", [prefix + configuration["suffix"]]))
        kwargs = dict(configuration.get("kwargs", {}))
        plugins[key] = configuration["type"](*args, **kwargs)
    return plugins


def writers_factory(
    **writer_specs: dict[str, dict],
) -> list[adcore.ADWriterFactory]:
    """Construct writer factories from named specifications.

    Parameters
    ----------
    writer_specs:
        Named writer configurations. Built-in names are ``hdf``, ``jpeg``,
        and ``tiff``. Each configuration must provide a path provider in
        ``args``; factory defaults fill in the remaining writer settings.

    Examples
    --------
    A deployment supplies its IOC path and client URI while using defaults::

        writers_factory(
            hdf={
                "args": [{
                    "type": "ophyd_async.core.StaticPathProvider",
                    "args": [{
                        "type": "ophyd_async.core.StaticFilenameProvider",
                        "args": ["image"],
                    }],
                    "kwargs": {
                        "directory_path": "/ioc/data",
                        "directory_uri": "file://localhost/client/data/",
                    },
                }],
            },
        )

        # A custom sequence format is optional:
        # "kwargs": {"file_template": "%s%s_%3.3d.h5"}

    Each specification may provide a writer factory in ``type``; built-in
    writer names use the matching factory by default. Positional constructor
    arguments go in ``args`` and keyword arguments go in ``kwargs``. The
    caller must always provide the path provider for each writer. Nested
    ``type`` specifications are constructed recursively, which allows path
    and filename providers to be configured in the same structure.

    For example::

        writers_factory(
            hdf={
                "type": adcore.ADWriterFactory.hdf,
                "args": [{
                    "type": core.StaticPathProvider,
                    "args": [{
                        "type": core.StaticFilenameProvider,
                        "args": ["adsim_test"],
                    }],
                    "kwargs": {
                        "directory_path": "/tmp/learning/",
                        "directory_uri": "file://localhost/local/ioc/iocad/tmp/learning/",
                        "create_dir_depth": -5,
                    },
                }],
                "kwargs": {
                    "writer_suffix": "HDF1:",
                    "writer_name": "hdf",
                    "datakey_suffix": "-hdf",
                },
            },
        )
    """

    def construct(spec):
        if not isinstance(spec, dict) or "type" not in spec:
            return spec
        args = [construct(arg) for arg in spec.get("args", [])]
        kwargs = {
            key: construct(value) for key, value in spec.get("kwargs", {}).items()
        }
        constructor = spec["type"]
        if isinstance(constructor, str):
            constructor = import_object(constructor)
        return constructor(*args, **kwargs)

    unrecognized = []
    unsupported = []
    missing_path_provider = []
    for writer_name, spec in writer_specs.items():
        if writer_name not in WRITER_DEFAULTS and not isinstance(spec, dict):
            unrecognized.append(writer_name)
            continue
        if not isinstance(spec, dict):
            unrecognized.append(writer_name)
            continue
        if "type" not in spec and writer_name not in WRITER_DEFAULTS:
            unrecognized.append(writer_name)
        elif "type" in spec:
            writer_type = spec["type"]
            if isinstance(writer_type, str):
                try:
                    import_object(writer_type)
                except (ImportError, AttributeError, ValueError):
                    unsupported.append(writer_name)
            elif not callable(writer_type):
                unsupported.append(writer_name)
        if not spec.get("args"):
            missing_path_provider.append(writer_name)

    if unrecognized:
        raise ValueError(f"Unrecognized writer specifications: {unrecognized!r}")
    if unsupported:
        raise ValueError(
            f"Unsupported writer specifications: {unsupported!r}; "
            "`type` must be callable or an import path"
        )
    if missing_path_provider:
        raise ValueError(
            f"Missing path provider for writers: {missing_path_provider!r}; "
            "provide the writer factory's first positional argument"
        )

    writers = []
    for writer_name, spec in writer_specs.items():
        factory_spec = dict(spec)
        defaults = WRITER_DEFAULTS.get(writer_name, {})
        factory_spec.setdefault("type", defaults.get("type"))
        kwargs = dict(factory_spec.get("kwargs", {}))
        kwargs.setdefault("writer_name", writer_name)
        if "writer_suffix" in defaults:
            kwargs.setdefault("writer_suffix", defaults["writer_suffix"])
        kwargs.setdefault("datakey_suffix", f"-{writer_name}")
        factory_spec["kwargs"] = kwargs
        writers.append(construct(factory_spec))
    return writers


def ad_creator_async(
    prefix: str = "",
    name: str = "",  # MUST not be empty string
    driver_suffix: str = "cam1:",
    driver: adcore.ADBaseIO | str | None = None,
    acquire_logic: core.DetectorAcquireLogic | None = None,
    config_sigs: Sequence[core.SignalR] | None = None,
    trigger_logic: core.DetectorTriggerLogic | None = None,
    plugin_list: Sequence[str | dict[str, dict]] | None = None,
    writer_specs: dict[str, dict] | None = None,
) -> adcore.AreaDetector:
    """Create an ophyd-async area detector object.

    Parameters
    ----------
    prefix:
        Detector PV prefix.
    name:
        Bluesky device name.
    driver_suffix:
        Driver suffix used by the default ADSimDetector path or a string
        driver class.
    driver:
        An instantiated driver, a dotted/colon import path, or ``None``.
        ``None`` selects the ADSimDetector convenience defaults.
    acquire_logic:
        Required for custom drivers; defaults to ``ADAcquireLogic`` for ADSim.
    trigger_logic:
        Required for custom drivers; defaults to
        ``SimDetectorTriggerLogic`` for ADSim.
    config_sigs:
        Additional configuration signals.
    plugin_list:
        Plugin names or override dictionaries.
    writer_specs:
        Named writer configurations.

    Examples
    --------
    Default ADSimDetector setup::

        det = ad_creator_async("ad:", name="det")

    Custom driver specified using entry-point-style notation::

        det = ad_creator_async(
            "eiger:",
            driver="my_instrument.detectors:ADEiger2",
            acquire_logic=my_acquire_logic,
            trigger_logic=my_trigger_logic,
        )
    """
    if len(prefix) == 0:
        raise ValueError("MUST provide a `prefix` kwarg.")

    if driver is None:
        # The no-driver form is the ADSimDetector convenience path.
        driver = adcore.ADBaseIO(prefix + driver_suffix)
        acquire_logic = acquire_logic or adcore.ADAcquireLogic(driver)
        trigger_logic = trigger_logic or adsimdetector.SimDetectorTriggerLogic(driver)
    else:
        if isinstance(driver, str):
            driver = import_object(driver)(prefix + driver_suffix)
        if acquire_logic is None or trigger_logic is None:
            raise ValueError(
                "When supplying a custom `driver`, both `acquire_logic` and "
                "`trigger_logic` must be supplied."
            )

    if plugin_list is None:
        plugin_list = {"image", "pva"}
    plugins = plugins_factory(prefix, plugin_list)

    if writer_specs is None:
        writer_specs = {}
    writers = writers_factory(**writer_specs)

    if config_sigs is None:
        config_sigs = ()

    det = adcore.AreaDetector(
        driver,
        prefix,
        *writers,
         trigger_logic=trigger_logic,
         acquire_logic=acquire_logic,

        plugins=plugins,
        config_sigs=config_sigs,
        name=name,
    )
    return det
