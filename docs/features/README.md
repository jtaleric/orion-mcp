# Features Overview

> **Navigation**: [Documentation Home](../README.md) → Features

Orion MCP provides powerful performance analysis features for OpenShift and Kubernetes environments.

## 🎯 Core Features

### Performance Regression Detection
- **Pull Request Analysis** - Automated PR performance impact analysis
- **Regression Detection** - System-wide changepoint detection  
- **Metric Correlation** - Multi-metric relationship analysis

### Visualization & Reporting
- **Performance Charts** - Trend lines, scatter plots, and multi-version comparisons
- **Custom Reports** - Generate publication-ready performance reports

### Data Analysis
- **Metric Collection** - Available performance metrics and their meanings
- **Configuration Management** - Test configuration options and customization

## 🚀 Feature Comparison

| Feature | Description | Use Case | Output Format |
|---------|-------------|----------|---------------|
| **PR Analysis** | Compare PR vs baseline performance | CI/CD integration, code review | JSON with regression flags |
| **Regression Detection** | Scan for performance changepoints | Monitoring, alerting | Text summary with affected metrics |
| **Metric Correlation** | Analyze relationships between metrics | Root cause analysis | Scatter plot with correlation coefficient |
| **Trend Analysis** | Multi-version performance trends | Release planning, capacity planning | Multi-line charts |

---

# Pull Request Performance Analysis

## Overview

The PR Performance Analysis feature provides **automated performance regression detection** for GitHub Pull Requests by comparing PR-specific test results against periodic baseline performance data.

### How It Works

1. **Baseline Collection**: Gathers periodic performance data for the specified OpenShift version over the lookback period
2. **PR Analysis**: Runs performance tests specifically for the target Pull Request
3. **Comparison**: Compares PR performance against the periodic baseline using a **10% threshold**
4. **Multi-Config Testing**: Tests across multiple Orion configurations for comprehensive coverage

## API Reference

### `openshift_report_on_pr`

**Method**: POST  
**Endpoint**: `/tools/openshift_report_on_pr`  
**Content-Type**: `application/json`

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `version` | string | No | `"4.20"` | OpenShift version to analyze |
| `lookback` | string | No | `"15"` | Number of days to look back for baseline data |
| `organization` | string | No | `"openshift"` | GitHub organization name |
| `repository` | string | No | `"ovn-kubernetes"` | GitHub repository name |
| `pull_request` | string | No | `"2841"` | Pull request number |

#### Response Format

```json
{
  "summaries": [
    {
      "config": "/orion/examples/trt-external-payload-cluster-density.yaml",
      "periodic_avg": {
        "podReadyLatency_P99": 1250.5,
        "ovnCPU_avg": 0.85,
        "memory_usage": 2048.3,
        "networkLatency_avg": 15.2
      },
      "pull": {
        "podReadyLatency_P99": 1375.2,
        "ovnCPU_avg": 0.92,
        "memory_usage": 2156.7,
        "networkLatency_avg": 16.8
      }
    }
  ]
}
```

## Quick Start Guide

### 1. Basic PR Analysis
Analyze a Pull Request using default parameters:
- **Organization**: openshift
- **Repository**: ovn-kubernetes  
- **Version**: 4.20
- **Lookback**: 15 days

### 2. Analyze Different Version
Analyze the same PR against a different OpenShift version (e.g., 4.21) to see version-specific performance impacts.

### 3. Extended Lookback Period
Use a longer lookback period (e.g., 30 days) to get a more stable baseline for comparison, useful when recent data might be noisy.

## Understanding Results

### Sample Response Analysis
```json
{
  "summaries": [
    {
      "config": "/orion/examples/trt-external-payload-cluster-density.yaml",
      "periodic_avg": {
        "podReadyLatency_P99": 1250.5,
        "ovnCPU_avg": 0.85
      },
      "pull": {
        "podReadyLatency_P99": 1375.2,
        "ovnCPU_avg": 0.92
      }
    }
  ]
}
```

### Regression Detection
- **podReadyLatency_P99**: `(1375.2 - 1250.5) / 1250.5 = 9.97%` ✅ **OK** (< 10%)
- **ovnCPU_avg**: `(0.92 - 0.85) / 0.85 = 8.24%` ✅ **OK** (< 10%)

### Interpreting Results

- **periodic_avg**: Baseline performance metrics averaged over the lookback period
- **pull**: Performance metrics from the specific PR's test runs
- **Regression Detection**: Compare values using the 10% threshold:
  - `(pull_value - periodic_avg) / periodic_avg > 0.10` indicates a potential regression
  - Values within ±10% are considered normal variance

## Test Configurations

The PR analysis runs against these key performance test configurations:

| Configuration | Focus Area | Key Metrics |
|---------------|------------|-------------|
| `trt-external-payload-cluster-density.yaml` | Pod scaling, cluster stress | `podReadyLatency_P99`, `ovnCPU_avg` |
| `trt-external-payload-node-density.yaml` | Node resource utilization | `nodeMemoryUtilization`, `cpuUtilization` |
| `trt-external-payload-node-density-cni.yaml` | Network performance | `cniLatency_P95`, `networkThroughput` |
| `trt-external-payload-crd-scale.yaml` | API server performance | `crdCreationLatency`, `apiServerLatency` |

## Performance Metrics

### Latency Metrics
- **Pod startup latency** (P50, P95, P99) - Time for pods to reach ready state
- **API server response times** - Kubernetes API operation latency
- **Network latency measurements** - Container networking performance
- **Storage I/O latency** - Persistent volume operation times

### Resource Utilization
- **CPU utilization** (avg, max, P95) - Processor usage across nodes
- **Memory usage and pressure** - RAM consumption and memory pressure
- **Network throughput and packet loss** - Network performance metrics
- **Disk I/O operations and bandwidth** - Storage performance metrics

### Scalability Metrics
- **Maximum pod density per node** - Scaling limits per worker node
- **Cluster scaling limits** - Maximum cluster capacity
- **Time to scale operations** - Duration of scaling events
- **Resource efficiency ratios** - Resource utilization efficiency

## Implementation Details

### Data Flow

1. **Input Validation**: Validates organization, repository, and PR parameters
2. **Configuration Loading**: Loads predefined test configurations
3. **Orion Execution**: Runs Orion with input variables:
   ```json
   {
     "jobtype": "pull",
     "organization": "openshift",
     "repository": "ovn-kubernetes", 
     "pull_number": "2841",
     "version": "4.20"
   }
   ```
4. **Data Processing**: Extracts `periodic_avg` and `pull` metrics from Orion output
5. **Response Formatting**: Returns structured JSON for AI/LLM consumption

### Orion Command Integration

The feature passes input variables to Orion using the `--input-vars` flag:

```bash
orion --lookback 15d --hunter-analyze \
  --config /orion/examples/trt-external-payload-cluster-density.yaml \
  --input-vars '{"jobtype":"pull","organization":"openshift","repository":"ovn-kubernetes","pull_number":"2841","version":"4.20"}' \
  -o json
```

## Common Use Cases

### CI/CD Integration
Integrate PR performance analysis into your CI/CD pipeline to automatically check for performance regressions before merging code changes. The analysis compares PR performance against baseline metrics using configurable thresholds.

### Release Validation
Use PR analysis during release cycles to validate that performance improvements or fixes don't introduce regressions in other areas.

### Performance Monitoring
Continuously monitor the performance impact of code changes across different OpenShift versions and configurations.

## Parameters Reference

| Parameter | Default | Description | Example Values |
|-----------|---------|-------------|----------------|
| `organization` | `"openshift"` | GitHub org | `"kubernetes"`, `"openshift"` |
| `repository` | `"ovn-kubernetes"` | GitHub repo | `"kubernetes"`, `"ovn-kubernetes"` |
| `pull_request` | `"2841"` | PR number | `"12345"`, `"999"` |
| `version` | `"4.20"` | OpenShift version | `"4.19"`, `"4.21"`, `"4.22"` |
| `lookback` | `"15"` | Days of baseline data | `"7"`, `"30"`, `"60"` |

## Error Handling

The API handles various error conditions:

- **Invalid JSON**: Returns parsing error details
- **Orion Command Failure**: Returns command output and error codes
- **Missing Data**: Handles cases where periodic or PR data is unavailable
- **Configuration Errors**: Reports issues with Orion configuration files

## Troubleshooting

### Common Issues

1. **No Data Available**
   - Ensure the PR has been tested in the performance CI
   - Check that the lookback period includes relevant test runs
   - Verify the organization/repository names are correct

2. **Configuration Errors**
   - Ensure Orion configuration files exist in `/orion/examples/`
   - Check that the ES_SERVER environment variable is set
   - Verify OpenSearch connectivity and permissions

3. **Parsing Errors**
   - Check Orion output format compatibility
   - Ensure JSON output is properly formatted
   - Verify that required fields (`periodic_avg`, `pull`) exist

### No Data Returned
- **Check if PR exists** - Verify the Pull Request number is valid and has associated performance data
- **Validate parameters** - Ensure organization, repository, and version parameters are correct

### Server Connection Issues
- **Test server connectivity** - Verify the MCP server is running and accessible
- **Check server logs** - Review container or application logs for error messages

### Data Source Issues  
- **Verify OpenSearch connection** - Ensure the data source is properly configured and accessible
- **Check authentication** - Verify credentials and network connectivity to the data source

## Advanced Analysis

### Compare Multiple PRs
Compare performance impact across different Pull Requests by analyzing each PR separately and comparing their metrics against the same baseline period.

### Historical Trend Analysis
Analyze the same PR with different lookback periods (7 days vs 30 days) to understand how baseline stability affects regression detection. Longer periods provide more stable baselines but may miss recent performance shifts.

## AI/LLM Integration

### Response Format Optimization

The response format is optimized for AI analysis. The LLM can:

1. **Automatically detect regressions** by comparing periodic_avg vs pull metrics
2. **Apply the 10% threshold** to determine significance
3. **Generate human-readable reports** highlighting concerning changes
4. **Provide actionable insights** about which metrics regressed and by how much

### Example AI Analysis Prompt

```
Analyze this PR performance data and identify any regressions using a 10% threshold:
[paste the JSON response]

For each metric that shows >10% degradation, explain:
1. The metric name and what it measures
2. The baseline vs PR values  
3. The percentage change
4. Potential impact on users

Format as a markdown report with severity levels (🔴 Critical, 🟡 Warning, 🟢 OK).
```

### Example AI Analysis Output
```markdown
# PR #2841 Performance Analysis

## Summary
- ✅ **No critical regressions detected**
- 🟡 **2 metrics show minor increases** (< 10% threshold)

## Detailed Results

### Cluster Density Configuration
- 🟢 **podReadyLatency_P99**: 1250.5ms → 1375.2ms (+9.97%) - Within acceptable range
- 🟢 **ovnCPU_avg**: 0.85 → 0.92 (+8.24%) - Minor increase, monitor in production

### Recommendations
1. Monitor pod startup times in production
2. Consider CPU resource limits for OVN components
3. No blocking issues for merge
```

## Supported Versions

- **OpenShift**: 4.17+
- **Kubernetes**: 1.24+
- **OKD**: (OpenShift Origin)

---

**Next Steps**: 
- Explore [API Reference](../api/README.md) for complete tool documentation
- See [Examples](../examples/README.md) for real-world usage patterns
- Check [Installation Guide](../installation.md) for setup instructions