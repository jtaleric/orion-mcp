# Installation Guide

> **Navigation**: [Documentation Home](README.md) → Installation

Complete installation instructions for Orion MCP in various environments.

## 🔧 System Requirements

### Minimum Requirements
- **Python**: 3.11 or newer
- **Memory**: 2GB RAM minimum, 4GB recommended
- **Storage**: 1GB free space
- **Network**: Access to OpenSearch/Elasticsearch endpoint

### Supported Platforms
- **Linux**: Ubuntu 20.04+, RHEL 8+, Fedora 35+
- **macOS**: 12.0+ (Monterey)
- **Windows**: 10/11 with WSL2
- **Containers**: Docker, Podman, OpenShift

## 📦 Installation Methods

### Method 1: Local Python Installation

#### Step 1: Clone Repository
```bash
git clone https://github.com/YOUR_ORG/orion-mcp.git
cd orion-mcp
```

#### Step 2: Create Virtual Environment
```bash
# Create virtual environment
python3.11 -m venv .venv

# Activate virtual environment
# Linux/macOS:
source .venv/bin/activate
# Windows (WSL):
source .venv/bin/activate
```

#### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 4: Verify Installation
```bash
python -c "import orion_mcp; print('✅ Installation successful')"
```

### Method 2: Container Installation

#### Using Podman (Recommended)
```bash
# Build image
podman build -t orion-mcp .

# Run container
podman run --name orion-mcp \
  --env ES_SERVER="https://your-opensearch:9200" \
  --publish 3030:3030 \
  orion-mcp
```

#### Using Docker
```bash
# Build image
docker build -t orion-mcp .

# Run container
docker run --name orion-mcp \
  --env ES_SERVER="https://your-opensearch:9200" \
  --publish 3030:3030 \
  orion-mcp
```

### Method 3: OpenShift/Kubernetes Deployment

#### Quick Deployment
```bash
# Apply deployment manifest
oc apply -f openshift-deployment.yml

# Verify deployment
oc get pods -l app.kubernetes.io/name=orion-mcp
```

#### Custom Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orion-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orion-mcp
  template:
    metadata:
      labels:
        app: orion-mcp
    spec:
      containers:
      - name: orion-mcp
        image: orion-mcp:latest
        ports:
        - containerPort: 3030
        env:
        - name: ES_SERVER
          value: "https://your-opensearch:9200"
```

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ES_SERVER` | ✅ Yes | None | OpenSearch/Elasticsearch endpoint URL |
| `ES_METADATA_INDEX` | No | `perf_scale_ci*` | Metadata index pattern |
| `ES_BENCHMARK_INDEX` | No | `ripsaw-kube-burner-*` | Benchmark data index pattern |
| `ORION_DEBUG` | No | `false` | Enable debug logging |
| `PYTHONUNBUFFERED` | No | `false` | Disable Python output buffering |

### Configuration File
Create `.env` file in project root:
```bash
ES_SERVER=https://your-opensearch:9200
ES_METADATA_INDEX=perf_scale_ci*
ES_BENCHMARK_INDEX=ripsaw-kube-burner-*
ORION_DEBUG=true
```

## 🔐 Authentication Setup

### OpenSearch Authentication

The server uses the `ES_SERVER` environment variable to connect to OpenSearch/Elasticsearch. You can include authentication credentials in the URL:

```bash
export ES_SERVER="https://username:password@opensearch:9200"
```

Or use a URL without credentials if your OpenSearch instance doesn't require authentication:

```bash
export ES_SERVER="https://opensearch:9200"
```

## 🧪 Verification

### Test Installation
```bash
# Start server
python orion_mcp.py &

# Verify server is running (check logs for startup messages)
# Server should start on http://localhost:3030

# Stop server
pkill -f orion_mcp.py
```

### Expected Output
```json
{
  "content": [
    {
      "type": "text",
      "text": "[\"small-scale-udn-l3.yaml\", \"trt-external-payload-cluster-density.yaml\", ...]"
    }
  ]
}
```

## 🚨 Troubleshooting

### Common Issues


#### Dependency Installation Failures
```bash
# Update pip
pip install --upgrade pip setuptools wheel

# Install build dependencies
sudo apt install build-essential python3.11-dev

# Retry installation
pip install -r requirements.txt
```

#### OpenSearch Connection Issues
```bash
# Check DNS resolution
nslookup your-opensearch-host

# Verify certificates (if using HTTPS)
openssl s_client -connect your-opensearch-host:9200
```

#### Container Build Failures
```bash
# Clear build cache
podman system prune -a

# Build with verbose output
podman build --no-cache -t orion-mcp .

# Check for base image issues
podman pull python:3.11.8-slim-bookworm
```

#### Port Already in Use
```bash
# Find process using port 3030
sudo netstat -tulpn | grep 3030

# Kill process
sudo kill -9 <PID>
```

### Debug Mode

Enable detailed logging:
```bash
export ORION_DEBUG=1
export PYTHONUNBUFFERED=1
python orion_mcp.py
```

### Log Analysis
```bash
# Check container logs
podman logs orion-mcp

# Follow logs in real-time
podman logs -f orion-mcp

# Check system logs
journalctl -u orion-mcp
```

## 🔄 Updates

### Update Local Installation
```bash
cd orion-mcp
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
```

### Update Container
```bash
# Rebuild image
podman build -t orion-mcp .

# Stop and remove old container
podman stop orion-mcp
podman rm orion-mcp

# Start new container
podman run --name orion-mcp \
  --env ES_SERVER="https://your-opensearch:9200" \
  --publish 3030:3030 \
  orion-mcp
```

## 📚 Next Steps

After successful installation:

1. **[Quick Start Guide](quickstart.md)** - Run your first analysis
2. **[API Reference](api/README.md)** - Explore available tools
3. **[Features Guide](features/README.md)** - Complete features documentation

---

**Need Help?** File an issue on GitHub or check the [main documentation](README.md).
