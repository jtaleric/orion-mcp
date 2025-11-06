# Orion MCP

[![License](https://img.shields.io/github/license/jtaleric/orion-mcp)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)  
Orion MCP is a Model Context Protocol (MCP) server for performance regression analysis powered by the [cloud-bulldozer/orion](https://github.com/cloud-bulldozer/orion) library.

---

## Key Features

* **Regression Detection** – Automatically detects performance regressions in OpenShift & Kubernetes clusters.
* **Interactive MCP API** – Exposes a set of composable tools & resources that can be consumed via HTTP or by other MCP agents.
* **Visual Reporting** – Generates publication-ready plots (PNG/JPEG) for trends, multi-version comparisons and metric correlations.
* **Container-first** – Ships with a lightweight OCI image and an example OpenShift deployment manifest.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Quick Start](#quick-start)
3. [Available Tools](#available-tools)
4. [Deployment](#deployment)
5. [Development](#development)
6. [Contributing](#contributing)
7. [License](#license)

---

## Getting Started

### Prerequisites

* **Python** 3.11 or newer
* An **OpenSearch** (or Elasticsearch ≥7.17) endpoint with Orion-indexed benchmark results
* **Podman** or **Docker** (optional – for containerised execution)

### Installation (virtual-env)

```bash
# Clone repository
$ git clone https://github.com/YOUR_ORG/orion-mcp.git && cd orion-mcp

# Create & activate a virtual environment
$ python3.11 -m venv .venv
$ source .venv/bin/activate

# Install Python dependencies
$ pip install -r requirements.txt
```

---

## Quick Start

Set the data-source endpoint and launch the server locally:

```bash
export ES_SERVER="https://opensearch.example.com:9200"
python orion_mcp.py  # listens on 0.0.0.0:3030 by default
```

---

## Available Tools

| Tool | Description | Default Arguments |
|------|-------------|-------------------|
| `get_data_source` | Returns the configured OpenSearch URL | _none_ |
| `get_orion_configs` | Lists available Orion configuration files | _none_ |
| `get_orion_metrics` | Lists metrics grouped by Orion config | _none_ |
| `openshift_report_on` | Generates a trend line for one or more OCP versions | `versions="4.19"`, `lookback="15"`, `metric="podReadyLatency_P99"`, `config="small-scale-udn-l3.yaml"` |
| `openshift_report_on_pr` | **NEW** Analyzes performance impact of a specific Pull Request | `version="4.20"`, `lookback="15"`, `organization="openshift"`, `repository="ovn-kubernetes"`, `pull_request="2841"` |
| `has_openshift_regressed` | Scans all configs for changepoints | `version="4.19"`, `lookback="15"` |
| `metrics_correlation` | Correlates two metrics & returns a scatter plot | `metric1="podReadyLatency_P99"`, `metric2="ovnCPU_avg"`, `config="trt-external-payload-cluster-density.yaml"`, `version="4.19"`, `lookback="15"` |

---

## Pull Request Performance Analysis

### Overview

The `openshift_report_on_pr` tool provides **automated performance regression detection** for GitHub Pull Requests. This feature compares the performance metrics of a specific PR against the periodic baseline performance to identify potential regressions.

### How It Works

1. **Baseline Collection**: Gathers periodic performance data for the specified OpenShift version over the lookback period
2. **PR Analysis**: Runs performance tests specifically for the target Pull Request
3. **Comparison**: Compares PR performance against the periodic baseline using a **10% threshold**
4. **Multi-Config Testing**: Tests across multiple Orion configurations for comprehensive coverage

### Supported Configurations

The PR analysis runs against these key performance test configurations:

- `trt-external-payload-cluster-density.yaml` - Cluster density and pod scaling tests
- `trt-external-payload-node-density.yaml` - Node-level performance and resource utilization
- `trt-external-payload-node-density-cni.yaml` - CNI-specific networking performance
- `trt-external-payload-crd-scale.yaml` - Custom Resource Definition scaling tests

### Interpreting Results

- **periodic_avg**: Baseline performance metrics averaged over the lookback period
- **pull**: Performance metrics from the specific PR's test runs
- **Regression Detection**: Compare values using the 10% threshold:
  - `(pull_value - periodic_avg) / periodic_avg > 0.10` indicates a potential regression
  - Values within ±10% are considered normal variance

### Integration with AI/LLM

The response format is optimized for AI analysis. The LLM can:

1. **Automatically detect regressions** by comparing periodic_avg vs pull metrics
2. **Apply the 10% threshold** to determine significance
3. **Generate human-readable reports** highlighting concerning changes
4. **Provide actionable insights** about which metrics regressed and by how much

### Documentation

For comprehensive documentation:

- **[📚 Complete Documentation](docs/README.md)** - Full documentation index
- **[🚀 Quick Start Guide](docs/quickstart.md)** - Get started in minutes
- **[🎯 Features Guide](docs/features/README.md)** - Complete features documentation including PR analysis
- **[🔧 API Reference](docs/api/README.md)** - Complete API documentation

### Example AI Analysis Prompt

```
Analyze this PR performance data and identify any regressions using a 10% threshold:
[paste the JSON response]

For each metric that shows >10% degradation, explain:
1. The metric name and what it measures
2. The baseline vs PR values  
3. The percentage change
4. Potential impact on users
```

---

## Deployment

### Container Image

```bash
podman build -t quay.io/YOUR_ORG/orion-mcp:latest .
```

### OpenShift

A production-ready `openshift-deployment.yml` is provided:

```bash
# Update ES_SERVER env if required then apply
oc apply -f openshift-deployment.yml

# Verify
oc get pods -l app.kubernetes.io/name=orion-mcp
```

Expose the service using an **OpenShift Route** and point your MCP client to `http://<host>:3030`.

---

## Development

```bash
# Run linters & tests
flake8
pytest

# Auto-format with black & isort
black . && isort .
```

---

## Contributing

Pull requests are very welcome! Please ensure you have read and adhere to the [Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

1. Fork the repository
2. Create a new branch for your feature or bugfix
3. Make your changes and add tests if applicable
4. Submit a pull request with a clear description of your changes


---

## License

Orion-MCP is distributed under the **Apache 2.0** License. See the [LICENSE](LICENSE) file for full text.

