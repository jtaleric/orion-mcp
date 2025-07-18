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
    convert_results_to_csv,
    csv_to_graph,
    summarize_result,
    get_data_source,
    orion_metrics,
    orion_configs,
    generate_correlation_plot
)

mcp = FastMCP(name="orion-mcp",
              host="0.0.0.0",
              port=3030,
              log_level='INFO')

ORION_CONFIGS = [
    "/orion/examples/trt-external-payload-cluster-density.yaml",
    "/orion/examples/trt-external-payload-node-density.yaml",
    "/orion/examples/trt-external-payload-node-density-cni.yaml",
    "/orion/examples/trt-external-payload-crd-scale.yaml",
    "/orion/examples/small-scale-udn-l3.yaml"
]

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
async def get_orion_metrics() -> dict:
    """
    Provides the metrics for Orion analysis.

    Returns:
        dictionary of metrics names that Orion uses to analyze the data.
        the key is the config the metric is associated with
        the value is a list of all the metric names that are available for that config
    """
    return await orion_metrics(ORION_CONFIGS)


@mcp.tool()
async def openshift_report_on(
    version: Annotated[str, Field(description="Version of OpenShift to look into")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    metric: Annotated[str, Field(description="Metric to analyze")] = "containerCPU",
    config: Annotated[str, Field(description="Config to analyze")] = "cluster-density.yaml",
) -> types.ImageContent | types.TextContent:
    """
    Captures a performance analysis against the specified OpenShift version using Orion.

    Orion uses an EDivisive algorithm to analyze performance data from a specified
    configuration file to detect any performance regressions.

    Args:
        version: Openshift version to look into.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        metric: The metric to analyze. Defaults to CPU.
        config: The config to analyze. Defaults to trt-external-payload-cluster-density.yaml.

    Returns:
        Returns an image showing the performance overtime.
    """

    path="/orion/examples/"

    result = await run_orion(
        lookback=lookback,
        config=path + config,
        data_source=get_data_source(),
        version=version
    )

    if result.returncode != 0:
        sum_result = await summarize_result(result)
        error_results = [{"error": sum_result}]
        b64_imgs = await csv_to_graph(convert_results_to_csv(error_results))
        imgs = []
        for img in b64_imgs:
            if img is None:
                continue
            b64_img = img.decode('utf-8')
            imgs.append(
                types.ImageContent(type="image", data=b64_img, mimeType="image/jpeg")
            )
        return imgs[0]

    data = {}
    data[config] = {}
    data[config] = await summarize_result(result, isolate=metric)
    results = [data]
    b64_imgs = await csv_to_graph(convert_results_to_csv(results))
    imgs = []
    for img in b64_imgs:
        if img is None:
            continue
        b64_img = img.decode('utf-8')
        imgs.append(
            types.ImageContent(type="image", data=b64_img, mimeType="image/jpeg")
        )
    return imgs[0]


def _extract_regression_metrics(stdout: str) -> list[str]:
    """Extract regression metrics from orion output."""
    data = json.loads(stdout)
    metrics = []
    for dat in data:
        if not dat["is_changepoint"]:
            continue
        for metric in dat["metrics"]:
            percentage_change = dat["metrics"][metric]["percentage_change"]
            if percentage_change > 0:
                metrics.append(f"{metric} increased by {percentage_change}%")
    return metrics


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

    for config in ORION_CONFIGS:
        # Execute the command as a subprocess
        result = await run_orion(
            lookback=lookback,
            config=config,
            data_source=get_data_source(),
            version=version
        )

        if result.returncode != 0:
            metrics = _extract_regression_metrics(result.stdout)
            if metrics:
                return f"Regression found while running config: {config}, metrics: {', '.join(metrics)}"

    return "No regressions found"


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

    path = "/orion/examples/"

    # Run Orion to gather data
    result = await run_orion(
        lookback=lookback,
        config=path + config,
        data_source=get_data_source(),
        version=version,
    )

    # Handle execution errors early
    if result.returncode != 0:
        summary_err = await summarize_result(result)
        return types.TextContent(type="text", text=f"Failed to execute Orion: {summary_err}")

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

