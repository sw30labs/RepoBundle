import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from export_repo import export_repository
from import_repo import restore_repository


def _walk_files(root):
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for name in filenames:
            if name.startswith('.'):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root)
            result[str(rel)] = full.read_bytes()
    return result


def test_roundtrip_byte_identical():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / 'source'
        source.mkdir()

        # (a) text file WITH trailing newline
        (source / 'with_newline.txt').write_text('hello\n', encoding='utf-8')
        # (b) text file WITHOUT trailing newline
        (source / 'no_newline.txt').write_text('world', encoding='utf-8')
        # (c) binary file with null bytes
        (source / 'data.bin').write_bytes(b'\x00\x01\x02\x00\xff\x00')
        # (d) file in a nested subdir
        nested = source / 'nested' / 'deep'
        nested.mkdir(parents=True)
        (nested / 'nested.txt').write_text('nested content\n', encoding='utf-8')

        # bundle written OUTSIDE the source tree
        bundle_dir = tmp_path / 'bundles'
        bundle_dir.mkdir()
        bundle = bundle_dir / 'export.txt'

        export_repository(source, bundle, log=None)
        assert bundle.exists()

        restore_dir = tmp_path / 'restored'
        restore_repository(bundle, restore_dir, log=None)

        original = _walk_files(source)
        restored = _walk_files(restore_dir)

        assert set(original) == set(restored)
        for rel, data in original.items():
            assert restored[rel] == data, f"Mismatch for {rel}"
