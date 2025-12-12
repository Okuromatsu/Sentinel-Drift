#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import json
import threading
import time
import getpass
import tempfile
import atexit

# --- Colors ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- Spinner ---
class Spinner:
    def __init__(self, message="Processing..."):
        self.message = message
        self.stop_running = False
        self.thread = None

    def spin(self):
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while not self.stop_running:
            sys.stdout.write(f"\r{Colors.CYAN}{chars[i % len(chars)]}{Colors.ENDC} {self.message}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def start(self):
        self.stop_running = False
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()

    def stop(self):
        self.stop_running = True
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r") # Clear line
        sys.stdout.flush()

def parse_ansible_json(json_output):
    try:
        data = json.loads(json_output)
    except json.JSONDecodeError:
        print(f"{Colors.FAIL}❌ Failed to parse Ansible JSON output.{Colors.ENDC}")
        return

    stats = data.get('stats', {})
    plays = data.get('plays', [])

    print(f"\n{Colors.HEADER}=== 🛡️  Sentinel-Drift Report ==={Colors.ENDC}\n")

    # Track drift per host
    host_drifts = {host: [] for host in stats.keys()}
    
    # Iterate through tasks to find drift messages
    for play in plays:
        for task in play.get('tasks', []):
            task_name = task.get('task', {}).get('name', '')
            
            # Identify tasks that report drift
            if task_name in ["Display Diff", "Display Metadata Drift", "Display Missing File Warning"]:
                for host, result in task.get('hosts', {}).items():
                    if not result.get('skipped', False):
                        msg = result.get('msg', '')
                        host_drifts[host].append(msg)

    # Display Summary
    for host, stat in stats.items():
        if stat.get('unreachable', 0) > 0:
            print(f"{Colors.FAIL}❌ {host}: UNREACHABLE{Colors.ENDC}")
            continue
        
        if stat.get('failures', 0) > 0:
            # Check if it was a drift failure or other error
            print(f"{Colors.FAIL}❌ {host}: FAILED{Colors.ENDC}")
            continue

        drifts = host_drifts.get(host, [])
        
        if not drifts:
            print(f"{Colors.GREEN}✅ {host}: OK (Compliant){Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}⚠️  {host}: DRIFT DETECTED{Colors.ENDC}")
            for msg in drifts:
                # Indent the message
                formatted_msg = "\n".join([f"    {line}" for line in msg.splitlines()])
                print(f"{Colors.WARNING}{formatted_msg}{Colors.ENDC}")
            print("") # Empty line separator

def main():
    parser = argparse.ArgumentParser(
        description="Sentinel-Drift 🛡️ - Configuration Drift Detection & Remediation Tool",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('--check', action='store_true', help="run in audit mode only (default behavior).")
    parser.add_argument('--ask-fix', action='store_true', help="interactively ask to fix each detected drift.")
    parser.add_argument('--auto-fix', action='store_true', help="⚠️  automatically fix all detected drifts (DANGEROUS).")
    parser.add_argument('--report', action='store_true', help="generate an HTML dashboard report after execution.")
    parser.add_argument('--inventory', '-i', default='inventory.yml', help="path to the inventory file (default: inventory.yml).")
    parser.add_argument('--vault-pass', nargs='?', const='__PROMPT__', help="ansible vault password (optional argument, or prompt if omitted).")
    parser.add_argument('--verbose', '-v', action='store_true', help="show full Ansible output (useful for debugging).")

    args = parser.parse_args()

    # --- Safety Checks ---
    if args.auto_fix:
        print(f"\n{Colors.FAIL}🚨  DANGER ZONE: AUTO-FIX ENABLED  🚨{Colors.ENDC}")
        print("You are about to overwrite configuration files on remote servers without confirmation.")
        response = input(f"{Colors.WARNING}Type 'yes' to confirm and proceed: {Colors.ENDC}")
        if response.strip() != 'yes':
            print(f"{Colors.FAIL}❌ Aborted by user.{Colors.ENDC}")
            sys.exit(1)

    # --- Build Ansible Command ---
    cmd = [
        "ansible-playbook",
        "sentinel_drift.yml",
        "-i", args.inventory
    ]

    # Pass variables to Ansible
    extra_vars = []
    
    if args.auto_fix:
        extra_vars.append("auto_fix=true")
    elif args.ask_fix:
        extra_vars.append("ask_fix=true")
    
    if args.report:
        extra_vars.append("generate_report=true")

    if extra_vars:
        cmd.extend(["-e", " ".join(extra_vars)])

    # --- Vault Password Handling ---
    vault_pass_file = None
    vault_password_value = None

    if args.vault_pass:
        vault_password_value = args.vault_pass
        if args.vault_pass == '__PROMPT__':
            vault_password_value = getpass.getpass(f"{Colors.BLUE}Vault password: {Colors.ENDC}")
        
        # Create a temporary helper script (NOT containing the password)
        # This script will just echo the environment variable SENTINEL_VAULT_PASS
        fd, vault_pass_file = tempfile.mkstemp(suffix='.sh')
        with os.fdopen(fd, 'w') as f:
            f.write("#!/bin/sh\n")
            f.write("echo \"$SENTINEL_VAULT_PASS\"\n")
        
        # Make it executable
        os.chmod(vault_pass_file, 0o700)
        
        cmd.extend(["--vault-password-file", vault_pass_file])
        
        # Ensure cleanup
        def cleanup_vault_file():
            if vault_pass_file and os.path.exists(vault_pass_file):
                os.remove(vault_pass_file)
        atexit.register(cleanup_vault_file)

    # --- Execution ---
    
    # Prepare Environment
    env = os.environ.copy()
    if vault_password_value:
        env['SENTINEL_VAULT_PASS'] = vault_password_value

    # Determine mode: Interactive/Verbose vs Quiet/Pretty
    # Force verbose if ask-fix is on (need to see prompts) or if user requested verbose
    is_verbose = args.verbose or args.ask_fix

    if is_verbose:
        print(f"{Colors.BLUE}🚀 Launching Sentinel-Drift (Verbose/Interactive Mode)...{Colors.ENDC}")
        try:
            subprocess.run(cmd, check=True, env=env)
        except subprocess.CalledProcessError as e:
            print(f"\n{Colors.FAIL}❌ Ansible execution failed with return code {e.returncode}{Colors.ENDC}")
            sys.exit(e.returncode)
    else:
        # Quiet Mode with Spinner and Custom Output
        print(f"{Colors.BLUE}🚀 Launching Sentinel-Drift...{Colors.ENDC}")
        
        env['ANSIBLE_STDOUT_CALLBACK'] = 'json'
        # Disable other output callbacks that might interfere
        env['ANSIBLE_LOAD_CALLBACK_PLUGINS'] = '1'
        
        spinner = Spinner("Auditing infrastructure...")
        spinner.start()
        
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        except KeyboardInterrupt:
            spinner.stop()
            print(f"\n{Colors.FAIL}🛑 Execution interrupted by user.{Colors.ENDC}")
            sys.exit(130)
        finally:
            spinner.stop()

        if result.returncode != 0 and not result.stdout.strip().startswith("{"):
             # Fatal error that didn't produce JSON (e.g. connection error before play starts)
            print(f"\n{Colors.FAIL}❌ Ansible execution failed:{Colors.ENDC}")
            print(result.stderr)
            print(result.stdout)
            sys.exit(result.returncode)
            
        # Parse and display pretty output
        parse_ansible_json(result.stdout)
        
        if result.returncode != 0:
             sys.exit(result.returncode)

if __name__ == "__main__":
    main()
