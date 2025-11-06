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