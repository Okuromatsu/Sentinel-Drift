# Sentinel-Drift 🛡️

**Sentinel-Drift** is a lightweight agentless, open-source tool to detect and fix configuration drift across your server fleet. It compares the actual state of configuration files on your servers against a "Source of Truth" (SoT) stored in this repository.

![image](https://raw.githubusercontent.com/Okuromatsu/Sentinel-Drift/refs/heads/assets/Assets/ASCII_Title.png)

## 🚀 Features

*   **Source of Truth**: Define your desired configuration states in the `source_of_truth/` folder.
*   **Drift Detection**: Calculates SHA-256 hashes to verify integrity (Content & Metadata).
*   **Smart Diff**: Displays a clean, readable `diff` output showing exactly what changed.
*   **Multi-File Support**: Audit multiple configuration files per server.
*   **Modular Architecture**: Logic is split into specialized task files for better maintainability.
*   **Secure Vault Integration**: Handles encrypted Source of Truth files with in-memory decryption (no secrets on disk).
*   **Auto-Fix / Ask-Fix**: Automatically repair drift or ask for confirmation before overwriting.
*   **Robust CLI**: Python wrapper (`sentinel.py`) with safety checks, summary reporting, and interactive modes.
*   **Audit Logging**: Keeps a history of all audit runs in `audit_history.log`.

## 📂 Project Structure

We use a modular architecture orchestrated by a Python wrapper.

```
.
├── sentinel.py             # 🧠 CLI Wrapper & Entry Point
├── sentinel_drift.yml      # 📜 Main Playbook
├── inventory.yml           # 🗺️ Server Inventory
├── config_maps/            # 📍 Host-to-File Mappings
│   ├── standard_servers.yml
│   └── ...
├── source_of_truth/        # 💎 Reference Config Files (SoT)
│   └── ...
├── tasks/                  # 🧩 Modular Ansible Tasks
│   ├── audit_file.yml      # Orchestrator
│   ├── detect_drift.yml    # Logic: Hash & Metadata Check
│   ├── generate_diff.yml   # Logic: Diff Generation
│   ├── display_results.yml # Logic: Console Output
│   ├── remediate_drift.yml # Logic: Auto-Fix / Ask-Fix
│   └── log_results.yml     # Logic: History Logging
└── audit_history.log       # 📝 Execution Logs
```

## 📦 Dependencies

Sentinel-Drift is built on **Ansible**. You don't need to install any agent on your remote servers, but you need a control machine (your laptop or a CI/CD runner) with the following requirements:

*   **Ansible Core**: Version 2.9 or higher.
*   **Python**: Version 3.8 or higher (on the control machine).
*   **SSH Access**: The control machine must have SSH access to the target servers (using keys is recommended).

To install Ansible on your control machine:
```bash
# MacOS (Homebrew)
brew install ansible

# Linux (Ubuntu/Debian)
sudo apt update && sudo apt install ansible

# Python (pip)
pip install ansible
```

Please refer to Ansible official documentation if you have an installation issue.

## 🛠️ Usage Guide

### 1. Define your Inventory (`inventory.yml`)
List your servers and organize them into groups (e.g., `web_servers`, `db_servers`).
You can specify the SSH user and key here.

```yaml
all:
  hosts:
    web_01:
      ansible_host: 192.168.1.10
      ansible_user: ubuntu
      ansible_ssh_private_key_file: ~/.ssh/id_rsa
  children:
    standard_servers:
      hosts:
        web_01:
```

### 2. Add your Config Files (`source_of_truth/`)
Place the "perfect" version of your configuration files in the `source_of_truth/` directory. You can organize them in subfolders.

### 3. Map Files to Groups (`config_maps/`)
Create a YAML file in `config_maps/` matching your group name (e.g., `standard_servers.yml`).
Define the `audit_files` list to tell Sentinel-Drift which files to check.

You can also specify **permissions** (`mode`), **owner**, and **group**.

```yaml
# config_maps/standard_servers.yml
audit_files:
  - src: "sample_app/standard_config.conf" # Path inside source_of_truth/
    dest: "/etc/app/config.conf"           # Path on the remote server
    mode: "0644"                           # Optional: Check permissions
    owner: "root"                          # Optional: Check owner
    group: "root"                          # Optional: Check group
  
  - src: "ssh/sshd_config"
    dest: "/etc/ssh/sshd_config"
    mode: "0600"
```

### 4. Run the Tool

Use the `sentinel.py` wrapper script for a better experience.

**Audit Mode (Default):**
Checks for drift and displays a summary.
```bash
./sentinel.py
```

**Generate HTML Report:**
Creates a `report.html` dashboard after the audit.
```bash
./sentinel.py --report
```
![image](https://raw.githubusercontent.com/Okuromatsu/Sentinel-Drift/refs/heads/assets/Assets/HTML_Report.png)

**Interactive Fix Mode:**
Asks you for confirmation before fixing each detected drift.
```bash
./sentinel.py --ask-fix
```

**Auto-Fix Mode:**
Automatically overwrites drifted files with the Source of Truth. (Use with caution!)
```bash
./sentinel.py --auto-fix
```

**Using Ansible Vault:**
If your Source of Truth contains encrypted files, provide the vault password.
You can enter it interactively (secure prompt) or pass it as an argument.

```bash
# Interactive prompt (hides input)
./sentinel.py --vault-pass

# Pass password directly (useful for scripts)
./sentinel.py --vault-pass "my_secret_password"
```

**Debug Mode:**
Show full Ansible output.
```bash
./sentinel.py -v
```

### 5. View the Dashboard 📊
After the run,if you used --report, you can open the generated `report.html` file in your browser to see the compliance dashboard.

## 🔐 Handling Secrets (Ansible Vault)

If your configuration files contain secrets (passwords, API keys), **DO NOT** store them in plain text. Use Ansible Vault.

1.  **Encrypt your file:**
    ```bash
    ansible-vault encrypt source_of_truth/database/db_config.conf
    ```
2.  **Run Sentinel-Drift with the vault password:**
    ```bash
    ./sentinel.py --vault-pass
    ```
    Sentinel-Drift will automatically decrypt the file in memory to compare it with the remote server.

## 📊 Logs
Check `audit_history.log` for a summary of the execution:
```
[2023-10-27 10:00:00] [OK]    Host: web_01 | File: /etc/app/config.conf
[2023-10-27 10:00:01] [DRIFT] Host: db_01  | File: /etc/app/config.conf | Ref: custom_config.conf
[2023-10-27 10:05:00] [FIXED] Host: db_01  | File: /etc/app/config.conf | Ref: custom_config.conf
```

## 📄 License
MIT
