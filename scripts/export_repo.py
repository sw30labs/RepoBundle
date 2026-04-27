#!/usr/bin/env python3
# =========================================================================
# export_repo.py
# =========================================================================
# Author: Nic Cravino
# Created: May 25th, 2025
# =========================================================================
# This script exports a repository's structure and contents to a single, human-readable text file. Binary files are base64 encoded.
# =========================================================================
# License Apache 2 ...
#

import base64
import datetime
import os
from pathlib import Path


def _emit(log, message):
    if log is not None:
        log(message)


def default_output_path(root_dir, output_dir=None):
    """Return the timestamped export path for a repository."""
    root_path = Path(root_dir).expanduser().resolve()
    base_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return base_dir / f"{root_path.name}_export_{timestamp}.txt"


def is_binary(file_path, log=print):
    """Check if a file is binary."""
    try:
        with open(file_path, 'rb') as f:
            # Read first 8000 bytes to check for binary content
            chunk = f.read(8000)
            # Check for null bytes or high byte values
            if b'\x00' in chunk:
                return True
            # Try to decode as text
            try:
                chunk.decode('utf-8')
            except UnicodeDecodeError:
                return True
    except Exception as e:
        _emit(log, f"Error checking if file is binary: {e}")
        return True
    return False


def get_file_contents(file_path, relative_path=None, binary=None, log=print):
    """Get file contents with appropriate encoding."""
    if binary is None:
        binary = is_binary(file_path, log=log)

    if binary:
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return f"\n[Binary file - {len(content)} bytes - base64 encoded]\n{base64.b64encode(content).decode('ascii')}\n"
        except Exception as e:
            return f"\n[Error reading binary file: {e}]\n"
    else:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"\n[Error reading file: {e}]\n"


def export_repository(root_dir, output_file=None, log=print, progress=None):
    """Export repository structure and contents to a single text file."""
    root_path = Path(root_dir).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Repository not found: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root_path}")

    output_path = Path(output_file).expanduser().resolve() if output_file else default_output_path(root_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        'output_path': str(output_path),
        'files': 0,
        'text_files': 0,
        'binary_files': 0,
        'directories': 0,
        'errors': 0,
        'bytes': 0,
    }

    _emit(log, f"Exporting repository from: {root_path}")
    _emit(log, f"Output file: {output_path}")

    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Write header
        outfile.write("=" * 80 + "\n")
        outfile.write(f"REPOSITORY EXPORT: {root_path.name}\n")
        outfile.write(f"Generated on: {datetime.datetime.now().isoformat()}\n")
        outfile.write("=" * 80 + "\n\n")
        
        # Walk through the directory
        for current_dir, dirs, files in os.walk(root_path):
            # Skip hidden directories (like .git)
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            dirs.sort()
            
            relative_dir = Path(current_dir).relative_to(root_path)
            
            # Write directory header
            if str(relative_dir) != '.':
                summary['directories'] += 1
                outfile.write("\n" + "#" * 80 + "\n")
                outfile.write(f"DIRECTORY: {relative_dir}\n")
                outfile.write("#" * 80 + "\n\n")
            
            # Process files
            for file in sorted(files):
                if file.startswith('.'):
                    continue  # Skip hidden files
                    
                file_path = Path(current_dir) / file
                if file_path.resolve() == output_path:
                    continue

                relative_file_path = relative_dir / file
                
                # Write file header
                outfile.write("\n" + "-" * 60 + "\n")
                outfile.write(f"FILE: {relative_file_path}\n")
                outfile.write("-" * 60 + "\n\n")
                
                # Write file contents
                try:
                    binary = is_binary(file_path, log=log)
                    content = get_file_contents(file_path, relative_file_path, binary=binary, log=log)
                    outfile.write(content)
                    if not content.endswith('\n'):
                        outfile.write('\n')
                    summary['files'] += 1
                    if binary:
                        summary['binary_files'] += 1
                    else:
                        summary['text_files'] += 1
                    if content.startswith("\n[Error"):
                        summary['errors'] += 1
                except Exception as e:
                    outfile.write(f"[Error processing file: {e}]\n")
                    summary['errors'] += 1
                
                outfile.write("\n" + "=" * 60 + "\n\n")
                if progress is not None:
                    progress(dict(summary))
    
    summary['bytes'] = os.path.getsize(output_path)
    _emit(log, f"\nExport completed successfully to: {output_path}")
    _emit(log, f"Total size: {summary['bytes'] / (1024 * 1024):.2f} MB")
    if progress is not None:
        progress(dict(summary))
    return summary

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        root_directory = sys.argv[1]
    else:
        root_directory = os.getcwd()
    
    output_filename = default_output_path(root_directory)
    
    try:
        export_repository(root_directory, output_filename)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
