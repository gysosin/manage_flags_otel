#!/usr/bin/env python3
"""
Manage FlagD Feature Flags Tool

This tool allows remote management of OpenTelemetry Demo feature flags
by updating Kubernetes ConfigMaps and triggering pod restarts.

Usage:
    python manage_flags.py --flag <flag_name> --value <variant_value>
    python manage_flags.py --flag productCatalogFailure --value on
    python manage_flags.py --flag cartServiceFailure --value off

For custom kubeconfig:
    python manage_flags.py --kubeconfig ./kubeconfig.yaml --flag <flag_name> --value <variant_value>
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError:
    print("Error: kubernetes package not installed.")
    print("Run: pip install -r requirements.txt")
    sys.exit(1)


def get_flagd_pod(v1, namespace, label_selector="app.kubernetes.io/name=flagd"):
    """Find a running flagd pod in the given namespace."""
    try:
        pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
        if not pods.items:
            # Fallback to component label
            pods = v1.list_namespaced_pod(namespace, label_selector="app.kubernetes.io/component=flagd")
            
        for pod in pods.items:
            if pod.status.phase == "Running":
                return pod.metadata.name
        return None
    except ApiException as e:
        print(f"Error viewing pods: {e}")
        return None


def list_flags(v1, namespace, config_map_name):
    """List all available feature flags."""
    try:
        config_map = v1.read_namespaced_config_map(config_map_name, namespace)
        
        target_key = "demo.flagd.json"
        if target_key not in config_map.data:
            for key in config_map.data:
                if key.endswith(".json"):
                    target_key = key
                    break
        
        if target_key not in config_map.data:
            print(f"Error: Could not find flag configuration in ConfigMap {config_map_name}")
            return
        
        flag_data = json.loads(config_map.data[target_key])
        flags = flag_data.get("flags", {})
        
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║                    Available Feature Flags                    ║")
        print("╠══════════════════════════════════════════════════════════════╣")
        
        for flag_name, flag_config in flags.items():
            default = flag_config.get("defaultVariant", "N/A")
            variants = list(flag_config.get("variants", {}).keys())
            print(f"║  {flag_name:<30} | default: {default:<8} | variants: {variants}")
        
        print("╚══════════════════════════════════════════════════════════════╝\n")
        
    except ApiException as e:
        print(f"Error reading ConfigMap: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def update_config_map(v1, namespace, config_map_name, flag_name, variant_value):
    """Update the flag's defaultVariant in the ConfigMap."""
    try:
        config_map = v1.read_namespaced_config_map(config_map_name, namespace)
        
        target_key = "demo.flagd.json"
        if target_key not in config_map.data:
            for key in config_map.data:
                if key.endswith(".json"):
                    target_key = key
                    break
        
        if target_key not in config_map.data:
            print(f"Error: Could not find flag configuration in ConfigMap {config_map_name}")
            return None

        flag_data = json.loads(config_map.data[target_key])
        
        if flag_name not in flag_data.get("flags", {}):
            print(f"Error: Flag '{flag_name}' not found in configuration.")
            print(f"Available flags: {', '.join(flag_data.get('flags', {}).keys())}")
            return None

        print(f"Updating '{flag_name}' defaultVariant to '{variant_value}'...")
        flag_data['flags'][flag_name]['defaultVariant'] = variant_value
        
        config_map.data[target_key] = json.dumps(flag_data, indent=2)
        
        v1.patch_namespaced_config_map(config_map_name, namespace, config_map)
        print("✓ ConfigMap updated successfully.")
        return json.dumps(flag_data, indent=2)

    except ApiException as e:
        print(f"Error updating ConfigMap: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def hot_reload_pod(v1, namespace, pod_name, kubeconfig_path=None):
    """Restart the flagd deployment to pick up ConfigMap changes."""
    try:
        print("Triggering pod restart to reload configuration...")
        
        restart_cmd = [
            'kubectl', 'rollout', 'restart',
            'deployment/flagd',
            '-n', namespace
        ]
        
        # Add kubeconfig if specified
        if kubeconfig_path:
            restart_cmd.extend(['--kubeconfig', kubeconfig_path])
        
        resp = subprocess.run(restart_cmd, capture_output=True, text=True)
        
        if resp.returncode == 0:
            print("Deployment restart triggered successfully.")
            print("Waiting for rollout to complete...")
            
            wait_cmd = [
                'kubectl', 'rollout', 'status',
                'deployment/flagd',
                '-n', namespace,
                '--timeout=60s'
            ]
            
            if kubeconfig_path:
                wait_cmd.extend(['--kubeconfig', kubeconfig_path])
            
            wait_resp = subprocess.run(wait_cmd, capture_output=True, text=True)
            
            if wait_resp.returncode == 0:
                print("✓ Pod restarted successfully! Flags updated.")
            else:
                print(f"Warning: Rollout status check failed: {wait_resp.stderr}")
        else:
            print(f"Error triggering restart: {resp.stderr}")

    except Exception as e:
        print(f"Error executing reload: {e}")


def load_kubeconfig(kubeconfig_path=None):
    """Load kubeconfig from specified path or default locations."""
    if kubeconfig_path:
        if not os.path.exists(kubeconfig_path):
            print(f"Error: Kubeconfig file not found: {kubeconfig_path}")
            sys.exit(1)
        print(f"Using kubeconfig: {kubeconfig_path}")
        config.load_kube_config(config_file=kubeconfig_path)
        return kubeconfig_path
    
    # Check for local kubeconfig in tool directory
    tool_dir = Path(__file__).parent
    local_kubeconfig = tool_dir / "kubeconfig.yaml"
    
    if local_kubeconfig.exists():
        print(f"Using local kubeconfig: {local_kubeconfig}")
        config.load_kube_config(config_file=str(local_kubeconfig))
        return str(local_kubeconfig)
    
    # Try default locations
    try:
        config.load_kube_config()
        print("Using default kubeconfig (~/.kube/config)")
        return None
    except Exception:
        try:
            config.load_incluster_config()
            print("Using in-cluster config")
            return None
        except Exception:
            print("Error: Could not load kubeconfig.")
            print("Please provide --kubeconfig or place kubeconfig.yaml in this directory.")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Manage FlagD feature flags for OpenTelemetry Demo.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  List all flags:
    python manage_flags.py --list

  Enable a failure flag:
    python manage_flags.py --flag productCatalogFailure --value on

  Disable a failure flag:
    python manage_flags.py --flag cartServiceFailure --value off

  Use custom kubeconfig:
    python manage_flags.py --kubeconfig ./kubeconfig.yaml --flag myFlag --value on
        """
    )
    parser.add_argument('--kubeconfig', '-k', help='Path to kubeconfig file')
    parser.add_argument('--namespace', '-n', default='otel-demo', help='Kubernetes namespace (default: otel-demo)')
    parser.add_argument('--config-map', '-c', default='flagd-config', help='ConfigMap name (default: flagd-config)')
    parser.add_argument('--flag', '-f', help='Flag name to update')
    parser.add_argument('--value', '-v', help='New variant value (e.g., "on", "off")')
    parser.add_argument('--list', '-l', action='store_true', help='List all available flags')
    
    args = parser.parse_args()
    
    # Load kubeconfig
    kubeconfig_path = load_kubeconfig(args.kubeconfig)
    
    v1 = client.CoreV1Api()
    
    # List flags mode
    if args.list:
        list_flags(v1, args.namespace, args.config_map)
        return
    
    # Update flag mode
    if not args.flag or not args.value:
        parser.error("--flag and --value are required (or use --list to see available flags)")
    
    print(f"\n{'='*60}")
    print(f"  FlagD Feature Flag Manager")
    print(f"{'='*60}")
    print(f"  Namespace:  {args.namespace}")
    print(f"  ConfigMap:  {args.config_map}")
    print(f"  Flag:       {args.flag}")
    print(f"  New Value:  {args.value}")
    print(f"{'='*60}\n")
    
    # Update ConfigMap
    new_json_content = update_config_map(v1, args.namespace, args.config_map, args.flag, args.value)
    
    if new_json_content:
        pod_name = get_flagd_pod(v1, args.namespace)
        if pod_name:
            hot_reload_pod(v1, args.namespace, pod_name, kubeconfig_path)
        else:
            print("Warning: Could not find running flagd pod. Change is persisted but hot-reload failed.")
    
    print("")


if __name__ == '__main__':
    main()
