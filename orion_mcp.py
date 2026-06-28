"""
Model Context Protocol (MCP) server for Orion performance regression analysis.

This module provides tools for running performance regression analysis using
the cloud-bulldozer/orion library.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Annotated
from pydantic import Field
import jinja2
import yaml

from mcp import types
from mcp.server.fastmcp import Context, FastMCP

# Import utility functions from utils module
from utils.utils import (
    run_orion,
    summarize_result,
    get_data_source,
    orion_metrics,
    orion_configs,
    generate_correlation_plot,
    generate_multi_line_plot,
    list_orion_configs,
    parse_nightly_version,
    parse_timestamp,
    filter_data_by_timestamp,
    current_es_config,  # Context variable for ES config isolation
)
from utils.header_decryption import get_es_config_from_headers

RELEASE_DATES = {
    "4.17": "2024-10-29",
    "4.18": "2025-02-28",
    "4.19": "2025-06-17",
    "4.20": "2025-10-23",
    "4.21": "2026-02-25",
    "4.22": "2026-06-17",
    "5.0": "2026-10-31",
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


def _extract_and_set_es_server(ctx) -> None:
    """
    Extract ES config from request headers and set in context variable.

    If encrypted ES config found in headers, decrypts it and sets current_es_config
    context variable. Config includes: es_server, es_metadata_index, es_benchmark_index.
    Downstream code (get_data_source, get_es_metadata_index, get_es_benchmark_index)
    checks context first.

    Falls back to environment variables if no header present.
    """
    if not ctx:
        return

    # Access HTTP headers through ctx.request_context.request.headers (Starlette Request)
    try:
        if hasattr(ctx, 'request_context') and ctx.request_context:
            request = ctx.request_context.request
            if request and hasattr(request, 'headers'):
                # Convert Starlette Headers to dict
                headers_dict = dict(request.headers)
                es_config = get_es_config_from_headers(headers_dict)
                if es_config:
                    current_es_config.set(es_config)
    except Exception:
        # Silently fall back to environment variables
        pass


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
async def get_release_date(
    version : Annotated[str, Field(description="OCP Version to get Release date")] = "4.20") -> str:
    """
    Get the release date for a given OpenShift version.

    Args:
        version: OpenShift version to get the release date for.
        Defaults to 4.20.

    Returns:
        The release date for the given OpenShift version.
        If the version is not a valid OpenShift version, returns "Invalid version: {version}".
    """
    if version in RELEASE_DATES :
        return RELEASE_DATES[version]
    return f"Invalid version: {version}"

@mcp.tool()
def get_orion_configs() -> list[str]:
    """
    Return the list of Orion config filenames (not full paths).
    """
    return orion_configs(ORION_CONFIGS)

@mcp.tool()
async def get_orion_metrics(
    config_name: Annotated[
        str | None,
        Field(
            description="Orion configuration file name (e.g. 'small-scale-udn-l3.yaml')"
        ),
    ] = None,
    version: Annotated[str, Field(description="OpenShift version used to query metrics")] = "4.20",
    ctx: Context = None,
) -> dict:
    """Return the list of metrics available for a specific Orion *config*.

    Args:
        config_name: **Filename** of the Orion configuration to query (not the full path).
        version: OpenShift version used to query metrics.
        ctx: MCP context for accessing request headers

    Returns:
        A dictionary where the key is the *config* (full path) and the value is a
        list of metric names available for that configuration.
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

    default_config = "small-scale-udn-l3.yaml"
    effective_config = config_name or default_config

    # Query only the requested config
    result = await orion_metrics([ORION_CONFIGS_PATH + effective_config], version=version)

    if isinstance(result, str):
        return {"error": f"Failed to fetch Orion metrics: {result}"}

    return result


@mcp.tool()
async def get_orion_metrics_with_meta(
    config_name: Annotated[
        str | None,
        Field(
            description="Orion configuration file name (e.g. 'small-scale-udn-l3.yaml')"
        ),
    ] = None,
    version: Annotated[str, Field(description="OpenShift version used to render the config template")] = "4.19",
    ctx: Context = None,
) -> dict:
    """Return metrics and metadata for a specific Orion *config*.

    Args:
        config_name: **Filename** of the Orion configuration to query (not the full path).
        version: OpenShift version used to render the config template.
        ctx: MCP context for accessing request headers

    Returns:
        A dictionary with "metrics" (list) and "meta" (per-metric metadata).
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

    default_config = "small-scale-udn-l3.yaml"
    effective_config = config_name or default_config
    try:
        metrics, meta_map = _load_config_metrics_with_meta(
            os.path.join(ORION_CONFIGS_PATH, effective_config),
            version=version,
        )
        return {"metrics": metrics, "meta": meta_map}
    except Exception as e:
        # Fall back to Orion metrics without metadata if parsing fails
        # Preserve the caller's version when we have to fall back to data-driven metric discovery.
        result = await orion_metrics(
            [ORION_CONFIGS_PATH + effective_config], version=version
        )
        if isinstance(result, str):
            return {"error": f"{e} | {result}"}
        return {"metrics": result, "meta": {}, "warning": str(e)}


@mcp.tool()
async def openshift_report_on(
    versions: Annotated[str, Field(description="Comma-separated list of OpenShift versions e.g. '4.19,4.20'")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    since: Annotated[str, Field(description="Date to begin lookback")] = None,
    *,
    metric: Annotated[str, Field(description="Metric to analyze")] = "podReadyLatency_P99",
    config_name: Annotated[
        str | None,
        Field(description="Orion configuration file name (e.g. 'small-scale-udn-l3.yaml')"),
    ] = None,
    options: Annotated[str, Field(description="Options in format 'output_format' or 'output_format:display_field'. Examples: 'image', 'json', 'both', 'json:ocpVirtVersion'")] = "image",
    ctx: Context = None,
) -> types.ImageContent | types.TextContent:
    """
    Captures a performance analysis against the specified OpenShift version using Orion.

    Orion uses an EDivisive algorithm to analyze performance data from a specified
    configuration file to detect any performance regressions.

    Args:
        versions: Comma-separated list of OpenShift versions to analyze.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        since: The date to begin looking back for performance data. Defaults to None.
        metric: The metric to analyze. Defaults to podReadyLatency_P99.
        config_name: The config to analyze. Defaults to small-scale-udn-l3.yaml.
        options: Output format and optional display field. Format: 'output_format' or
                'output_format:display_field'. Examples: 'image', 'json:ocpVirtVersion'.

    Returns:
        Returns an image showing the performance overtime, or JSON data based on options.
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

    # Parse options to extract output_format and display
    if ":" in options:
        output_format, display = options.split(":", 1)
    else:
        output_format = options
        display = ""

    # Parse versions into list
    if isinstance(versions, str):
        version_list = [v.strip() for v in versions.split(',') if v.strip()]
    else:
        version_list = list(versions)

    series: dict[str, list[float]] = {}
    full_data: dict[str, dict] = {}  # Store full summarized data for JSON output

    default_config = "small-scale-udn-l3.yaml"
    config_value = config_name or default_config
    errors = []
    for ver in version_list:
        result = await run_orion(
            config=ORION_CONFIGS_PATH + config_value,
            version=ver,
            lookback=lookback,
            since=since,
            display=display if display.strip() else None,
        )

        sum_result = await summarize_result(result, isolate=metric)

        # Ensure we have the expected structure before indexing
        if not isinstance(sum_result, dict) or metric not in sum_result:
            errors.append(f"No data for version {ver}: {sum_result}")
            continue

        raw_values = sum_result[metric].get("value", [])  # type: ignore[assignment]
        if not isinstance(raw_values, list):
            errors.append(f"Unexpected data format for version {ver}")
            continue

        # Remove None values to keep the plot continuous
        values = [v for v in raw_values if v is not None]
        if not values:
            errors.append(f"All values are None for version {ver}")
            continue

        series[ver] = values
        full_data[ver] = sum_result  # Store full data for JSON output
        print(f"series: {series}")

    if errors and not series:
        return types.TextContent(type="text", text="\n".join(errors))

    # Handle different output formats
    if output_format.lower() == "json":
        # Return JSON data
        json_output = {
            "config": config_value,
            "metric": metric,
            "lookback": lookback,
            "display": display if display.strip() else None,
            "data": full_data
        }
        return types.TextContent(type="text", text=json.dumps(json_output, indent=2))

    if output_format.lower() == "both":
        # Return both JSON and image info
        json_output = {
            "config": config_value,
            "metric": metric,
            "lookback": lookback,
            "display": display if display.strip() else None,
            "data": full_data,
            "plot_info": "Image data follows JSON data"
        }
        try:
            img_b64 = generate_multi_line_plot(series, metric, title_prefix=f"{config_value}: ")
            combined_output = json.dumps(json_output, indent=2) + "\n\n[IMAGE_DATA_BASE64]\n" + img_b64.decode("utf-8")
            return types.TextContent(type="text", text=combined_output)
        except ValueError as e:
            return types.TextContent(type="text", text=f"Error generating plot: {str(e)}\n\nJSON data:\n{json.dumps(json_output, indent=2)}")

    else:
        # Default: return image
        try:
            img_b64 = generate_multi_line_plot(series, metric, title_prefix=f"{config_value}: ")
            return types.ImageContent(type="image", data=img_b64.decode("utf-8"), mimeType="image/jpeg")
        except ValueError as e:
            return types.TextContent(type="text", text=str(e))


@mcp.tool()
async def get_orion_performance_data(
    config_name: Annotated[
        str | None,
        Field(
            description="Orion configuration file name (e.g. 'small-scale-udn-l3.yaml')"
        ),
    ] = None,
    *,
    metric: Annotated[str, Field(description="Metric to analyze")] = "podReadyLatency_P99",
    version: Annotated[str, Field(description="OpenShift version to analyze")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    since: Annotated[str | None, Field(description="Date to begin looking back for performance data")] = None,
    ctx: Context = None,
) -> dict:
    """Return performance data values for a specific config/metric/version.

    Returns:
        Dict with config, metric, version, lookback, values, count.
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

    default_config = "small-scale-udn-l3.yaml"
    config_value = config_name or default_config
    try:
        result = await run_orion(
            config=ORION_CONFIGS_PATH + config_value,
            version=version,
            lookback=lookback,
            since=since,
        )
        sum_result = await summarize_result(result, isolate=metric)

        if not isinstance(sum_result, dict) or metric not in sum_result:
            return {"error": f"No data found for metric {metric}"}

        metric_data = sum_result[metric]
        values = metric_data.get("value", [])
        if not isinstance(values, list):
            return {"error": f"Unexpected data format for metric {metric}"}

        values = [v for v in values if v is not None]
        return {
            "config": config_value,
            "metric": metric,
            "version": version,
            "lookback": lookback,
            "values": values,
            "count": len(values),
        }
    except Exception as e:
        return {"error": str(e)}

def _add_percentage_changes(pulls_list: list[dict], periodic_avg: dict) -> None:
    """Calculate and set percentage_change on each metric in pull data."""
    for pull_obj in pulls_list:
        for pull_entry in pull_obj.get("data", []):
            for metric_name, metric_data in pull_entry.get("metrics", {}).items():
                if metric_name not in periodic_avg:
                    periodic_value = None
                else:
                    periodic_data = periodic_avg[metric_name]
                    if isinstance(periodic_data, dict):
                        periodic_value = periodic_data.get("value")
                    else:
                        periodic_value = periodic_data

                pull_value = metric_data.get("value")
                if (
                    isinstance(periodic_value, (int, float))
                    and isinstance(pull_value, (int, float))
                    and periodic_value != 0
                ):
                    metric_data["percentage_change"] = ((pull_value - periodic_value) / periodic_value) * 100
                else:
                    metric_data["percentage_change"] = None


async def get_pr_details(
    organization: str,
    repository: str,
    pull_requests: list[str],
    version: str = "4.20",
    lookback: str = "15",
) -> list[dict]:
    """
    Get PR performance analysis details by running Orion with input variables.

    Args:
        organization: GitHub organization name
        repository: Repository name
        pull_requests: List of pull request numbers to analyze
        version: OpenShift version to analyze
        lookback: Days to look back for data

    Returns:
        List of dictionaries containing PR analysis results for each config.
        Each dictionary contains the config, periodic_avg, and pulls.
        periodic_avg is the average of the periodic metrics for the version.
        pulls is a list of {pr, data} objects with results for each PR.
        The LLM should compare the periodic_avg to the pull metrics and determine if the PR introduces a performance regression.
        The LLM should use a 10% threshold to determine if the PR introduces a performance regression.
    """

    configs = [
        "trt-external-payload-cluster-density.yaml",
        "trt-external-payload-node-density.yaml",
        "trt-external-payload-node-density-cni.yaml",
        "trt-external-payload-crd-scale.yaml",
    ]

    if not pull_requests:
        raise ValueError("At least one pull request number is required")
    try:
        pull_numbers = [int(pr) for pr in pull_requests]
    except ValueError as exc:
        raise ValueError("Pull request numbers must be integers") from exc

    input_vars = {
        "jobtype": "pull",
        "organization": organization,
        "repository": repository,
        "pull_number": pull_requests[0],
        "version": version
    }

    full_config_paths = [os.path.join(ORION_CONFIGS_PATH, config) for config in configs]
    summaries: list[dict] = []

    for full_config_path in full_config_paths:
        result = await run_orion(
            config=full_config_path,
            version=version,
            lookback=lookback,
            input_vars=input_vars,
            pr_analysis=True,
            pull_numbers=pull_numbers,
        )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"Failed to parse orion output for {full_config_path}: {e}")
            continue

        if not isinstance(data, dict):
            print(f"Unexpected data type from orion for {full_config_path}: {type(data)}")
            continue

        if "periodic_avg" not in data:
            print(f"Missing periodic_avg in orion output for {full_config_path}")
            continue

        periodic_avg = data["periodic_avg"]

        if "pulls" not in data:
            print(f"Missing pulls in orion output for {full_config_path}")
            continue

        pulls_list = data["pulls"]
        _add_percentage_changes(pulls_list, periodic_avg)

        summaries.append({
            "config": full_config_path,
            "periodic_avg": periodic_avg,
            "pulls": pulls_list,
        })

    return summaries

@mcp.tool()
async def openshift_report_on_pr(
    version: Annotated[str, Field(description="OpenShift version to analyze")] = "4.20",
    *,
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    organization: Annotated[str, Field(description="Organization to look into")] = "openshift",
    repository: Annotated[str, Field(description="Repository to look into")] = "ovn-kubernetes",
    pull_request: Annotated[str, Field(description="PR number to analyze (for single PR)")] = "2841",
    pull_requests: Annotated[str, Field(description="Comma-separated PR numbers to compare (e.g. '3169,3170'). Overrides pull_request if provided.")] = "",
    ctx: Context = None,
) -> dict:
    """
    Captures a performance analysis against the specified OpenShift version using Orion.

    Args:
        version: OpenShift version to analyze.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        organization: The organization to look into. Defaults to openshift.
        repository: The repository to look into. Defaults to ovn-kubernetes.
        pull_request: Single PR number to analyze. Defaults to 2841.
        pull_requests: Comma-separated PR numbers for multi-PR comparison (e.g. '3169,3170').
            When provided, overrides pull_request.
        ctx: MCP context for accessing request headers

    Returns:
        Dictionary with summaries containing PR analysis results for each config.
    """
    _extract_and_set_es_server(ctx)

    if pull_requests and pull_requests.strip():
        pr_list = [pr.strip() for pr in pull_requests.split(",") if pr.strip()]
    else:
        pr_list = [pull_request]

    summaries = await get_pr_details(organization, repository, pr_list, version, lookback)
    if not summaries:
        return {
            "summaries": [],
            "message": "No performance data found for this PR. Please ensure the PR has been tested and the version is correct."
        }
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

    Args:
        configs: List of Orion config filenames
        version: OpenShift version
        lookback: Days to look back
    """
    full_config_paths = [os.path.join(ORION_CONFIGS_PATH, config) for config in configs]
    changepoints: list[str] = []

    for full_config_path in full_config_paths:
        result = await run_orion(
            config=full_config_path,
            version=version,
            lookback=lookback,
            jira_ack=True,
            jira_status_filter="Done",
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
    ctx: Context = None,
) -> str:
    """
    Runs a performance regression analysis against the OpenShift version using Orion.

    Orion uses an EDivisive algorithm to analyze performance data from a specified
    configuration file to detect any performance regressions.

    Args:
        version: Openshift version to look into.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        ctx: MCP context for accessing request headers

    Returns:
        Returns string stating if there is a regression and in which config it was found.
                       If no regressions are found, returns "No regressions found".
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

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
    ctx: Context = None,
) -> str:
    """
    Runs a performance regression analysis against networking-focused configs.

    Checks only the following Orion configurations:
      - small-scale-udn-l3.yaml
      - trt-external-payload-node-density-cni.yaml

    Args:
        version: Openshift version to look into.
        lookback: The number of days to look back for performance data. Defaults to 15 days.
        ctx: MCP context for accessing request headers
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

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
    *,
    config_name: Annotated[
        str | None,
        Field(
            description="Orion configuration file name (e.g. 'trt-external-payload-cluster-density.yaml')"
        ),
    ] = None,
    since: Annotated[str, Field(description="Date to begin looking back for performance data")] = None,
    version: Annotated[str, Field(description="Version of OpenShift to look into")] = "4.19",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "15",
    ctx: Context = None,
) -> types.ImageContent | types.TextContent:
    """
    Calculate and visualise the correlation between two metrics for a given
    Orion configuration.

    A scatter-plot annotated with the Pearson correlation coefficient is
    returned. If either metric is missing from the Orion results the function
    falls back to returning a textual error message.
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

    default_config = "trt-external-payload-cluster-density.yaml"
    config_value = config_name or default_config

    # Run Orion to gather data
    result = await run_orion(
        config=ORION_CONFIGS_PATH + config_value,
        version=version,
        lookback=lookback,
        since=since,
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
    corr_b64 = generate_correlation_plot(values1, values2, metric1, metric2, title_prefix=f"{config_value}: ")

    return types.ImageContent(type="image", data=corr_b64.decode("utf-8"), mimeType="image/jpeg")


@mcp.tool()
async def has_nightly_regressed(
    nightly_version: Annotated[str, Field(description="Full nightly version string (e.g., '4.22.0-0.nightly-2026-01-05-203335')")],
    previous_nightly: Annotated[str, Field(description="Optional previous nightly to compare against (e.g., '4.22.0-0.nightly-2026-01-01-123456')")] = "",
    lookback: Annotated[str, Field(description="Number of days to lookback")] = "30",
    configs: Annotated[str, Field(description="Comma-separated list of config files (optional, defaults to TRT configs)")] = "",
    ctx: Context = None,
) -> str:
    """
    Detect regressions for a specific OpenShift nightly version.

    Parses the nightly version to extract major version and date, queries Orion,
    filters data to the nightly date, and reports any changepoints found.

    If previous_nightly is specified, only looks for regressions between the two nightlies.

    Args:
        nightly_version: Full nightly version string (e.g., '4.22.0-0.nightly-2026-01-05-203335').
        previous_nightly: Optional previous nightly to compare against. If specified, only data
                          between previous_nightly and nightly_version dates is analyzed.
        lookback: Days to look back for data. Defaults to 30.
        configs: Comma-separated list of config files. Defaults to TRT configs.
        ctx: MCP context for accessing request headers

    Returns:
        String with regression details or "No regressions found".
    """
    # Extract and set ES_SERVER from request headers if present
    _extract_and_set_es_server(ctx)

    # Parse the nightly version
    try:
        nightly_info = parse_nightly_version(nightly_version)
    except ValueError as e:
        return f"Error parsing nightly version: {e}"

    if not nightly_info.is_nightly:
        return f"Error: '{nightly_version}' is not a nightly version."

    # Parse previous_nightly if specified
    prev_nightly_info = None
    if previous_nightly.strip():
        try:
            prev_nightly_info = parse_nightly_version(previous_nightly)
        except ValueError as e:
            return f"Error parsing previous_nightly: {e}"
        if not prev_nightly_info.is_nightly:
            return f"Error: '{previous_nightly}' is not a nightly version."
        if prev_nightly_info.nightly_date >= nightly_info.nightly_date:
            return "Error: previous_nightly must be earlier than nightly_version."

    # Use default TRT configs if none specified
    config_list = ([c.strip() for c in configs.split(",") if c.strip()] if configs.strip() else [
        "trt-external-payload-cluster-density.yaml",
        "trt-external-payload-node-density.yaml",
        "trt-external-payload-node-density-cni.yaml",
        "trt-external-payload-crd-scale.yaml",
    ])

    all_regressions: list[str] = []

    for config in config_list:
        full_config_path = os.path.join(ORION_CONFIGS_PATH, config)
        result = await run_orion(
            config=full_config_path,
            version=nightly_info.major_version,
            lookback=lookback,
            jira_ack=True,
            jira_status_filter="Done",
        )

        try:
            data = json.loads(result.stdout)
            if not isinstance(data, list):
                continue
            # Filter to entries on or before nightly date
            data = filter_data_by_timestamp(data, nightly_info.nightly_date)
            # If previous_nightly specified, also filter out entries before that date
            if prev_nightly_info:
                data = [e for e in data if e.get("timestamp") and _timestamp_after(e["timestamp"], prev_nightly_info.nightly_date)]
        except (json.JSONDecodeError, TypeError):
            continue

        # Find changepoints and format output
        for idx, entry in enumerate(data):
            if not entry.get("is_changepoint"):
                continue

            # Build metric changes
            metrics = []
            for name, info in entry.get("metrics", {}).items():
                pct = info.get("percentage_change", 0)
                if pct != 0:
                    metrics.append(f"{name} {'increased' if pct > 0 else 'decreased'} by {abs(pct):.2f}%")

            prev = data[idx - 1] if idx > 0 else {}
            prs_added = [p for p in (entry.get("prs") or []) if p not in (prev.get("prs") or [])]

            lines = [
                f"⚠️ Regression in {nightly_info.full_version}",
                f"Config: {config}",
                f"UUID: {entry.get('uuid')}",
                f"Version: {entry.get('ocpVersion')} (prev: {prev.get('ocpVersion', 'N/A')})",
            ]
            if prev_nightly_info:
                lines.insert(1, f"Comparing against: {prev_nightly_info.full_version}")
            if prs_added:
                lines.append(f"PRs: {', '.join(prs_added)}")
            if metrics:
                lines.append(f"Metrics: {'; '.join(metrics)}")

            all_regressions.append("\n".join(lines))

    return "\n\n".join(all_regressions) if all_regressions else "No regressions found"


def _timestamp_after(timestamp_val, cutoff_datetime: datetime) -> bool:
    """Check if a timestamp is after (not on or before) the cutoff datetime."""
    entry_dt = parse_timestamp(timestamp_val)
    return entry_dt is not None and entry_dt > cutoff_datetime


def main():
    """Main function to run the MCP server."""
    # (No operation)


def _metric_key(metric: dict) -> str:
    name = metric.get("name", "unknown")
    if "agg" in metric and isinstance(metric["agg"], dict):
        agg_type = metric["agg"].get("agg_type", "")
        if agg_type:
            return f"{name}_{agg_type}"
    metric_of_interest = metric.get("metric_of_interest", "value")
    return f"{name}_{metric_of_interest}"


def _render_config_yaml(config_path: str, version: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as template_file:
        template_content = template_file.read()

    env_vars = {k.lower(): v for k, v in os.environ.items()}
    env_vars.update(
        {
            "version": version,
            "jobtype": "periodic",
            "pull_number": 0,
            "organization": "",
            "repository": "",
        }
    )

    try:
        template = jinja2.Template(template_content, undefined=jinja2.StrictUndefined)
        rendered = template.render(env_vars)
    except jinja2.exceptions.UndefinedError:
        template = jinja2.Template(template_content)
        rendered = template.render(env_vars)

    return yaml.safe_load(rendered)


def _load_config_metrics_with_meta(config_path: str, version: str) -> tuple[list[str], dict]:
    rendered_config = _render_config_yaml(config_path, version)
    metrics_list: list[str] = []
    meta_map: dict = {}

    for test in rendered_config.get("tests", []):
        for metric in test.get("metrics", []):
            key = _metric_key(metric)
            metrics_list.append(key)
            direction_raw = metric.get("direction")
            threshold_raw = metric.get("threshold")
            try:
                direction_val = (
                    int(direction_raw) if direction_raw is not None else None
                )
            except (TypeError, ValueError):
                direction_val = None
            try:
                threshold_val = (
                    float(threshold_raw) if threshold_raw is not None else None
                )
            except (TypeError, ValueError):
                threshold_val = None
            meta_map[key] = {
                "direction": direction_val,
                "threshold": threshold_val,
                "metric_of_interest": metric.get("metric_of_interest"),
                "agg_type": metric.get("agg", {}).get("agg_type") if isinstance(metric.get("agg"), dict) else None,
            }

    return metrics_list, meta_map


if __name__ == "__main__":
    if os.getenv("ES_SERVER") is None:
        print("ES_SERVER environment variable is not set")
        import sys
        sys.exit(1)
    TRANSPORT = "streamable-http"
    asyncio.run(mcp.run(transport=TRANSPORT))
    print("Running MCP server with transport:", TRANSPORT)

