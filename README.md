# FlagD Feature Flag Manager

A standalone tool to remotely manage OpenTelemetry Demo feature flags via Kubernetes.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Setup kubeconfig (choose one):
#    - Copy your kubeconfig: cp ~/.kube/config ./kubeconfig.yaml
#    - Or use --kubeconfig flag to point to existing config

# 3. Run the tool
python manage_flags.py --list                           # List all flags
python manage_flags.py --flag productCatalogFailure --value on   # Enable failure
python manage_flags.py --flag productCatalogFailure --value off  # Disable failure
```

## Prerequisites

- Python 3.8+
- `kubectl` installed and in PATH
- Access to the Kubernetes cluster running OpenTelemetry Demo

## Kubeconfig Setup

The tool looks for kubeconfig in this order:
1. `--kubeconfig` CLI argument
2. `./kubeconfig.yaml` in this directory
3. Default `~/.kube/config`
4. In-cluster config (if running inside Kubernetes)

### Getting Your Kubeconfig

```bash
# AWS EKS
aws eks update-kubeconfig --name <cluster-name> --region <region>
cat ~/.kube/config > kubeconfig.yaml

# GCP GKE
gcloud container clusters get-credentials <cluster-name> --zone <zone>
cat ~/.kube/config > kubeconfig.yaml

# Azure AKS
az aks get-credentials --resource-group <rg> --name <cluster-name>
cat ~/.kube/config > kubeconfig.yaml

# Local Kind/Minikube
kind export kubeconfig --name <cluster-name> > kubeconfig.yaml
# or
cat ~/.kube/config > kubeconfig.yaml
```

## Usage

```bash
# List all available flags
python manage_flags.py --list

# Update a flag
python manage_flags.py --flag <flag_name> --value <on|off>

# Use specific kubeconfig
python manage_flags.py --kubeconfig /path/to/kubeconfig --flag myFlag --value on

# Target different namespace
python manage_flags.py --namespace my-namespace --flag myFlag --value on
```

### Available Flags

| Flag Name | Description |
|-----------|-------------|
| `productCatalogFailure` | Simulates product catalog service failure |
| `cartServiceFailure` | Simulates cart service failure |
| `adServiceFailure` | Simulates ad service failure |
| `recommendationServiceCacheFailure` | Simulates recommendation cache miss |
| `paymentServiceFailure` | Simulates payment processing failure |
| `paymentServiceUnreachable` | Simulates payment service timeout |
| `loadgeneratorFloodHomepage` | Increases load on homepage |
| `kafkaQueueProblems` | Simulates Kafka queue issues |

## CLI Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--kubeconfig` | `-k` | auto-detect | Path to kubeconfig file |
| `--namespace` | `-n` | `otel-demo` | Kubernetes namespace |
| `--config-map` | `-c` | `flagd-config` | ConfigMap name |
| `--flag` | `-f` | - | Flag name to update |
| `--value` | `-v` | - | New variant value |
| `--list` | `-l` | - | List all available flags |

## How It Works

1. **Updates ConfigMap**: Modifies the `flagd-config` ConfigMap with the new flag value
2. **Restarts Pod**: Triggers a rolling restart of the flagd deployment
3. **Waits for Rollout**: Confirms the pod is running with updated configuration

## Troubleshooting

### "Could not load kubeconfig"
- Ensure `kubeconfig.yaml` exists in this directory or provide `--kubeconfig` path
- Verify kubectl works: `kubectl get pods -n otel-demo`

### "Flag not found"
- Run `--list` to see available flags
- Check namespace is correct (default: `otel-demo`)

### "Permission denied"
- Ensure your kubeconfig has permissions to:
  - Read/patch ConfigMaps in the target namespace
  - Restart deployments in the target namespace

## Files

```
tools/manage_flags/
├── README.md              # This file
├── manage_flags.py        # Main tool script
├── requirements.txt       # Python dependencies
├── kubeconfig.yaml        # Your kubeconfig (create this)
└── kubeconfig.yaml.example # Example kubeconfig template
```
