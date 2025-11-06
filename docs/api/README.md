# API Reference

> **Navigation**: [Documentation Home](../README.md) → API Reference

Complete reference for the Orion MCP API, including all tools, resources, and integration patterns.

## 📋 Overview

Orion MCP exposes its functionality through the Model Context Protocol (MCP), providing:

- **Tools** - Executable functions for performance analysis
- **Resources** - Data sources and configuration information
- **Structured Responses** - JSON outputs optimized for AI/LLM consumption

## 🛠️ Available Tools

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| [`get_orion_configs`](tools.md#get_orion_configs) | List available test configurations | None | Array of config filenames |
| [`get_orion_metrics`](tools.md#get_orion_metrics) | Get metrics for a configuration | `config` | Metrics dictionary |
| [`openshift_report_on`](tools.md#openshift_report_on) | Generate performance trends | `versions`, `metric`, `config` | Image (PNG/JPEG) |
| [`openshift_report_on_pr`](tools.md#openshift_report_on_pr) | Analyze PR performance | `organization`, `repository`, `pull_request` | JSON analysis |
| [`has_openshift_regressed`](tools.md#has_openshift_regressed) | Detect regressions | `version`, `lookback` | Text summary |
| [`metrics_correlation`](tools.md#metrics_correlation) | Correlate two metrics | `metric1`, `metric2`, `config` | Scatter plot image |

## 📊 Resources

| Resource | Purpose | Data Format |
|----------|---------|-------------|
| [`get_data_source`](resources.md#get_data_source) | OpenSearch endpoint URL | String |

## 🔗 Base URL

```
http://localhost:3030
```

## 📝 Request Format

All tool requests use HTTP POST with JSON payloads sent to the appropriate tool endpoint. The MCP server accepts structured JSON parameters for each tool and returns formatted responses.

## 📤 Response Formats

### Successful Tool Response
```json
{
  "content": [
    {
      "type": "text|image",
      "text": "...",           // For text responses
      "data": "...",        // For image responses (base64)
      "mimeType": "..."     // For image responses
    }
  ]
}
```

### Error Response
```json
{
  "error": {
    "code": "TOOL_ERROR",
    "message": "Detailed error description"
  }
}
```

## 🎯 Available Operations

### Configuration Management
- **List Available Configurations** - Get all available Orion test configurations
- **Get Configuration Metrics** - Retrieve metrics available for a specific configuration

### Performance Analysis  
- **Analyze Pull Requests** - Compare PR performance against baseline metrics
- **Check for Regressions** - Detect performance changepoints across configurations
- **Generate Trend Charts** - Create multi-version performance visualizations
- **Correlate Metrics** - Analyze relationships between different performance metrics

## 📚 Detailed Documentation

- **[Tools Reference](tools.md)** - Complete tool documentation with parameters and examples
- **[Resources Reference](resources.md)** - Available resources and data sources
- **[Integration Guide](../examples/integrations.md)** - CI/CD and automation examples
- **[AI/LLM Integration](../examples/ai-integration.md)** - Using with AI systems

## 🔧 Authentication

Currently, Orion MCP uses environment-based authentication:

- **OpenSearch**: Configure via `ES_SERVER` environment variable
- **GitHub**: No authentication required for public repositories

## 🚨 Rate Limits

- No built-in rate limiting
- Performance analysis can be resource-intensive
- Consider implementing client-side throttling for high-volume usage

## 📈 Best Practices

### Performance
- Use specific configurations rather than scanning all configs
- Limit lookback periods to reduce data processing time
- Cache results when possible

### Error Handling
- Always check response status codes
- Parse error messages for debugging information
- Implement retry logic for transient failures

### Data Interpretation
- Use 10% threshold for regression detection
- Consider seasonal variations in baseline data
- Validate results against known performance changes

---

**Next**: Explore detailed [Tools Reference](tools.md) or see [Integration Examples](../examples/integrations.md)
