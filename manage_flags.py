#!/usr/bin/env python3
"""
Manage FlagD Feature Flags Tool

This tool allows remote management of OpenTelemetry Demo feature flags
by updating Kubernetes ConfigMaps and triggering pod restarts.

No external dependencies like kubectl required - uses pure Python kubernetes library.

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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError:
    print("Error: kubernetes package not installed.")
    print("Run: pip install -r requirements.txt")
    sys.exit(1)



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


def hot_reload_pod(namespace, deployment_name="flagd"):
    """
    Restart the flagd deployment to pick up ConfigMap changes.
    Uses pure Python kubernetes library - no kubectl required.
    """
    try:
        print("Triggering pod restart to reload configuration...")
        
        apps_v1 = client.AppsV1Api()
        
        # Patch the deployment with a restart annotation (same as kubectl rollout restart)
        restart_annotation = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
            }
        }
        
        apps_v1.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=restart_annotation
        )
        print("Deployment restart triggered successfully.")
        
        # Wait for rollout to complete
        print("Waiting for rollout to complete...")
        max_wait = 60
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
            status = deployment.status
            
            # Check if rollout is complete
            if (status.updated_replicas == status.replicas and
                status.ready_replicas == status.replicas and
                status.available_replicas == status.replicas):
                print("✓ Pod restarted successfully! Flags updated.")
                return
            
            time.sleep(2)
        
        print("Warning: Rollout did not complete within 60 seconds, but changes are persisted.")
        
    except ApiException as e:
        print(f"Error restarting deployment: {e.reason}")
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
        hot_reload_pod(args.namespace)
    
    print("")


if __name__ == '__main__':
    main()
