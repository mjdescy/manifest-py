import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from manifest_py.builder import ManifestBuilder
from manifest_py.manifest import Manifest, ManifestMetadata
from manifest_py.serialize import (
    dump_csv,
    dump_json,
    metadata_sidecar_path,
    write_csv,
    write_json,
    write_metadata_csv,
)

app = typer.Typer(help="Create a manifest of one or more directory trees.")


class Format(StrEnum):
    json = "json"
    csv = "csv"


@app.command()
def main(
    roots: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Root folder(s) of the directory trees to include.",
        ),
    ],
    format: Annotated[
        Format, typer.Option("--format", "-f", help="Output format.")
    ] = Format.json,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write to this file instead of stdout."),
    ] = None,
) -> None:
    """Create a manifest (path, size, mtime, SHA-256) of directory trees."""
    manifest: Manifest = Manifest.union(
        *(ManifestBuilder.from_directory(str(r)) for r in roots)
    )
    metadata: ManifestMetadata = ManifestMetadata.for_manifest(
        manifest, (str(r) for r in roots)
    )
    try:
        if output is not None:
            if format is Format.json:
                write_json(manifest, output, metadata=metadata)
            else:
                write_csv(manifest, output)
                write_metadata_csv(metadata, metadata_sidecar_path(output))
        elif format is Format.json:
            dump_json(manifest, sys.stdout, metadata=metadata)
            sys.stdout.write("\n")
        else:
            dump_csv(manifest, sys.stdout)
    except OSError as err:
        typer.echo(f"Error: cannot write output: {err}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
