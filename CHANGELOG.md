# Changelog

### [2.0.0] - 2025-07-28

### Major Changes
- **Replaced raw SSH calls with `sshtunnel` and `paramiko`**  
  Port forwarding and SSH connections are now handled via Python libraries, removing reliance on system `ssh` and `scp`.  
  This improves portability (works on Windows, macOS, and Linux) and enables smoother error handling and reconnection.

- **Jump Host (-J) Support via Paramiko**  
  Jump/bastion servers are now supported directly using `sshtunnel` instead of relying on `ssh -J`.  
  This makes chained connections more reliable and cross-platform.

### New Features
- **Dependency-managed installation**  
  `paramiko` and `sshtunnel` are now added to the package’s dependencies, so they are installed automatically via `pip`.

- **Improved Logging**  
  Logs now use the `__version__` field (from `__init__.py`) in log prefixes for easier debugging and tracking which version launched the kernel.

- **Cleaner Process Management**  
  `start_kernel` manages tunnel and kernel processes separately, making `--kill` and exit cleanup more reliable.

### Breaking Changes
- **Removed reliance on system `ssh` and `scp` binaries**  
  All network operations are now handled by Python libraries.  
  If you previously relied on system `ssh` configs, you may need to reconfigure host keys and credentials in `paramiko`.

### [1.6.0] - 2025-07-28
### Added
- **`remote_kernel connect` command**  
  - Allows direct SSH connection to a registered remote kernel by its slug name.
  - If no kernel name is provided, lists all available kernels with endpoints and optional bastion (`-J`) details.
  - Supports automatic detection of jump hosts for seamless SSH access.
- **`remote_kernel -v` command**  
  - Show the version
- **`remote_kernel -h` command**  
  - Show usage
