#!/usr/bin/env python3
"""
Sentinel-Drift Wrapper Script
=============================

This script serves as the primary entry point for the Sentinel-Drift tool.
It wraps the Ansible playbook execution, providing a user-friendly CLI,
interactive drift remediation, and enhanced reporting capabilities.

It handles:
- Argument parsing and validation.
- Secure Ansible Vault password injection (in-memory).
- Interactive prompts for drift remediation.
- Output formatting (JSON parsing for audit, YAML for interactive).
- Post-execution summary generation from audit logs.

Author: Okuromatsu
License: Open Source - MIT
"""

import argparse
import atexit
import getpass
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional, Any

# Constants
AUDIT_LOG_FILE = "audit_history.log"
PLAYBOOK_FILE = "sentinel_drift.yml"
DRIFT_TASKS = [
    "Display Diff",
    "Display Metadata Drift",
    "Display Missing File Warning",
    "Display Vault Error"
]
FIX_TASKS = [
    "Display Fix Applied"
]


class Colors:
    """ANSI color codes for terminal output styling."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Spinner:
    """
    A simple terminal spinner to indicate background activity.
    Runs in a separate thread to not block the main execution flow.
    """
    def __init__(self, message: str = "Processing..."):
        self.message = message
        self.stop_running = False
        self.thread: Optional[threading.Thread] = None

    def spin(self):
        """Cycle through spinner characters until stopped."""
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while not self.stop_running:
            sys.stdout.write(f"\r{Colors.CYAN}{chars[i % len(chars)]}{Colors.ENDC} {self.message}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def start(self):
        """Start the spinner thread."""
        self.stop_running = False
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()

    def stop(self):
        """Stop the spinner thread and clear the line."""
        self.stop_running = True
        if self.thread:
            self.thread.join()
        # Clear the line after stopping
        sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r")
        sys.stdout.flush()


def setup_vault_password(vault_pass_arg: Optional[str], cmd_list: List[str]) -> Optional[str]:
    """
    Securely handles the Ansible Vault password.

    If a password is provided (or prompted), it creates a temporary helper script
    that echoes the password from an environment variable. This avoids writing
    the password to disk in plain text.

    Args:
        vault_pass_arg: The argument provided via CLI (None, value, or '__PROMPT__').
        cmd_list: The list of command arguments to append the vault password file option to.

    Returns:
        The password string to be set in the environment variable, or None.
    """
    if not vault_pass_arg:
        return None

    vault_password_value = vault_pass_arg
    if vault_pass_arg == '__PROMPT__':
        vault_password_value = getpass.getpass(f"{Colors.BLUE}Vault password: {Colors.ENDC}")

    # Create a temporary helper script (0o700 permissions)
    # This script simply echoes the environment variable SENTINEL_VAULT_PASS
    fd, vault_pass_file = tempfile.mkstemp(suffix='.sh')
    with os.fdopen(fd, 'w') as f:
        f.write("#!/bin/sh\n")
        f.write("echo \"$SENTINEL_VAULT_PASS\"\n")

    # Make it executable and readable only by the owner
    os.chmod(vault_pass_file, 0o700)

    cmd_list.extend(["--vault-password-file", vault_pass_file])

    # Register cleanup to remove the temp file on exit
    def cleanup_vault_file():
        if vault_pass_file and os.path.exists(vault_pass_file):
            os.remove(vault_pass_file)
    
    atexit.register(cleanup_vault_file)

    return vault_password_value


def perform_safety_checks(args: argparse.Namespace):
    """
    Performs critical safety checks before execution.
    Warns the user about dangerous operations (Auto-Fix, Secret Leaks).
    """
    # Check 1: Auto-Fix Danger
    if args.auto_fix:
        print(f"\n{Colors.FAIL}🚨  DANGER ZONE: AUTO-FIX ENABLED  🚨{Colors.ENDC}")
        if args.auto_fix != 'yes':
            print("You are about to overwrite configuration files on remote servers without confirmation.")
            response = input(f"{Colors.WARNING}Type 'yes' to confirm and proceed: {Colors.ENDC}")
            if response.strip() != 'yes':
                print(f"{Colors.FAIL}❌ Aborted by user.{Colors.ENDC}")
                sys.exit(1)

    # Check 2: Report Secret Leak
    if args.report and args.vault_pass:
        print(f"\n{Colors.WARNING}⚠️  SECURITY WARNING: POTENTIAL SECRET LEAK  ⚠️{Colors.ENDC}")
        print("You are generating a report containing diffs of encrypted files.")
        print("Secrets will appear IN PLAIN TEXT in 'report.html'.")
        if args.report != 'yes':
            response = input(f"{Colors.WARNING}Type 'yes' to confirm you understand the risk: {Colors.ENDC}")
            if response.strip() != 'yes':
                print(f"{Colors.FAIL}❌ Aborted by user.{Colors.ENDC}")
                sys.exit(1)


def parse_ansible_json(json_output: str):
    """
    Parses the JSON output from Ansible (used in Quiet/Audit mode)
    and prints a human-readable summary to the console.
    """
    try:
        data = json.loads(json_output)
    except json.JSONDecodeError:
        print(f"{Colors.FAIL}❌ Failed to parse Ansible JSON output.{Colors.ENDC}")
        return

    stats = data.get('stats', {})
    plays = data.get('plays', [])

    print(f"\n{Colors.HEADER}=== 🛡️  Sentinel-Drift Report ==={Colors.ENDC}\n")

    # Initialize drift tracking
    host_drifts: Dict[str, List[str]] = {host: [] for host in stats.keys()}
    host_fixes: Dict[str, List[str]] = {host: [] for host in stats.keys()}

    # Iterate through plays and tasks to find specific drift messages
    for play in plays:
        for task in play.get('tasks', []):
            task_name = task.get('task', {}).get('name', '')

            if task_name in DRIFT_TASKS:
                for host, result in task.get('hosts', {}).items():
                    if not result.get('skipped', False):
                        msg = result.get('msg', '')
                        host_drifts[host].append(msg)
            
            elif task_name in FIX_TASKS:
                for host, result in task.get('hosts', {}).items():
                    if not result.get('skipped', False):
                        msg = result.get('msg', '')
                        host_fixes[host].append(msg)

    # Display Final Summary
    for host, stat in stats.items():
        if stat.get('unreachable', 0) > 0:
            print(f"{Colors.FAIL}❌ {host}: UNREACHABLE{Colors.ENDC}")
            continue

        if stat.get('failures', 0) > 0:
            print(f"{Colors.FAIL}❌ {host}: FAILED{Colors.ENDC}")
            continue

        drifts = host_drifts.get(host, [])
        fixes = host_fixes.get(host, [])

        if not drifts and not fixes:
            print(f"{Colors.GREEN}✅ {host}: OK (Compliant){Colors.ENDC}")
            continue

        # If we have fixes, show them
        if fixes:
            print(f"{Colors.GREEN}🔧 {host}: FIXED{Colors.ENDC}")
            for msg in fixes:
                print(f"{Colors.GREEN}    {msg}{Colors.ENDC}")
        
        # Filter out drifts that were fixed
        fixed_files = []
        for fmsg in fixes:
            # msg is "✅ FIXED: /path/to/file"
            if "FIXED: " in fmsg:
                fixed_files.append(fmsg.split("FIXED: ")[1].strip())
        
        remaining_drifts = []
        for dmsg in drifts:
            # Check if this drift message relates to a fixed file
            is_fixed = False
            for ffile in fixed_files:
                if ffile in dmsg:
                    is_fixed = True
                    break
            if not is_fixed:
                remaining_drifts.append(dmsg)

        if remaining_drifts:
            print(f"{Colors.FAIL}⚠️  {host}: DRIFT DETECTED{Colors.ENDC}")
            for msg in remaining_drifts:
                # Indent the message for better readability
                formatted_msg = "\n".join([f"    {line}" for line in msg.splitlines()])
                print(f"{Colors.WARNING}{formatted_msg}{Colors.ENDC}")
            print("")  # Empty line separator
        elif fixes:
            print("") # Empty line separator if only fixes shown


def parse_audit_log(start_time: datetime):
    """
    Parses the 'audit_history.log' file to generate a summary report.
    This is useful for Interactive mode where JSON output is not available.
    
    Args:
        start_time: Only log entries after this time will be considered.
    """
    if not os.path.exists(AUDIT_LOG_FILE):
        return

    print(f"\n{Colors.HEADER}=== 🛡️  Sentinel-Drift Report (Summary) ==={Colors.ENDC}\n")

    # Structure: host -> {'status': 'OK'|'DRIFT'|'FIXED', 'messages': []}
    host_report: Dict[str, Dict[str, Any]] = {}

    try:
        with open(AUDIT_LOG_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line.startswith("["):
                    continue

                # Extract and parse timestamp
                try:
                    # Log Format: [YYYY-MM-DD HH:MM:SS] [STATUS] ...
                    ts_str = line.split("]")[0].strip("[")
                    log_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")

                    if log_time < start_time:
                        continue
                except ValueError:
                    continue

                # Parse log content
                parts = line.split("] ", 2)
                if len(parts) < 2:
                    continue

                status_part = parts[1]  # e.g., [DRIFT]
                status = status_part.strip("[]")
                details = parts[2] if len(parts) > 2 else ""

                # Extract Host, File, and Type from details string
                host = "Unknown"
                file_path = "Unknown"
                drift_type = "Unknown"

                detail_parts = details.split(" | ")
                for part in detail_parts:
                    part = part.strip() # Clean up whitespace
                    if part.startswith("Host: "):
                        host = part.replace("Host: ", "")
                    elif part.startswith("File: "):
                        file_path = part.replace("File: ", "")
                    elif part.startswith("Type: "):
                        drift_type = part.replace("Type: ", "")

                # Initialize host entry if missing
                if host not in host_report:
                    host_report[host] = {'status': 'OK', 'messages': []}

                # Update status based on log entry
                if status == 'DRIFT':
                    host_report[host]['status'] = 'DRIFT'
                    msg = f"File: {file_path} (Type: {drift_type})"
                    if drift_type == 'vault_error':
                        msg += "\n    ⚠️  VAULT ERROR: Source file is encrypted but password was missing."
                    host_report[host]['messages'].append(msg)
                
                elif status == 'FIXED':
                    host_report[host]['status'] = 'FIXED'
                    host_report[host]['messages'].append(f"File: {file_path} (FIXED)")
                
                elif status == 'OK':
                    # Keep as OK unless already marked as DRIFT or FIXED
                    pass

    except Exception as e:
        print(f"{Colors.FAIL}Error parsing log for summary: {e}{Colors.ENDC}")
        return

    # Render the summary to console
    for host, data in host_report.items():
        status = data['status']
        if status == 'OK':
            print(f"{Colors.GREEN}✅ {host}: OK (Compliant){Colors.ENDC}")
        elif status == 'FIXED':
            print(f"{Colors.GREEN}✅ {host}: DRIFT FIXED{Colors.ENDC}")
            for msg in data['messages']:
                print(f"{Colors.CYAN}    {msg}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}⚠️  {host}: DRIFT DETECTED{Colors.ENDC}")
            for msg in data['messages']:
                print(f"{Colors.WARNING}    {msg}{Colors.ENDC}")
        print("")


def main():
    parser = argparse.ArgumentParser(
        description="Sentinel-Drift 🛡️ - Configuration Drift Detection & Remediation Tool",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('--check', action='store_true', help="Run in audit mode only (default behavior).")
    parser.add_argument('--ask-fix', action='store_true', help="Interactively ask to fix each detected drift.")
    parser.add_argument('--auto-fix', nargs='?', const='prompt', help="⚠️  Automatically fix all detected drifts (DANGEROUS). Pass 'yes' to skip confirmation.")
    parser.add_argument('--report', nargs='?', const='prompt', help="Generate an HTML dashboard report after execution. Pass 'yes' to skip vault warning.")
    parser.add_argument('--inventory', '-i', default='inventory.yml', help="Path to the inventory file (default: inventory.yml).")
    parser.add_argument('--vault-pass', nargs='?', const='__PROMPT__', help="Ansible Vault password (optional argument, or prompt if omitted).")
    parser.add_argument('--verbose', '-v', action='store_true', help="Show full Ansible output (useful for debugging).")

    args = parser.parse_args()

    # 1. Perform Safety Checks
    perform_safety_checks(args)

    # 2. Build Ansible Command
    cmd = [
        "ansible-playbook",
        PLAYBOOK_FILE,
        "-i", args.inventory
    ]

    # Inject variables based on CLI arguments
    extra_vars = []
    if args.auto_fix:
        extra_vars.append("auto_fix=true")
    elif args.ask_fix:
        extra_vars.append("ask_fix=true")
    
    if args.report:
        extra_vars.append("generate_report=true")

    if extra_vars:
        cmd.extend(["-e", " ".join(extra_vars)])

    # 3. Setup Vault Password (if requested)
    vault_password_value = setup_vault_password(args.vault_pass, cmd)

    # 4. Prepare Execution Environment
    env = os.environ.copy()
    if vault_password_value:
        env['SENTINEL_VAULT_PASS'] = vault_password_value

    # Capture start time for log parsing
    start_time = datetime.now()

    # 5. Determine Execution Mode
    # - Interactive: ask-fix enabled.
    # - Audit/Quiet: Default check mode OR auto-fix (without verbose).
    is_interactive = args.ask_fix

    if is_interactive or args.verbose:
        print(f"{Colors.BLUE}🚀 Launching Sentinel-Drift (Interactive Mode)...{Colors.ENDC}")

        # Configure Ansible output for interactive use
        if not args.verbose:
            # Suppress noise to focus on prompts and changes
            env['ANSIBLE_DISPLAY_SKIPPED_HOSTS'] = 'no'
            env['ANSIBLE_DISPLAY_OK_HOSTS'] = 'no'
            env['ANSIBLE_STDOUT_CALLBACK'] = 'yaml'
            env['ANSIBLE_RETRY_FILES_ENABLED'] = '0'

        try:
            # Run directly to allow user interaction (stdin/stdout)
            subprocess.run(cmd, check=True, env=env)
        except subprocess.CalledProcessError as e:
            print(f"\n{Colors.FAIL}❌ Ansible execution failed with return code {e.returncode}{Colors.ENDC}")
            # Attempt to show summary even on failure
            parse_audit_log(start_time)
            sys.exit(e.returncode)
        
        # Show summary after interactive run
        parse_audit_log(start_time)

    else:
        # Quiet Mode (Audit or Auto-Fix)
        mode_msg = "Auditing infrastructure..."
        if args.auto_fix:
            mode_msg = "Auditing and Fixing infrastructure..."
            
        print(f"{Colors.BLUE}🚀 Launching Sentinel-Drift...{Colors.ENDC}")

        # Force JSON output for parsing
        env['ANSIBLE_STDOUT_CALLBACK'] = 'json'
        env['ANSIBLE_LOAD_CALLBACK_PLUGINS'] = '1'

        spinner = Spinner(mode_msg)
        spinner.start()

        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        except KeyboardInterrupt:
            spinner.stop()
            print(f"\n{Colors.FAIL}🛑 Execution interrupted by user.{Colors.ENDC}")
            sys.exit(130)
        finally:
            spinner.stop()

        # Handle fatal errors that prevent JSON output
        if result.returncode != 0 and not result.stdout.strip().startswith("{"):
            print(f"\n{Colors.FAIL}❌ Ansible execution failed:{Colors.ENDC}")
            print(result.stderr)
            print(result.stdout)
            sys.exit(result.returncode)

        # Parse and display the audit report
        parse_ansible_json(result.stdout)

        if result.returncode != 0:
            sys.exit(result.returncode)


if __name__ == "__main__":
    main()
