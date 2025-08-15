#!/usr/bin/env python3
"""
remote_kernel CLI (SSH-config driven)

Subcommands:
  add       --endpoint <HostAlias> --name <Display Name> [--python /path/to/python]
  list
  delete    <slug-or-name>

Kernel launch path (used by Jupyter's kernel.json):
  remote_kernel --endpoint <HostAlias> -f {connection_file} [--python /path/to/python]

Behavior:
- Reads the *local* Jupyter connection JSON (-f) to get ports + key/etc.
- Copies that JSON to the remote (scp to /tmp/<basename>).
- Opens ssh -L tunnels for all 5 ports to the remote (using ~/.ssh/config).
- Executes `python -m ipykernel_launcher -f /tmp/<basename>` on the remote.
- No jump-host flags here; ProxyJump/ProxyCommand should be in ~/.ssh/config.
"""

import sys
import os
import json
import shutil
import time
import subprocess
import shlex
from typing import Optional, Tuple, List, Dict, Any


from remote_kernel import KERNELS_DIR, PYTHON_BIN, log, usage, version, SSH_CONFIG


# ---------------------------
# Helpers
# ---------------------------

def _list_ssh_config_hosts() -> List[str]:
    """Parse ~/.ssh/config and return a list of host aliases (excluding '*')."""
    cfg_path = os.path.expanduser(SSH_CONFIG)
    if not os.path.exists(cfg_path):
        return []
    hosts: List[str] = []
    try:
        with open(cfg_path) as f:
            for line in f:
                s = line.strip()
                if s.lower().startswith("host ") and not s.lower().startswith("host *"):
                    parts = s.split()
                    # Support lines like: Host gpu-core hpc-node1
                    for name in parts[1:]:
                        if name != "*" and name not in hosts:
                            hosts.append(name)
    except Exception as e:
        log(f"WARNING: Failed to read {cfg_path}: {e}")
    return hosts


def _arg(flag: str, default: Optional[str] = None) -> Optional[str]:
    """Return value following a flag if present, else default."""
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _read_connection_file(conn_file: str) -> Tuple[Optional[List[int]], Optional[dict]]:
    """
    Load ports and the raw config from a Jupyter kernel connection file.
    Returns (ports_list, full_cfg_dict) or (None, None) on error.
    """
    if not os.path.exists(conn_file):
        log(f"ERROR: Connection file not found: {conn_file}")
        return None, None

    try:
        with open(conn_file) as f:
            cfg = json.load(f)
    except Exception as e:
        log(f"ERROR: Failed to parse connection file {conn_file}: {e}")
        return None, None

    try:
        ports = [int(cfg[k]) for k in ("shell_port", "iopub_port", "stdin_port", "control_port", "hb_port")]
    except KeyError as e:
        log(f"ERROR: Missing key in connection file: {e}")
        return None, None
    except (TypeError, ValueError) as e:
        log(f"ERROR: Invalid port value in {conn_file}: {e}")
        return None, None

    return ports, cfg


def _run(cmd: List[str], desc: str, check: bool = True) -> int:
    """Run a subprocess with logging; returns returncode (raises if check=True)."""
    pretty = shlex.join(cmd)
    log(f"{desc}: {pretty}")
    try:
        res = subprocess.run(cmd, check=check)
        log(f"{desc} -> returncode={res.returncode}")
        return res.returncode
    except subprocess.CalledProcessError as e:
        log(f"ERROR during {desc}: returncode={e.returncode}")
        raise
    except FileNotFoundError:
        log(f"ERROR during {desc}: command not found: {cmd[0]}")
        raise


def _probe_remote(endpoint: str, python_bin: str) -> bool:
    """
    Check remote Python and ipykernel availability.
    Returns:
      {
        "python_present": bool,
        "python_version": str or None,
        "ipykernel_present": bool,
        "ipykernel_version": str or None
      }
    """
    # Step 1: Check if python exists
    check_cmd = ["ssh", endpoint, f"which {shlex.quote(python_bin)}"]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        python_present = bool(res.stdout.strip())
    except subprocess.CalledProcessError:
        python_present = False

    if not python_present:
        log(f"ERROR: Python binary '{python_bin}' not found on remote '{endpoint}'.")
        log(f"python_version        : None")
        log(f"ipykernel_version     : None")        
        return False

    # Step 2: Get Python + ipykernel info
    code = (
        "import json,sys,importlib.util;"
        "pv=sys.version.split()[0];"
        "spec=importlib.util.find_spec('ipykernel');"
        "iv=__import__('ipykernel').__version__ if spec else None;"
        "print(json.dumps({'python_version': pv, 'ipykernel_present': bool(spec), 'ipykernel_version': iv}))"
    )
    remote_cmd = f"{shlex.quote(python_bin)} -c {shlex.quote(code)}"
    ssh_cmd = ["ssh", endpoint, remote_cmd]
    try:
        res = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        log(f"python_version        : {data.get("python_version")}")
        log(f"ipykernel_version     : {data.get("ipykernel_version")}") 
        return True
    except subprocess.CalledProcessError:
        log("ERROR: Failed to get Python/ipykernel info from remote.")
        return False



# ---------------------------
# Core actions
# ---------------------------

def start_kernel(endpoint: str, conn_file: str, python_bin: str) -> None:
    """
    1) Read local connection file to get ports (for ssh -L mapping) and cfg
    2) Copy that connection file to remote via scp (keep basename)
    3) Launch remote ipykernel using: python -m ipykernel_launcher -f /tmp/<basename>
    """
    ports, cfg = _read_connection_file(conn_file)
    if ports is None:
        return

    shell_p, iopub_p, stdin_p, control_p, hb_p = ports
    basename = os.path.basename(conn_file)
    remote_file = f"/tmp/{basename}"

    log("=== remote_kernel START ===")
    log(f"Endpoint          : {endpoint}")
    log(f"Local conn file   : {conn_file}")
    log(f"Remote conn file  : {remote_file}")
    log(f"Python (remote)   : {python_bin}")
    log(f"Ports             : shell={shell_p}, iopub={iopub_p}, stdin={stdin_p}, control={control_p}, hb={hb_p}")
    log(f"Transport         : {cfg.get('transport', 'tcp')}")
    log(f"Kernel name       : {cfg.get('kernel_name', '')}")
    log(f"Signature scheme  : {cfg.get('signature_scheme', '')}")
    log(f"IP (in file)      : {cfg.get('ip', '')}")

    # 2) Copy connection file to remote
    try:
        _run(["scp", "-q", conn_file, f"{endpoint}:{remote_file}"], "SCP connection file", check=True)
    except Exception:
        log("Aborting due to SCP failure.")
        return

    # 3) Build ssh -L and remote command
    remote_cmd = f"{shlex.quote(python_bin)} -m ipykernel_launcher -f {shlex.quote(remote_file)}"
    ssh_cmd = [
        "ssh",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=5",
        # No -t: ipykernel is not interactive; keep session open to hold forwards
    ]
    for p in ports:
        ssh_cmd += ["-L", f"{p}:localhost:{p}"]
    ssh_cmd += [endpoint, remote_cmd]

    log("Opening SSH with local port forwards to remote localhost ...")
    log("Note: close this session to stop the kernel and tear down tunnels.")

    try:
        _run(ssh_cmd, "SSH run (ipykernel)", check=True)
    except Exception:
        log("SSH session terminated with error.")
    finally:
        log("Kernel session ended (or SSH closed).")
        log("=== remote_kernel END ===")
        time.sleep(1)

def add_kernel(endpoint: str, name: Optional[str], python_bin: Optional[str] = None) -> None:
    """
    Install a Jupyter kernel spec that calls this script with:
      remote_kernel --endpoint <endpoint> -f {connection_file} [--python <python_bin>]
    """
    if not name:
        name = endpoint
        
    # Warn if endpoint is not present in ~/.ssh/config
    ssh_hosts = _list_ssh_config_hosts()
    if not ssh_hosts:
        log("⚠ No hosts found in ~/.ssh/config.")
    elif endpoint not in ssh_hosts:
        log(f"⚠ Endpoint '{endpoint}' not found in ~/.ssh/config.")
        log("Available hosts from ~/.ssh/config:")
        for h in ssh_hosts:
            print(f"  - {h}")

    if not _probe_remote(endpoint, python_bin or "python"):
        return None
        
    abs_path = os.path.abspath(sys.argv[0])
    slug = name.lower().replace(" ", "_")
    kernel_dir = os.path.join(KERNELS_DIR, slug)
    os.makedirs(kernel_dir, exist_ok=True)

    # Store --endpoint in kernel.json argv so Jupyter invokes correctly
    argv = [abs_path, "--endpoint", endpoint, "-f", "{connection_file}"]
    if python_bin:
        argv += ["--python", python_bin]

    kernel_json = {
        "argv": argv,
        "display_name": name,
        "language": "python"
    }

    with open(os.path.join(kernel_dir, "kernel.json"), "w") as f:
        json.dump(kernel_json, f, indent=2)

    log(f"Added kernel          : {name}")
    log(f"Slug/dir              : {slug} -> {kernel_dir}")
    log(f"Endpoint              : {endpoint}")
    log(f"Python (remote)       : {python_bin or 'python'}")


def list_kernels() -> None:
    """List kernels with endpoint, formatted as a clean table."""
    if not os.path.exists(KERNELS_DIR):
        log("No kernels installed")
        return

    print(f"{'slug':<20}| {'name':<26}| {'python':<18}| endpoint")
    print("-" * 90)
    for slug in sorted(os.listdir(KERNELS_DIR)):
        kjson = os.path.join(KERNELS_DIR, slug, "kernel.json")
        if not os.path.isfile(kjson):
            continue
        try:
            with open(kjson) as f:
                data = json.load(f)
            name = data.get("display_name", slug)
            argv = data.get("argv", [])
            endpoint = argv[argv.index("--endpoint") + 1] if "--endpoint" in argv else None
            python_bin = argv[argv.index("--python") + 1] if "--python" in argv else "python"
            if not endpoint:
                continue
            print(f"{slug:<20}| {name:<26}| {python_bin:<18}| {endpoint}")
        except Exception as e:
            log(f"Failed to read kernel spec {kjson}: {e}")
    print("---")


def delete_kernel(name_or_slug: str) -> None:
    slug = name_or_slug.lower().replace(" ", "_")
    kernel_dir = os.path.join(KERNELS_DIR, slug)
    if not os.path.exists(kernel_dir):
        log(f"Kernel '{name_or_slug}' not found")
        return
    try:
        shutil.rmtree(kernel_dir)
        log(f"Deleted kernel '{name_or_slug}'")
    except Exception as e:
        log(f"Failed to delete kernel '{name_or_slug}': {e}")


# ---------------------------
# Entry
# ---------------------------

def main():
    if len(sys.argv) < 2 or "-h" in sys.argv or "--help" in sys.argv:
        usage()
        return
    if "-v" in sys.argv or "--version" in sys.argv:
        version()
        return

    first_cmd = sys.argv[1].lower()


    if first_cmd == "add":
        # Format: remote_kernel add <HostAlias> [--name <Display Name>] [--python <path>]
        if len(sys.argv) < 3:
            usage()
            hosts = _list_ssh_config_hosts()
            if hosts:
                print("\nAvailable SSH hosts (from SSH_CONFIG or ~/.ssh/config):")
                for h in hosts:
                    print(f"  - {h}")
            else:
                print("\nNo SSH hosts found (set SSH_CONFIG or create ~/.ssh/config).")
            return

        endpoint = sys.argv[2]  # positional after 'add'
        name = _arg("--name")   # may be None -> default to endpoint
        python_bin = _arg("--python")
        add_kernel(endpoint, name, python_bin)
        return
    
    if first_cmd == "list":
        list_kernels()
        return

    if first_cmd == "delete":
        if len(sys.argv) < 3:
            usage()
            return
        delete_kernel(sys.argv[2])
        return

    # Direct kernel launch path (called by Jupyter via kernel.json)
    if "--endpoint" not in sys.argv or "-f" not in sys.argv:
        usage()
        return

    endpoint = _arg("--endpoint")
    conn_file = _arg("-f")
    python_bin = _arg("--python", PYTHON_BIN)

    start_kernel(endpoint, conn_file, python_bin)


if __name__ == "__main__":
    main()
