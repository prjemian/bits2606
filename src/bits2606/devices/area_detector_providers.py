"""AreaDetector-backed filename and path providers.

These providers adapt EPICS file-path signals to the synchronous
ophyd-async FilenameProvider and PathProvider protocols. Call ``update``
while connected before passing a provider to detector data logic.
"""

from dataclasses import dataclass
from pathlib import PurePath

from ophyd_async.core import FilenameProvider, PathInfo, PathProvider
from ophyd_async.epics.adcore import NDPluginFileIO


@dataclass
class ADFilenameProvider(FilenameProvider):
    """Provide the basename from an AreaDetector writer's FileName PV."""

    writer: NDPluginFileIO
    filename: str | None = None

    async def update(self) -> str:
        """Read and cache the current filename from the writer."""
        self.filename = await self.writer.file_name.get_value(cached=False)
        return self.filename

    def __call__(self, datakey_name: str | None = None) -> str:
        if self.filename is None:
            raise RuntimeError("Call `await update()` before requesting a filename")
        return self.filename


@dataclass
class ADPathProvider(PathProvider):
    """Provide a PathInfo from an AreaDetector writer's FilePath PV."""

    writer: NDPluginFileIO
    directory_uri: str | None = None
    create_dir_depth: int = 0
    filename_provider: ADFilenameProvider | None = None
    directory_path: PurePath | None = None

    def __post_init__(self) -> None:
        if self.filename_provider is None:
            self.filename_provider = ADFilenameProvider(self.writer)

    async def update(self) -> PathInfo:
        """Read and cache the current writer path and filename."""
        directory_path = await self.writer.file_path.get_value(cached=False)
        self.directory_path = PurePath(directory_path)
        await self.filename_provider.update()
        return self()

    def __call__(self, datakey_name: str | None = None) -> PathInfo:
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
