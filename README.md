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
| `has_openshift_regressed` | Scans all configs for changepoints | `version="4.19"`, `lookback="15"` |
| `metrics_correlation` | Correlates two metrics & returns a scatter plot | `metric1="podReadyLatency_P99"`, `metric2="ovnCPU_avg"`, `config="trt-external-payload-cluster-density.yaml"`, `version="4.19"`, `lookback="15"` |

---

## Deployment

### Container Image

```bash
podman build -t quay.io/YOUR_ORG/orion-mcp:latest .
# or
docker build -t your-org/orion-mcp:latest .
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

