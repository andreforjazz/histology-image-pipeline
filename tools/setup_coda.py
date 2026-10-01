"""Copy the required CODA files from a user-provided checkout into the local project."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='CODA update 12-13-2023 directory from your local copy or upstream checkout')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    entries = json.loads((root / 'docs/matlab_sources.json').read_text())
    copies = []
    for entry in entries:
        relative = Path(entry['destination'].replace('\\', '/'))
        # Keep file selection fixed to the audited manifest.
        source_relative = Path(*relative.parts[2:])
        source = args.source / source_relative
        target = root / relative
        if not source.is_file():
            parser.error(f'Required file not found: {source}')
        if target.exists() and target.read_bytes() != source.read_bytes():
            parser.error(f'Refusing to overwrite a different local file: {target}')
        copies.append((source, target, entry['original_sha256']))
    differences = 0
    for source, target, expected in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        if hashlib.sha256(source.read_bytes()).hexdigest().upper() != expected:
            differences += 1
            print(f'NOTICE: {source.name} differs from the locally validated CODA snapshot.')
    print(f'Installed {len(copies)} CODA files; {differences} differ from the validation snapshot.')
    if differences:
        print('Rerun MATLAB integration validation before processing research images.')


if __name__ == '__main__':
    main()
