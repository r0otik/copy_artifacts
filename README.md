# copy_artifacts

## Script Purpose

`copyArtifacts.py` is designed to:
- copy large volumes of files from remote hosts (SFTP/SSH),
- select files by date and filename pattern,
- optionally unpack `.gz` files.

---

## Configuration File Format

The script uses a configuration file in **INI** format.

Example filename:
```text
config_copyArtifacts.ini
```

The configuration consists of:
- a mandatory `[general]` section;
- one or more copy source sections (arbitrary section names).

---

## [general] Section

The `[general]` section contains **global execution parameters** that apply to all copy sources using an *override* mechanism similar to systemd units.

This means:
- parameters defined in `[general]` apply to all source sections;
- if the same parameter is defined in a source section, it **overrides** the value from `[general]`.

Example:
```ini
[general]
host=myhost.test.local
username=myuser
port=22
download_dirs=test_art
download_date=2025/11/24
keypath=/export/home/myuser/.ssh/id_rsa
protocol=sftp
unpack_gz=True
```

---

## Copy Source Sections

Each additional section describes a **separate file source**.

The section name is arbitrary, but it must match one of the values listed in `download_dirs`.

Example:
```ini
[test_art]
host=localhost
remote_path=/data/ART/
local_path=/data/sources_art/
file_pattern=ARHFBMS.*
unpack_gz=False
outfile_suffix=.j2
```

---

## Available Parameters

| Name | Description | Notes |
| ---- | ----------- | ----- |
| `host` | Host to connect to | If `localhost` is specified, all found files will be hard-linked |
| `username` | Username for connection | |
| `port` | Connection port | Default: 22 |
| `protocol` | File transfer protocol | Possible values: `sftp` or `ssh`<br>Default: `ssh`<br>SFTP provides higher throughput and is recommended when performance matters |
| `keypath` | Path to RSA key for SSH authentication | If specified, password authentication is skipped. If a key is defined in `[general]` but password auth is required for a specific host, define an empty value (`keypath=`) in that section |
| `download_dirs` | Logical names of download directions | **Only for `[general]` section**<br>Comma-separated list; each name must have a corresponding section below<br>Only listed directions are processed, unused sections may remain in config<br>Example: `test_art,ssdg,sources` |
| `download_date` | Date of files to download | Format: `yyyy/mm/dd`<br>This date is substituted into `%date%` templates. After `%date%`, a date format must be specified (see config example). Template can be used in `remote_path`, `local_path`, `subdir_pattern`, and `file_pattern` |
| `remote_path` | Path to files on remote host | |
| `local_path` | Path to store files locally | Created automatically if it does not exist |
| `file_pattern` | Regular expression to match filenames | Default: `.*`<br>Example: `ARHFBMS.*\\.gz` |
| `outfile_suffix` | Suffix appended to downloaded or unpacked files | Example: `.j2`<br>Useful when files must already have required extensions |
| `mtime_choice` | Select files by modification time | Values: `True` / `False`<br>Default: `False`<br>When `True`, files matching `file_pattern` and modified between `download_date 00:00:00` and the next day `00:00:00` are selected. Useful when filenames do not contain timestamps |
| `unpack_gz` | Unpack downloaded files | Values: `True` / `False`<br>Default: `False`<br>Unpacking is performed after all directions are downloaded<br>Only `.gz` files are unpacked |
| `recursive_search` | Recursive file search | Enables recursive search inside `remote_path` subdirectories |
| `subdir_pattern` | Subdirectory filter regex | Filters subdirectories during recursive search |
| `repeat_struct` | Replicate remote directory structure | When recursive search is enabled, remote directory structure is recreated locally |

---

## Configuration Example

```ini
[general]
host=myhost.test.local
username=myuser
port=22
download_dirs=test_art
download_date=2025/11/24
keypath=/export/home/myuser/.ssh/id_rsa
protocol=sftp
unpack_gz=True

[test_art]

host=localhost
remote_path=/data/ART/
local_path=/data/sources_art/
file_pattern=ARHFBMS.*
mtime_choice=True
unpack_gz=False
outfile_suffix=.j2

[art_prod]

keypath=./ansible_key
host=prod_host.test.local
remote_path=/data/ART/
local_path=/data/etalons_art/
file_pattern=%date%ARHFBMS.*,%Y%m%d
unpack_gz=False
outfile_suffix=.j2
```

---

## Common Errors

- Mismatch between section name and `download_dirs`
- Invalid SSH key path
- Incorrect date format in `file_pattern`
- Insufficient permissions on remote directory


