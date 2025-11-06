# Usage Examples

> **Navigation**: [Documentation Home](../README.md) → Examples

Real-world examples and integration patterns for Orion MCP.

## 📋 Example Categories

### Basic Usage
- **[Getting Started Examples](#getting-started)** - First steps and basic operations
- **[Command Line Examples](#command-line)** - Using curl and CLI tools
- **[Python Integration](#python-integration)** - Python client examples

### Advanced Integration
- **[CI/CD Integration](integrations.md)** - GitHub Actions, Jenkins, GitLab CI
- **[AI/LLM Integration](ai-integration.md)** - Using with ChatGPT, Claude, etc.
- **[Monitoring Integration](monitoring.md)** - Prometheus, Grafana, alerting

### Specific Use Cases
- **[Pull Request Analysis](#pr-analysis)** - Automated PR performance checks
- **[Release Validation](#release-validation)** - Pre-release performance validation
- **[Regression Hunting](#regression-hunting)** - Finding performance regressions

## 🚀 Getting Started

### Basic Server Health Check
```bash
# Check if server is running
curl http://localhost:3030/resources

# Expected response
{
  "resources": [
    {
      "uri": "orion-mcp://get_data_source",
      "name": "Data Source",
      "description": "OpenSearch endpoint URL"
    }
  ]
}
```

### List Available Configurations
```bash
curl -X POST http://localhost:3030/tools/get_orion_configs \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Get Metrics for a Configuration
```bash
curl -X POST http://localhost:3030/tools/get_orion_metrics \
  -H "Content-Type: application/json" \
  -d '{"config": "small-scale-udn-l3.yaml"}'
```

## 💻 Command Line

### Check for Regressions
```bash
#!/bin/bash
# check-regressions.sh

VERSION=${1:-"4.20"}
LOOKBACK=${2:-"15"}

echo "Checking for regressions in OpenShift $VERSION (last $LOOKBACK days)..."

RESULT=$(curl -s -X POST http://localhost:3030/tools/has_openshift_regressed \
  -H "Content-Type: application/json" \
  -d "{\"version\": \"$VERSION\", \"lookback\": \"$LOOKBACK\"}")

if echo "$RESULT" | grep -q "No changepoints found"; then
  echo "✅ No regressions detected"
  exit 0
else
  echo "⚠️  Regressions detected:"
  echo "$RESULT" | jq -r '.content[0].text'
  exit 1
fi
```

### Generate Performance Report
```bash
#!/bin/bash
# generate-report.sh

VERSIONS="4.19,4.20,4.21"
METRIC="podReadyLatency_P99"
CONFIG="small-scale-udn-l3.yaml"

echo "Generating performance report for $METRIC..."

curl -X POST http://localhost:3030/tools/openshift_report_on \
  -H "Content-Type: application/json" \
  -d "{
    \"versions\": \"$VERSIONS\",
    \"metric\": \"$METRIC\",
    \"config\": \"$CONFIG\"
  }" | jq -r '.content[0].data' | base64 -d > performance_report.png

echo "Report saved as performance_report.png"
```

## 🐍 Python Integration

### Basic Client
```python
import requests
import json
import base64
from typing import Dict, List, Optional

class OrionMCPClient:
    def __init__(self, base_url: str = "http://localhost:3030"):
        self.base_url = base_url
    
    def _post_tool(self, tool_name: str, params: Dict) -> Dict:
        """Execute a tool with given parameters."""
        url = f"{self.base_url}/tools/{tool_name}"
        response = requests.post(url, json=params)
        response.raise_for_status()
        return response.json()
    
    def get_configs(self) -> List[str]:
        """Get list of available Orion configurations."""
        result = self._post_tool("get_orion_configs", {})
        return json.loads(result["content"][0]["text"])
    
    def check_regressions(self, version: str = "4.20", lookback: str = "15") -> str:
        """Check for performance regressions."""
        result = self._post_tool("has_openshift_regressed", {
            "version": version,
            "lookback": lookback
        })
        return result["content"][0]["text"]
    
    def analyze_pr(self, org: str, repo: str, pr: str, version: str = "4.20") -> Dict:
        """Analyze pull request performance."""
        result = self._post_tool("openshift_report_on_pr", {
            "organization": org,
            "repository": repo,
            "pull_request": pr,
            "version": version
        })
        return json.loads(result["content"][0]["text"])
    
    def generate_chart(self, versions: str, metric: str, config: str) -> bytes:
        """Generate performance chart and return image data."""
        result = self._post_tool("openshift_report_on", {
            "versions": versions,
            "metric": metric,
            "config": config
        })
        
        if result["content"][0]["type"] == "image":
            return base64.b64decode(result["content"][0]["data"])
        else:
            raise ValueError("Expected image response")

# Usage example
client = OrionMCPClient()

# Check for regressions
regressions = client.check_regressions("4.20", "7")
print(f"Regression check: {regressions}")

# Analyze a PR
pr_analysis = client.analyze_pr("openshift", "ovn-kubernetes", "2841")
print(f"PR analysis: {json.dumps(pr_analysis, indent=2)}")

# Generate chart
chart_data = client.generate_chart("4.19,4.20", "podReadyLatency_P99", "small-scale-udn-l3.yaml")
with open("performance_chart.png", "wb") as f:
    f.write(chart_data)
```

## 📚 Next Steps

- **[Features Guide](../features/README.md)** - Complete features documentation
- **[API Reference](../api/README.md)** - Complete API documentation

---

**Need more examples?** Check our [GitHub repository](https://github.com/YOUR_ORG/orion-mcp) or file an issue with your use case.