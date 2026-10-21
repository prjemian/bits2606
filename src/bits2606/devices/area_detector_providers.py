"""AreaDetector-backed filename and path providers.

These providers adapt EPICS file-path signals to the synchronous
ophyd-async FilenameProvider and PathProvider protocols. They can be
constructed declaratively and bound to their writer when the detector is
assembled. Call ``update`` while connected before passing a provider to
detector data logic.
"""

import logging
from dataclasses import dataclass
from pathlib import PurePath

from ophyd_async.core import FilenameProvider, PathInfo, PathProvider
from ophyd_async.epics.adcore import NDPluginFileIO


logger = logging.getLogger(__name__)


@dataclass
class ADFilenameProvider(FilenameProvider):
    """Provide the basename from an AreaDetector writer's FileName PV."""

    writer: NDPluginFileIO | None = None
    filename: str | None = None

    def __post_init__(self) -> None:
        if not self.filename:
            logger.warning("AreaDetector FileName PV is empty when provider is created")

    def bind_writer(self, writer: NDPluginFileIO) -> None:
        """Bind the writer after declarative construction."""
        self.writer = writer

    async def update(self) -> str:
        """Read and cache the current filename from the writer."""
        if self.writer is None:
            raise RuntimeError("Bind a writer before updating the filename")
        self.filename = await self.writer.file_name.get_value(cached=False)
        if not self.filename:
            logger.warning("AreaDetector FileName PV is empty")
            raise ValueError("AreaDetector FileName PV is empty")
        return self.filename

    def __call__(self, datakey_name: str | None = None) -> str:
        if not self.filename:
            raise ValueError("AreaDetector FileName PV is empty")
        return self.filename


@dataclass
class ADPathProvider(PathProvider):
    """Provide a PathInfo from an AreaDetector writer's FilePath PV."""

    writer: NDPluginFileIO | None = None
    directory_uri: str | None = None
    create_dir_depth: int = 0
    filename_provider: ADFilenameProvider | None = None
    directory_path: PurePath | None = None

    def __post_init__(self) -> None:
        """Runs after the constructor..."""
        if self.filename_provider is None:
            self.filename_provider = ADFilenameProvider()
        if self.writer is not None:
            self.bind_writer(self.writer)

    def bind_writer(self, writer: NDPluginFileIO) -> None:
        """Bind the writer and its filename provider after construction."""
        self.writer = writer
        self.filename_provider.bind_writer(writer)

    async def update(self) -> PathInfo:
        """Read and cache the current writer path and filename."""
        if self.writer is None:
            raise RuntimeError("Bind a writer before updating the path")
        directory_path = await self.writer.file_path.get_value(cached=False)
        self.directory_path = PurePath(directory_path)
        await self.filename_provider.update()
        return self()

    def __call__(self, datakey_name: str | None = None) -> PathInfo:
        if self.writer is None:
            raise RuntimeError("Bind a writer before requesting a path")
        if self.directory_path is None:
            raise RuntimeError("Call `await update()` before requesting a path")
        kwargs = {
            "directory_path": self.directory_path,
            "filename": self.filename_provider(datakey_name),
            "create_dir_depth": self.create_dir_depth,
        }
        if self.directory_uri is not None:
            kwargs["directory_uri"] = self.directory_uri
        return PathInfo(**kwargs)
