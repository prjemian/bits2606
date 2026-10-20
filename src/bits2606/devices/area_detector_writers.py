"""Configurable AreaDetector file-writer factories.

The upstream ophyd-async data logic writes fixed FileTemplate PV values.
These local variants make the templates configurable while retaining the
upstream HDF5, JPEG, and TIFF behavior.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass

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
    ADHDFDataLogic,
    ADMultipartDataLogic,
    NDArrayDescription,
    get_ndarray_resource_info,
    get_ndattribute_dtype_source,
    prepare_file_paths,
)
from ophyd_async.epics.adcore._io import (
    NDArrayBaseIO,
    NDFileHDF5IO,
    NDPluginBaseIO,
    NDPluginFileIO,
)
from ophyd_async.epics.core import stop_busy_record


@dataclass
class ConfigurableHDFDataLogic(ADHDFDataLogic):
    """HDF5 data logic with a configurable FileTemplate PV value."""

    file_template: str = "%s%s.h5"

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        path_info = self.path_provider(datakey_name)
        frames_per_chunk = await self.writer.num_frames_chunks.get_value()
        if frames_per_chunk == 0:
            frames_per_chunk = 1
            await self.writer.num_frames_chunks.set(frames_per_chunk)

        await asyncio.gather(
            self.writer.chunk_size_auto.set(True),
            self.writer.num_extra_dims.set(0),
            self.writer.lazy_open.set(True),
            self.writer.swmr_mode.set(True),
            self.writer.xml_file_name.set(""),
            self.writer.enable_callbacks.set(EnableDisable.ENABLE),
            prepare_file_paths(
                path_info=path_info,
                file_template=self.file_template,
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
        return StreamResourceDataProvider(
            uri=f"{path_info.directory_uri}{path_info.filename}.h5",
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
        if callable(self.array_description):
            array_description = self.array_description(driver)
        elif self.array_description is not None:
            array_description = self.array_description
        else:
            array_description = NDArrayDescription(
                shape_signals=[
                    # driver.array_size_z,  # TODO: use logic to include?
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
