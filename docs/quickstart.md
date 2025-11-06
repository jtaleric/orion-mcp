# Quick Start Guide

> **Navigation**: [Documentation Home](README.md) → Quick Start

Get Orion MCP up and running in minutes with this step-by-step guide.

## 🚀 Prerequisites

- **Python 3.11+** installed
- **OpenSearch/Elasticsearch** endpoint with performance data
- **Container runtime** (Docker/Podman) - optional

## 📦 Installation

### Option 1: Local Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/orion-mcp.git
cd orion-mcp

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Option 2: Container

```bash
# Build container
podman build -t orion-mcp .

# Run container
podman run --env-host --network=host orion-mcp
```

## ⚙️ Configuration

Set your OpenSearch endpoint:

```bash
export ES_SERVER="https://your-opensearch-endpoint:9200"
```

## 🎯 First Run

Start the MCP server:

```bash
python orion_mcp.py
```

The server will start on `http://localhost:3030`

## 🧪 Test Your Setup

Once the server is running on `http://localhost:3030`, you can verify it's working by checking that the MCP server responds to requests. The server exposes various tools for performance analysis that can be accessed via the MCP protocol.

## 🎉 Success!

If the server starts without errors and listens on port 3030, you're ready to go!

## 🔄 Next Steps

### Available Features
- **Analyze Pull Requests** - Compare PR performance against baseline metrics
- **Generate Performance Charts** - Create trend visualizations across OpenShift versions  
- **Analyze Metric Correlations** - Explore relationships between different performance metrics
- **Detect Regressions** - Automatically identify performance changepoints

## 📚 Learn More

- **[Features Overview](features/README.md)** - Explore all available features
- **[PR Analysis Guide](features/pr-analysis-quickstart.md)** - Deep dive into PR analysis
- **[API Reference](api/tools.md)** - Complete API documentation
- **[Examples](examples/README.md)** - Real-world usage examples

## 🚨 Troubleshooting

### Server Won't Start
- Check Python version: `python --version`
- Verify dependencies: `pip list | grep mcp`
- Check port availability: `netstat -an | grep 3030`

### No Data Returned
- Verify ES_SERVER environment variable
- Test OpenSearch connectivity and verify the data source is accessible
- Check server logs for errors

### Permission Issues
- Ensure OpenSearch credentials are configured
- Check firewall settings
- Verify container networking (if using containers)

---
