"""Archive the portable distribution, always shipping an empty backup directory."""

from pathlib import Path
import os
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED


def package_portable(directory: Path, destination: Path) -> None:
    directory = directory.resolve(strict=True)
    (directory / "backup").mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(dir=destination.parent, suffix=".zip")
    os.close(fd)
    temporary = Path(name)

    def raise_walk_error(error: OSError) -> None:
        raise error

    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(f"{directory.name}/backup/", b"")
            for folder, children, files in os.walk(directory, onerror=raise_walk_error):
                path = Path(folder)
                if path == directory:
                    children[:] = [child for child in children if child.casefold() != "backup"]
                archive.write(path, path.relative_to(directory.parent))
                for file in files:
                    item = path / file
                    archive.write(item, item.relative_to(directory.parent))
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    package_portable(Path(sys.argv[1]), Path(sys.argv[2]))
