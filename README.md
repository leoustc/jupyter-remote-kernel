
# Jupyter Remote Kernel

A CLI tool for launching and managing remote Jupyter kernels over **native SSH** port forwarding.

## Features

- **Pure native `ssh`/`scp`** for tunneling and file transfer (no Paramiko)
- **SSH config integration**: uses your SSH config (supports jump hosts via `ProxyJump`, custom keys, etc.).
- **Kernel spec management**: `add`, `list`, `delete` for seamless integration with Jupyter & VS Code
- **Automatic remote probe**: verifies remote **Python** and **`ipykernel`** before launching
- **Verbose logging** for easier troubleshooting

---

## Simple Architecture

```plaintext
[ JupyterLab / VS Code ]
            |
    ~/.local/share/jupyter/kernels/<slug>/kernel.json
            |
     [ remote_kernel CLI ]
            |
  SSH -L tunnels  <====>  [ Remote Host: ipykernel + Python ]
            |
   /tmp/<connection file> copied to remote before launch
```

---

## Installation

```bash
pip install jupyter_remote_kernel
```

---

## CLI Usage

### Subcommands

```bash
remote_kernel add <HostAlias> [--name "Display Name"] [--python /path/to/python]
remote_kernel list
remote_kernel delete <slug-or-name>

# (invoked by Jupyter/VS Code)
remote_kernel --endpoint <HostAlias> -f {connection_file} [--python /path/to/python]
```

- `<HostAlias>` must exist in your SSH config (`~/.ssh/config` by default, or file pointed by `SSH_CONFIG`).
- If `--name` is omitted in `add`, the display name defaults to `<HostAlias>`.

### Add a remote kernel

```bash
remote_kernel add gpuhost --name "Remote CUDA" --python /usr/bin/python3
```

Creates `~/.local/share/jupyter/kernels/remote_cuda/kernel.json` similar to:

```json
{
  "argv": [
    "/path/to/remote_kernel",
    "--endpoint", "gpuhost",
    "-f", "{connection_file}",
    "--python", "/usr/bin/python3"
  ],
  "display_name": "Remote CUDA",
  "language": "python"
}
```

### List and delete

```bash
remote_kernel list
remote_kernel delete remote_cuda
```

---

## SSH Config Example

```sshconfig
Host gpuhost
    HostName 10.0.0.5
    User ubuntu
    Port 22
    # Jump/bastion handled here, not with CLI flags:
    ProxyJump bastion.example.com
    IdentityFile ~/.ssh/id_ed25519
```

Use a custom config file:

```bash
export SSH_CONFIG=/path/to/ssh_config
remote_kernel add gpuhost --name "GPU Host"
```

---

## How It Works (Runtime)

1. Jupyter launches: `remote_kernel --endpoint <HostAlias> -f {connection_file} [--python ...]`
2. CLI **probes the remote** to ensure `<python>` exists and `ipykernel` is importable.
3. CLI **copies** the local `{connection_file}` to the remote as `/tmp/<basename>.json` via `scp`.
4. CLI opens **`ssh -L` port forwards** for all 5 ZMQ channels using the ports from the JSON.
5. CLI runs on the remote: `python -m ipykernel_launcher -f /tmp/<basename>.json`.

> The SSH session remains open to keep the port forwardings alive. Closing it ends the kernel session.

---

## Troubleshooting

- **`channel XX: open failed: connect failed: Connection refused`**  
  One or more forwarded ports failed to bind on the remote. Ensure the SSH session stays open and that no other process uses those ports. Re-run after a few seconds.

- **`ModuleNotFoundError: No module named 'pexpect'` (seen from IPython)**  
  Install missing dependencies on the **remote**:
  ```bash
  python -m pip install --upgrade ipykernel pexpect
  ```

- **`Python binary 'X' not found on remote`**  
  The specified `--python` doesn’t exist in the remote PATH. Verify with:
  ```bash
  ssh <HostAlias> "sh -lc 'command -v /path/to/python || which /path/to/python'"
  ```

- **Custom SSH config**  
  Set `SSH_CONFIG` to point the CLI at a specific SSH config file:
  ```bash
  export SSH_CONFIG=/path/to/ssh_config
  ```

---

## License

Apache License Version 2.0, January 2004

---

# Changelog

## [2.6.2] - 2025-08-15
**Improvements**
- `add` accepts positional `<HostAlias>` and defaults display name to the alias when `--name` is omitted.
- Added `SSH_CONFIG` support and host listing when arguments are missing.
- Hardened remote probe using `subprocess.run` only and POSIX shell (`sh -lc`) for portability.
- Runtime uses `scp` to copy `{connection_file}` and `ssh -L` to forward all five ports.
- README overhauled to reflect native SSH-only workflow.

## [2.6.1] - 2025-08-15
**Major Changes**
- Dropped Paramiko and all Python SSH/SCP code.
- All operations now use **pure native `ssh` and `scp`**.
- Jump hosts handled exclusively via SSH config.

## [2.3.3] - 2025-07-31
**New Features**
- Added `rkernel` shortcut command for quicker access.

## [2.3.2] - 2025-07-31
**New Features**
- Added `sync` subcommand for file transfers (`scp` by default, Paramiko fallback).
- Expanded native SSH/SCP support with unified handling.
**Bug Fixes**
- Fixed stale connection file cleanup.
- Improved `--python` remote interpreter handling.

## [2.3.0] - 2025-07-31
**New Features**
- Native SSH usage for all operations.
- Native SCP for faster transfers.
- Simplified execution flow.
**Bug Fixes**
- Fixed tunnel init inconsistencies.
- Improved cleanup after kernel exit.

## [2.2.0] - 2025-07-30
**New Features**
- Native SSH by default.
- Paramiko fallback.
- Simplified error handling.

## [2.1.1] - 2025-07-28
**New Features**
- Full Python SSH/SCP via Paramiko.
- Integrated SSH tunneling.
- Interactive sessions.
- Kernel auto-cleanup.
- Streamlined CLI commands.
**Bug Fixes**
- Fixed Paramiko socket conflicts and tunnel race conditions.
- Reduced log spam.

## [2.0.0] - 2025-07-28
**Major Changes**
- Migrated to `paramiko`/`sshtunnel`.
- Added jump host support via SSH config.
**Breaking Changes**
- System SSH/SCP not used by default.

## [1.6.0] - 2025-07-28
**Added**
- `remote_kernel connect`
- `remote_kernel -v` and `-h` support.
