import os
import shutil
import tempfile
from pathlib import Path
from typing import Protocol


class GenerationProvider(Protocol):
    def generate_still(
        self,
        *,
        prompt: str,
        reference_paths: tuple[Path, ...],
        seed: int | None,
        output_path: Path,
    ) -> Path: ...


class ReferenceCopyProvider:
    def generate_still(
        self,
        *,
        prompt: str,
        reference_paths: tuple[Path, ...],
        seed: int | None,
        output_path: Path,
    ) -> Path:
        del prompt, seed
        if not reference_paths:
            raise ValueError("at least one reference path is required")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output_path.parent, prefix=".generated-"
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as destination:
                with Path(reference_paths[0]).open("rb") as source:
                    shutil.copyfileobj(source, destination)
                    destination.flush()
                    os.fsync(destination.fileno())
            os.replace(temporary_path, output_path)
        finally:
            temporary_path.unlink(missing_ok=True)

        return output_path
