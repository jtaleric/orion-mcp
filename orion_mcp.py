"""
Model Context Protocol (MCP) server for Orion performance regression analysis.

This module provides tools for running performance regression analysis using
the cloud-bulldozer/orion library.
"""

import asyncio
import json
import os
from typing import Annotated
from pydantic import Field

from mcp import types
from mcp.server.fastmcp import FastMCP

# Import utility functions from utils module
from utils.utils import (
    run_orion,
    summarize_result,
    get_data_source,
    orion_metrics,
    orion_configs,
    generate_correlation_plot,
    generate_multi_line_plot,
    list_orion_configs
)

RELEASE_DATES = {
    "4.17": "2024-10-29",
    "4.18": "2025-02-28",
    "4.19": "2025-06-17",
    "4.20": "2025-10-23",
}

mcp = FastMCP(name="orion-mcp",
              host="0.0.0.0",
              port=3030,
              log_level='INFO')

ORION_CONFIGS_PATH = "/orion/examples/"
_configs=list_orion_configs()
if _configs == []:
    ORION_CONFIGS = [
    "metal-perfscale-cpt-virt-udn-density.yaml",
    "trt-external-payload-cluster-density.yaml",
    "trt-external-payload-node-density.yaml",
    "trt-external-payload-node-density-cni.yaml",
    "trt-external-payload-crd-scale.yaml",
    "small-scale-udn-l3.yaml",
    "med-scale-udn-l3.yaml",]
else:
    ORION_CONFIGS = _configs

FULL_ORION_CONFIG_PATHS = [os.path.join(ORION_CONFIGS_PATH, config) for config in ORION_CONFIGS]

@mcp.resource("orion-mcp://release_dates")
def release_dates_resource() -> dict[str, str]:
    """
    Provides the release dates for the different OpenShift versions.
    """
    return RELEASE_DATES

@mcp.resource("orion-mcp://get_data_source")
def get_data_source_resource() -> str:
    """
    Provides the data source URL for Orion analysis.

    User must launch MCP server with the environment variable ES_SERVER
    set to the OpenSearch URL.

    Returns:
        The OpenSearch URL as a string.
    """
    return get_data_source()

@mcp.tool()
def get_orion_configs() -> list[str]:
    """
    Return the list of Orion config filenames (not full paths).
    """
    return orion_configs(ORION_CONFIGS)

@mcp.tool()
async def get_orion_metrics(
    config: Annotated[str, Field(description="Orion configuration file name (e.g. 'small-scale-udn-l3.yaml')")] = "small-scale-udn-l3.yaml",
) -> dict:
    """Return the list of metrics available for a specific Orion *config*.

    Args:
        config: **Filename** of the Orion configuration to query (not the full path).

    Returns:
        A dictionary where the key is the *config* (full path) and the value is a
        list of metric names available for that configuration.
    """

    # Query only the requested config
    result = await orion_metrics([ORION_CONFIGS_PATH + config])

    if isinstance(result, str):
        return {"error": f"Failed to fetch Orion metrics: {result}"}

    return result


@mcp.tool()
async def openshift_report_on(
    versions: Annotated[str, Field(description="Comma-separated list of OpenShift versions e.g. '4.19,4.20'")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    metric: Annotated[str, Field(description="Metric to analyze")] = "podReadyLatency_P99",
    config: Annotated[str, Field(description="Config to analyze")] = "small-scale-udn-l3.yaml",
) -> types.ImageContent | types.TextContent:
    """
    Captures a performance analysis against the specified OpenShift version using Orion.

    Orion uses an EDivisive algorithm to analyze performance data from a specified
    configuration file to detect any performance regressions.

    Args:
        version: Comma-separated list of OpenShift versions to analyze.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        metric: The metric to analyze. Defaults to CPU.
        config: The config to analyze. Defaults to trt-external-payload-cluster-density.yaml.

    Returns:
        Returns an image showing the performance overtime.
    """

    # Parse versions into list
    if isinstance(versions, str):
        version_list = [v.strip() for v in versions.split(',') if v.strip()]
    else:
        version_list = list(versions)

    series: dict[str, list[float]] = {}

    for ver in version_list:
        result = await run_orion(
            lookback=lookback,
            config=ORION_CONFIGS_PATH + config,
            data_source=get_data_source(),
            version=ver,
        )

        sum_result = await summarize_result(result, isolate=metric)

        # Ensure we have the expected structure before indexing
        if not isinstance(sum_result, dict) or metric not in sum_result:
            return types.TextContent(type="text", text=f"No data for version {ver}: {sum_result}")

        raw_values = sum_result[metric].get("value", [])  # type: ignore[assignment]
        if not isinstance(raw_values, list):
            return types.TextContent(type="text", text=f"Unexpected data format for version {ver}")

        # Remove None values to keep the plot continuous
        values = [v for v in raw_values if v is not None]
        if not values:
            return types.TextContent(type="text", text=f"All values are None for version {ver}")

        series[ver] = values
        print(f"series: {series}")

    # Generate multi-line plot
    try:
        img_b64 = generate_multi_line_plot(series, metric, title_prefix=f"{config}: ")
    except ValueError as e:
        return types.TextContent(type="text", text=str(e))

    return types.ImageContent(type="image", data=img_b64.decode("utf-8"), mimeType="image/jpeg")

async def get_pr_details(organization: str, repository: str, pull_request: str, version: str = "4.20", lookback: str = "15") -> list[dict]:
    """
    Get PR performance analysis details by running Orion with input variables.
    
    Args:
        organization: GitHub organization name
        repository: Repository name  
        pull_request: Pull request number
        version: OpenShift version to analyze
        lookback: Days to look back for data
        
    Returns:
        List of dictionaries containing PR analysis results for each config. 
        Each dictionary contains the config, periodic_avg, and pull.
        periodic_avg is the average of the periodic metrics for the version.
        pull contains the results from running performance tests aginst the pull request.
        The LLM should compare the periodic_avg to the pull metrics and determine if the PR introduces a performance regression. 
        The LLM should use a 10% threshold to determine if the PR introduces a performance regression.
    """

    configs = [
        "trt-external-payload-cluster-density.yaml",
        "trt-external-payload-node-density.yaml",
        "trt-external-payload-node-density-cni.yaml",
        "trt-external-payload-crd-scale.yaml",
    ]

    input_vars = {"jobtype": "pull",
            "organization": organization,
            "repository": repository,
            "pull_number": pull_request,
            "version": version}
            
    full_config_paths = [os.path.join(ORION_CONFIGS_PATH, config) for config in configs]
    summaries: list[dict] = []
    for full_config_path in full_config_paths:
        result = await run_orion(
            lookback=lookback,
            config=full_config_path,
            data_source=get_data_source(),
            version=version,
            input_vars=input_vars
        )
        data=json.loads(result.stdout)
        if "periodic_avg" not in data or "pull" not in data:
            return types.TextContent(type="text", text=f"Having issues finding PR data, please ensure the version the PR was tested on is correct and the PR was tested against the correct version of OpenShift.")
        summaries.append({
            "config": full_config_path,
            "periodic_avg": data["periodic_avg"],
            "pull": data["pull"]
        })
    return summaries

@mcp.tool()
async def openshift_report_on_pr(
    version: Annotated[str, Field(description="OpenShift version to analyze")] = "4.20",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    organization: Annotated[str, Field(description="Organization to look into")] = "openshift",
    repository: Annotated[str, Field(description="Repository to look into")] = "ovn-kubernetes",
    pull_request: Annotated[str, Field(description="PR to look into")] = "2841",
) -> dict:
    """
    Captures a performance analysis against the specified OpenShift version using Orion.

    Args:
        version: OpenShift version to analyze.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        organization: The organization to look into. Defaults to openshift.
        repository: The repository to look into. Defaults to ovn-kubernetes.
        pull_request: The PR to look into. Defaults to 2841.

    Returns:
        List of dictionaries containing PR analysis results for each version.
    """
    # Get the PR details
    summaries = await get_pr_details(organization, repository, pull_request, version, lookback)
    return {
        "summaries": summaries
    }


def _extract_regression_details(stdout: str) -> list[dict]:
    """Extract regression details (uuid, ocpVersion, previous ocpVersion, PR diffs, metrics)."""
    data = json.loads(stdout)
    details: list[dict] = []
    for idx, dat in enumerate(data):
        if not dat.get("is_changepoint"):
            continue

        # Build human-readable metric changes
        metrics: list[str] = []
        for metric_name, metric_info in dat.get("metrics", {}).items():
            percentage_change = metric_info.get("percentage_change", 0)
            if percentage_change > 0:
                metrics.append(f"{metric_name} increased by {percentage_change:.2f}%")
            elif percentage_change < 0:
                metrics.append(f"{metric_name} decreased by {abs(percentage_change):.2f}%")

        # Previous document (if available)
        prev_doc = data[idx - 1] if idx > 0 else None
        prev_ocp_version = prev_doc.get("ocpVersion") if isinstance(prev_doc, dict) else None

        # Compute PR differences between current and previous
        current_prs = dat.get("prs", []) or []
        prev_prs = (prev_doc.get("prs", []) if isinstance(prev_doc, dict) else []) or []
        # Preserve ordering while removing items present in the other list
        prs_added = [p for p in current_prs if p not in prev_prs]

        details.append({
            "uuid": dat.get("uuid"),
            "ocpVersion": dat.get("ocpVersion"),
            "previousOcpVersion": prev_ocp_version,
            "prs_added": prs_added,
            "metrics": metrics,
        })

        
    return details


async def _run_regression_checks(
    configs: list[str],
    version: str,
    lookback: str,
) -> str:
    """
    Execute Orion across the provided configs and return a formatted summary of
    detected changepoints, or "No changepoints found" if none are detected.
    """
    full_config_paths = [os.path.join(ORION_CONFIGS_PATH, config) for config in configs]
    changepoints: list[str] = []

    for full_config_path in full_config_paths:
        result = await run_orion(
            lookback=lookback,
            config=full_config_path,
            data_source=get_data_source(),
            version=version,
        )

        if result.returncode not in (0, 3):
            details = _extract_regression_details(result.stdout)
            for det in details:
                header_lines = [
                    f"⚠️ Change detected in configuration: '{full_config_path}'",
                    f"UUID: {det.get('uuid')}",
                    f"OCP Version: {det.get('ocpVersion')}",
                    f"Previous OCP Version: {det.get('previousOcpVersion')}",
                    "PRs added since Previous OCP Version:",
                ]
                prs_added = det.get("prs_added") or []
                if prs_added:
                    header_lines.extend([f"  - {pr}" for pr in prs_added])
                else:
                    header_lines.append("  - None")

                metrics_list = det.get("metrics", [])
                if metrics_list:
                    header_lines.append("Affected metrics:")
                    header_lines.extend([f"  - {m}" for m in metrics_list])

                changepoints.append("\n".join(header_lines))

    if changepoints:
        return "\n\n".join(changepoints)
    return "No changepoints found"

@mcp.tool()
async def has_openshift_regressed(
    version: Annotated[str, Field(description="Version of OpenShift to look into")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
) -> str:
    """
    Runs a performance regression analysis against the OpenShift version using Orion.

    Orion uses an EDivisive algorithm to analyze performance data from a specified
    configuration file to detect any performance regressions.

    Args:
        version: Openshift version to look into.
        lookback: The number of days to look back for performance data. Defaults to 15 days.

    Returns:
        Returns string stating if there is a regression and in which config it was found.
                       If no regressions are found, returns "No regressions found".
    """

    configs = [
        "trt-external-payload-cluster-density.yaml",
        "trt-external-payload-node-density.yaml",
        "trt-external-payload-node-density-cni.yaml",
        "trt-external-payload-crd-scale.yaml",
    ]
    return await _run_regression_checks(configs, version=version, lookback=lookback)


# Networking-only regression tool
@mcp.tool()
async def has_networking_regressed(
    version: Annotated[str, Field(description="Version of OpenShift to look into")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
) -> str:
    """
    Runs a performance regression analysis against networking-focused configs.

    Checks only the following Orion configurations:
      - small-scale-udn-l3.yaml
      - trt-external-payload-node-density-cni.yaml
    """

    configs = [
        "small-scale-udn-l3.yaml",
        "trt-external-payload-node-density-cni.yaml",
    ]
    return await _run_regression_checks(configs, version=version, lookback=lookback)

# Correlation tool

@mcp.tool()
async def metrics_correlation(
    metric1: Annotated[str, Field(description="First metric to analyze")] = "podReadyLatency_P99",
    metric2: Annotated[str, Field(description="Second metric to analyze")] = "ovnCPU_avg",
    config: Annotated[str, Field(description="Config to analyze")] = "trt-external-payload-cluster-density.yaml",
    version: Annotated[str, Field(description="Version of OpenShift to look into")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
) -> types.ImageContent | types.TextContent:
    """
    Calculate and visualise the correlation between two metrics for a given
    Orion configuration.

    A scatter-plot annotated with the Pearson correlation coefficient is
    returned. If either metric is missing from the Orion results the function
    falls back to returning a textual error message.
    """

    # Run Orion to gather data
    result = await run_orion(
        lookback=lookback,
        config=ORION_CONFIGS_PATH + config,
        data_source=get_data_source(),
        version=version,
    )

    summary = await summarize_result(result)

    # Ensure we received a valid dict back
    if not isinstance(summary, dict):
        return types.TextContent(type="text", text=f"Error processing Orion output: {summary}")

    # Extract metric values
    try:
        values1 = summary[metric1]["value"]
        values2 = summary[metric2]["value"]
    except KeyError:
        return types.TextContent(
            type="text",
            text="Requested metrics not present in the Orion summary for the chosen configuration.",
        )

    # Compute correlation & generate plot
    corr_b64 = generate_correlation_plot(values1, values2, metric1, metric2, title_prefix=f"{config}: ")

    return types.ImageContent(type="image", data=corr_b64.decode("utf-8"), mimeType="image/jpeg")


def main():
    """Main function to run the MCP server."""
    # (No operation)


if __name__ == "__main__":
    if os.getenv("ES_SERVER") is None:
        print("ES_SERVER environment variable is not set")
        import sys
        sys.exit(1)
    TRANSPORT = "streamable-http"
    asyncio.run(mcp.run(transport=TRANSPORT))
    print("Running MCP server with transport:", TRANSPORT)

