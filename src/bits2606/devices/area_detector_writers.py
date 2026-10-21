"""Configurable AreaDetector file-writer factories.

The upstream ophyd-async data logic writes fixed FileTemplate PV values.
These local variants make the templates configurable while retaining the
upstream HDF5, JPEG, and TIFF behavior.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath, PureWindowsPath
from urllib.parse import quote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from ophyd_async.core import (
    DetectorDataLogic,
    EnableDisable,
    PathProvider,
    StreamableDataProvider,
    StreamResourceDataProvider,
    StreamResourceInfo,
    set_and_wait_for_value,
)
from ophyd_async.epics import adcore
from ophyd_async.epics.adcore._data_logic import (
    ADFileWriteMode,
    ADHDFDataLogic,
    ADMultipartDataLogic,
    NDArrayDescription,
    get_ndarray_resource_info,
    get_ndattribute_dtype_source,
)
from ophyd_async.epics.adcore._io import (
    NDArrayBaseIO,
    NDFileHDF5IO,
    NDPluginBaseIO,
    NDPluginFileIO,
)
from ophyd_async.epics.core import stop_busy_record


def substitute_area_detector_date_tokens(path: str, now: datetime | None = None) -> str:
    """Replace unresolved AreaDetector date tokens in a path."""
    if not any(token in path for token in ("%Y", "%m", "%D")):
        return path
    now = now or datetime.now()
    replacements = {
        "%Y": now.strftime("%Y"),
        "%m": now.strftime("%m"),
        "%D": now.strftime("%d"),
    }
    for token, value in replacements.items():
        path = path.replace(token, value)
    return path


def reroot_path_uri(ioc_path: str, ioc_root: str, client_uri: str) -> str:
    """Map an IOC path below its root into the client-visible URI root."""
    ioc_path = PurePath(ioc_path)
    ioc_root = PurePath(ioc_root)
    try:
        relative_path = ioc_path.relative_to(ioc_root)
    except ValueError as exc:
        raise ValueError(f"IOC path {ioc_path!s} is not below root {ioc_root!s}") from exc

    parsed = urlsplit(client_uri)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Client URI must have a scheme and host: {client_uri!r}")
    root_path = parsed.path.rstrip("/")
    relative_uri = "" if relative_path == PurePath(".") else quote(
        relative_path.as_posix(), safe="/"
    )
    mapped_path = f"{root_path}/{relative_uri}" if relative_uri else f"{root_path}/"
    if not mapped_path.endswith("/"):
        mapped_path += "/"
    return urlunsplit((parsed.scheme, parsed.netloc, mapped_path, parsed.query, parsed.fragment))


async def prepare_file_paths(
    path_info, file_template: str, writer: NDPluginFileIO
) -> None:
    """Configure writer paths without changing the user-controlled number."""
    await writer.create_directory.set(path_info.create_dir_depth)
    if isinstance(path_info.directory_path, PureWindowsPath):
        directory_path = f"{path_info.directory_path}\\"
    else:
        directory_path = f"{path_info.directory_path}/"
    await asyncio.gather(
        writer.file_path.set(directory_path),
        writer.file_name.set(path_info.filename),
        writer.file_template.set(file_template),
        writer.auto_increment.set(True),
        writer.file_write_mode.set(ADFileWriteMode.STREAM),
    )
    if not await writer.file_path_exists.get_value():
        msg = f"Path {directory_path} doesn't exist or not writable!"
        raise FileNotFoundError(msg)
    await writer.num_capture.set(0)


@dataclass
class ConfigurableHDFDataLogic(ADHDFDataLogic):
    """HDF5 data logic with a configurable FileTemplate PV value."""

    file_template: str = "%s%s.h5"

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        update = getattr(self.path_provider, "update", None)
        if update is not None:
            await update()
        path_info = self.path_provider(datakey_name)
        frames_per_chunk = await self.writer.num_frames_chunks.get_value()
        if frames_per_chunk == 0:
            frames_per_chunk = 1
            await self.writer.num_frames_chunks.set(frames_per_chunk)

        file_template = await self.writer.file_template.get_value(cached=False)
        if not file_template:
            file_template = self.file_template
        if not file_template:
            raise ValueError("AreaDetector FileTemplate PV is empty")

        await asyncio.gather(
            self.writer.chunk_size_auto.set(True),
            self.writer.num_extra_dims.set(0),
            self.writer.lazy_open.set(True),
            self.writer.swmr_mode.set(True),
            self.writer.xml_file_name.set(""),
            self.writer.enable_callbacks.set(EnableDisable.ENABLE),
            prepare_file_paths(
                path_info=path_info,
                file_template=file_template,
                writer=self.writer,
            ),
        )
        await set_and_wait_for_value(
            self.writer.capture, True, wait_for_set_completion=False
        )

        main_dataset = await get_ndarray_resource_info(
            array_description=self.array_description,
            data_key=datakey_name,
            parameters={
                "dataset": "/entry/data/data",
                # The descriptor includes the one-frame collection axis. Concatenate
                # that axis across stream datums instead of stacking another one.
                "join_method": "concat",
            },
            frames_per_chunk=frames_per_chunk,
        )
        ndattribute_dtype_sources = await get_ndattribute_dtype_source(
            (self.driver, *self.plugins) if self.driver else (*self.plugins,)
        )
        ndattribute_datasets = [
            StreamResourceInfo(
                data_key=name,
                shape=(),
                chunk_shape=(16384,),
                dtype_numpy=dtype_numpy,
                source=source,
                parameters={"dataset": f"/entry/instrument/NDAttributes/{name}"},
            )
            for name, (dtype_numpy, source) in ndattribute_dtype_sources.items()
        ]
        file_path = str(path_info.directory_path)
        file_name = path_info.filename
        file_number = await self.writer.file_number.get_value(cached=False)
        now = datetime.now()
        file_path = substitute_area_detector_date_tokens(file_path, now)
        file_name = substitute_area_detector_date_tokens(file_name, now)
        if not file_path or not file_name:
            raise ValueError("AreaDetector FilePath_RBV and FileName_RBV must be populated")
        configured_directory = substitute_area_detector_date_tokens(
            str(
                getattr(self.path_provider, "configured_directory_path", None)
                or path_info.directory_path
            ),
            now,
        )
        file_path_uri = reroot_path_uri(
            file_path,
            configured_directory,
            path_info.directory_uri,
        )
        try:
            resource_uri = file_template % (file_path_uri, file_name, file_number)
        except TypeError:
            resource_uri = file_template % (file_path_uri, file_name)
        return StreamResourceDataProvider(
            uri=resource_uri,
            resources=[main_dataset] + ndattribute_datasets,
            mimetype="application/x-hdf5",
            collections_written_signal=self.writer.num_captured,
            flush_signal=self.writer.flush_now,
        )


@dataclass
class ConfigurableMultipartDataLogic(ADMultipartDataLogic):
    """JPEG/TIFF data logic with a configurable FileTemplate value."""

    file_template: str | None = None

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        update = getattr(self.path_provider, "update", None)
        if update is not None:
            await update()
        path_info = self.path_provider(datakey_name)
        file_template = self.file_template or ("%s%s_%6.6d" + self.extension)
        await prepare_file_paths(
            path_info=path_info,
            file_template=file_template,
            writer=self.writer,
        )
        await set_and_wait_for_value(
            self.writer.capture, True, wait_for_set_completion=False
        )
        template = path_info.filename + "_{:06d}" + self.extension
        main_dataset = await get_ndarray_resource_info(
            array_description=self.array_description,
            data_key=datakey_name,
            parameters={"template": template},
        )
        return StreamResourceDataProvider(
            uri=path_info.directory_uri,
            resources=[main_dataset],
            mimetype=self.mimetype,
            collections_written_signal=self.writer.num_captured,
        )


@dataclass
class ConfigurableWriterFactory:
    """Create a writer and data logic with a configurable file template."""

    writer_cls: type
    writer_suffix: str
    writer_name: str
    datakey_suffix: str
    array_description: object = None
    file_template: str | None = None
    data_logic_factory: Callable | None = None

    def __call__(self, prefix: str, driver, plugins: Sequence[NDPluginBaseIO]):
        writer = self.writer_cls(prefix + self.writer_suffix)
        bind_writer = getattr(self.path_provider, "bind_writer", None)
        if bind_writer is not None:
            bind_writer(writer)
        if callable(self.array_description):
            array_description = self.array_description(driver)
        elif self.array_description is not None:
            array_description = self.array_description
        else:
            array_description = NDArrayDescription(
                shape_signals=[
                    # driver.array_size_z,  # Adds an extra dimension to the stream resource
                    driver.array_size_y,
                    driver.array_size_x,
                ],
                data_type_signal=driver.data_type,
                color_mode_signal=driver.color_mode,
            )
        if self.data_logic_factory is not None:
            logic = self.data_logic_factory(
                writer, array_description, driver, plugins, self.file_template
            )
        elif self.writer_cls is NDFileHDF5IO:
            logic = ConfigurableHDFDataLogic(
                array_description=array_description,
                path_provider=self.path_provider,
                writer=writer,
                driver=driver,
                plugins=list(plugins),
                datakey_suffix=self.datakey_suffix,
                file_template=self.file_template or "%s%s.h5",
            )
        else:
            logic = ConfigurableMultipartDataLogic(
                array_description=array_description,
                path_provider=self.path_provider,
                writer=writer,
                extension=self.extension,
                mimetype=self.mimetype,
                datakey_suffix=self.datakey_suffix,
                file_template=self.file_template,
            )
        return writer, logic

    path_provider: PathProvider = None
    extension: str = ""
    mimetype: str = ""


def hdf(
    path_provider: PathProvider,
    writer_suffix: str = "HDF1:",
    writer_name: str = "hdf",
    datakey_suffix: str = "",
    array_description: NDArrayDescription | Callable | None = None,
    file_template: str = "%s%s.h5",
) -> ConfigurableWriterFactory:
    """Create a configurable HDF5 writer factory.

    Parameters
    ----------
    path_provider:
        Supplies the IOC directory and basename for each acquisition.
    writer_suffix:
        HDF plugin PV suffix.
    writer_name:
        Attribute name assigned to the writer on the detector.
    datakey_suffix:
        Suffix appended to the detector data key.
    array_description:
        Optional array description or callable producing one from the driver.
    file_template:
        AreaDetector ``FileTemplate`` value, defaulting to ``%s%s.h5``.

    Example
    -------
    ``hdf(path_provider, file_template=\"%s%s_%3.3d.h5\")``
    """
    return ConfigurableWriterFactory(
        writer_cls=NDFileHDF5IO,
        writer_suffix=writer_suffix,
        writer_name=writer_name,
        datakey_suffix=datakey_suffix,
        array_description=array_description,
        file_template=file_template,
        path_provider=path_provider,
    )


def jpeg(
    path_provider: PathProvider,
    writer_suffix: str = "JPEG1:",
    writer_name: str = "jpeg",
    datakey_suffix: str = "",
    array_description: NDArrayDescription | Callable | None = None,
    file_template: str | None = None,
) -> ConfigurableWriterFactory:
    """Create a configurable JPEG writer factory.

    ``file_template`` defaults to the upstream six-digit JPEG template.
    """
    return ConfigurableWriterFactory(
        writer_cls=NDPluginFileIO,
        writer_suffix=writer_suffix,
        writer_name=writer_name,
        datakey_suffix=datakey_suffix,
        array_description=array_description,
        file_template=file_template,
        path_provider=path_provider,
        extension=".jpg",
        mimetype="multipart/related;type=image/jpeg",
    )


def tiff(
    path_provider: PathProvider,
    writer_suffix: str = "TIFF1:",
    writer_name: str = "tiff",
    datakey_suffix: str = "",
    array_description: NDArrayDescription | Callable | None = None,
    file_template: str | None = None,
) -> ConfigurableWriterFactory:
    """Create a configurable TIFF writer factory.

    ``file_template`` defaults to the upstream six-digit TIFF template.
    """
    return ConfigurableWriterFactory(
        writer_cls=NDPluginFileIO,
        writer_suffix=writer_suffix,
        writer_name=writer_name,
        datakey_suffix=datakey_suffix,
        array_description=array_description,
        file_template=file_template,
        path_provider=path_provider,
        extension=".tiff",
        mimetype="multipart/related;type=image/tiff",
    )
