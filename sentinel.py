#!/usr/bin/env python3
import argparse
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Sentinel-Drift 🛡️ - Configuration Drift Detection & Remediation Tool",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('--check', action='store_true', help="Run in audit mode only (default behavior).")
    parser.add_argument('--ask-fix', action='store_true', help="Interactively ask to fix each detected drift.")
    parser.add_argument('--auto-fix', action='store_true', help="⚠️  Automatically fix all detected drifts (DANGEROUS).")
    parser.add_argument('--report', action='store_true', help="Generate an HTML dashboard report after execution.")
    parser.add_argument('--inventory', '-i', default='inventory.yml', help="Path to the inventory file (default: inventory.yml).")
    parser.add_argument('--vault-pass', action='store_true', help="Ask for Ansible Vault password.")

    args = parser.parse_args()

    # --- Safety Checks ---
    if args.auto_fix:
        print("\n🚨  DANGER ZONE: AUTO-FIX ENABLED  🚨")
        print("You are about to overwrite configuration files on remote servers without confirmation.")
        response = input("Type 'yes' to confirm and proceed: ")
        if response.strip() != 'yes':
            print("❌ Aborted by user.")
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

    if args.vault_pass:
        cmd.append("--ask-vault-pass")

    # --- Execution ---
    print("🚀 Launching Sentinel-Drift...")
    try:
        # Run Ansible and stream output to console
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Ansible execution failed with return code {e.returncode}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\n🛑 Execution interrupted by user.")
        sys.exit(130)

if __name__ == "__main__":
    main()
