"""Date-based path provider for the basic ADSim campaign example."""

from __future__ import annotations

from datetime import date
from pathlib import PurePath

from ophyd_async.core import FilenameProvider
from ophyd_async.core import PathInfo
from ophyd_async.core import PathProvider


class ExampleDatePathProvider(PathProvider):
    """Provide ``example/YYYY/MM/DD`` paths without a device subdirectory."""

    def __init__(
        self,
        filename_provider: FilenameProvider,
        directory_path: PurePath,
        directory_uri: str,
        create_dir_depth: int = -3,
    ) -> None:
        self.filename_provider = filename_provider
        self.directory_path = directory_path
        self.directory_uri = directory_uri.rstrip("/")
        self.create_dir_depth = create_dir_depth

    def __call__(self, device_name: str | None = None) -> PathInfo:
        """Return today's IOC path and client URI."""
        ymd = date.today().strftime("%Y/%m/%d")
        return PathInfo(
            directory_path=self.directory_path / ymd,
            directory_uri=f"{self.directory_uri}/{ymd}/",
            filename=self.filename_provider(device_name),
            create_dir_depth=self.create_dir_depth,
        )
