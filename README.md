# Sentinel-Drift 🛡️

**Sentinel-Drift** is a lightweight agentless, open-source tool to detect and fix configuration drift across your server fleet. It compares the actual state of configuration files on your servers against a "Source of Truth" (SoT) stored in this repository.

## 🚀 Features

*   **Source of Truth**: Define your desired configuration states in the `source_of_truth/` folder.
*   **Drift Detection**: Calculates SHA-256 hashes to verify integrity.
*   **Smart Diff**: Displays a clean, readable `diff` output showing exactly what changed.
*   **Multi-File Support**: Audit multiple configuration files per server.
*   **Auto-Fix / Ask-Fix**: Automatically repair drift or ask for confirmation before overwriting.
*   **Audit Logging**: Keeps a history of all audit runs in `audit_history.log`.

## 📂 Project Structure

We kept it simple. No complex roles, just what you need.

```
.
├── sentinel_drift.yml      # The main playbook to run
├── inventory.yml           # Define your servers and groups here
├── config_maps/            # Map groups to config files here
│   ├── standard_servers.yml
│   └── custom_servers.yml
├── source_of_truth/        # PUT YOUR REFERENCE CONFIG FILES HERE
│   └── sample_app/
│       ├── standard_config.conf
│       └── custom_config.conf
├── tasks/
│   └── audit_file.yml      # The logic (Hash, Compare, Diff, Log)
└── audit_history.log       # Execution logs
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

## 🛠️ Usage Guide

### 1. Define your Inventory (`inventory.yml`)
List your servers and organize them into groups (e.g., `web_servers`, `db_servers`).

```yaml
all:
  hosts:
    web_01:
      ansible_host: 192.168.1.10
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

```yaml
# config_maps/standard_servers.yml
audit_files:
  - src: "sample_app/standard_config.conf" # Path inside source_of_truth/
    dest: "/etc/app/config.conf"           # Path on the remote server
  
  - src: "ssh/sshd_config"
    dest: "/etc/ssh/sshd_config"
```

### 4. Run the Audit
Run the main playbook:
```bash
ansible-playbook sentinel_drift.yml
```

### 5. Fix the Drift
You have two options to repair configuration drift:

**Option A: Interactive Fix (Recommended)**
Ask for confirmation before overwriting any file.
```bash
ansible-playbook sentinel_drift.yml -e "ask_fix=true"
```

**Option B: Auto-Fix (Use with Caution)**
Automatically overwrite all drifted files with the Source of Truth.
*Note: You will be prompted once at the start to confirm this dangerous action.*
```bash
ansible-playbook sentinel_drift.yml -e "auto_fix=true"
```

## 📊 Logs
Check `audit_history.log` for a summary of the execution:
```
[2023-10-27 10:00:00] [OK]    Host: web_01 | File: /etc/app/config.conf
[2023-10-27 10:00:01] [DRIFT] Host: db_01  | File: /etc/app/config.conf | Ref: custom_config.conf
[2023-10-27 10:05:00] [FIXED] Host: db_01  | File: /etc/app/config.conf | Ref: custom_config.conf
```

## 📄 License
MIT
