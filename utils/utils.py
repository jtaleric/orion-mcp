"""
Utility functions for the orion-mcp server.

This module contains helper functions for running Orion analysis,
converting data formats, and generating visualizations.
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import shutil
import subprocess
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

import matplotlib.pyplot as plt
import numpy as np

# Define ORION_CONFIGS_PATH locally to avoid circular import
ORION_CONFIGS_PATH = "/orion/examples/"

# Context variable for ES config from encrypted request headers
# Provides async-safe isolation between concurrent requests
# Contains: es_server, es_metadata_index (optional), es_benchmark_index (optional)
current_es_config: ContextVar[Optional[dict]] = ContextVar('current_es_config', default=None)

def resolve_env_var(primary_name: str, secondary_name: str, default_value: str) -> str:
    """
    Resolve an environment variable using a preferred name, a case-variant fallback,
    and a default if neither is set to a non-empty value.

    The current behavior prefers the lowercase variable (primary) and then falls
    back to the uppercase variant (secondary) to preserve existing semantics.
    """
    primary_value = os.environ.get(primary_name)
    if primary_value is not None and primary_value.strip() != "":
        return primary_value

    secondary_value = os.environ.get(secondary_name)
    if secondary_value is not None and secondary_value.strip() != "":
        return secondary_value

    return default_value


async def run_command_async(command: list[str] | str, env: Optional[dict] = None, shell: bool = False, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """
    Run a command line tool asynchronously and return a CompletedProcess-like result.
    Args:
        command: List of command arguments or a single string for shell=True.
        env: Optional environment variables to set for the command.
        shell: Whether to use the shell to execute the command.
        cwd: Optional working directory for the command.
    Returns:
        A subprocess.CompletedProcess-like object with args, returncode, stdout, stderr.
    """
    print(f"Running command: {command}")
    if cwd:
        print(f"Working directory: {cwd}")
    if env is not None:
        env_vars = os.environ.copy()
        env_vars.update(env)
    else:
        env_vars = None
    try:
        if shell:
            if not isinstance(command, str):
                raise TypeError("command must be a string when shell=True")
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars,
                cwd=cwd
            )
        else:
            if not isinstance(command, list):
                raise TypeError("command must be a list when shell=False")
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars,
                cwd=cwd
            )
        stdout, stderr = await process.communicate()
        result = subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout=stdout.decode('utf-8'),
            stderr=stderr.decode('utf-8')
        )
        return result
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout='',
            stderr=str(e)
        )

def orion_configs(configs: list[str]) -> list[str]:
    """
    Return the list of Orion config filenames (not full paths).
    """
    return [os.path.basename(cfg) for cfg in configs]

async def run_orion(
    config: str,
    version: str,
    lookback: str,
    *,
    since: str = None,
    input_vars: Optional[dict] = None,
    display: Optional[str] = None,
    pr_analysis: bool = False,
    pull_numbers: Optional[list[int]] = None,
    jira_ack: bool = False,
    jira_status_filter: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """
    Execute Orion to analyze performance data for regressions.

    Args:
        lookback: Days to look back for performance data.
        config: Path to the Orion configuration file to use for analysis.
        version: Version to analyze.
        display: Optional field to display in the output (e.g., "ocpVirtVersion").
        jira_ack: Use JIRA as ACK provider instead of file-based ACKs.
        jira_status_filter: Only treat JIRA issues with this status as ACKs (e.g., "Done").

    Returns:
        The result of the Orion command execution, including stdout and stderr.
    """
    # get_data_source() checks context variable first, then environment variable
    data_source = get_data_source()
    if data_source == "":
        raise ValueError("Data source is not set")

    command = []
    if not shutil.which("orion"):
        print("Using orion from podman")
        command = ["podman", "run", "--env-host",
            "orion",
            "orion",
            "--lookback", f"{lookback}d",
            "--hunter-analyze",
            "--config", config,
            "-o", "json"
        ]
    else:
        print("Using orion from path")
        command = [
            "orion",
            "--lookback", f"{lookback}d",
            "--hunter-analyze",
            "--config", config,
            "-o", "json"
        ]

    if jira_ack:
        command.append("--jira-ack")
    if jira_status_filter:
        command.extend(["--jira-status-filter", jira_status_filter])

    if since is not None:
        command.extend(["--since", since])

    if input_vars is not None:
        command.extend(["--input-vars", json.dumps(input_vars)])

    if display is not None and display.strip():
        command.extend(["--display", display.strip()])

    if pr_analysis:
        command.append("--pr-analysis")

    if pull_numbers:
        for pn in pull_numbers:
            command.extend(["--pull-number", str(pn)])

    # Get indices from context (if present) or environment variables
    es_metadata_index = get_es_metadata_index()
    es_benchmark_index = get_es_benchmark_index()

    env = {
        "ES_SERVER": data_source,
        "version": version,
        "es_metadata_index": es_metadata_index,
        "es_benchmark_index": es_benchmark_index,
    }

    # Log env
    print(f"Env: version={version}, es_metadata_index={es_metadata_index}, es_benchmark_index={es_benchmark_index}")
    result = await run_command_async(command, env=env, cwd="/tmp")
    # Log the full result for debugging
    print(f"Orion return code: {result.returncode}")
    print(f"Orion stdout: {result.stdout}")
    print(f"Orion stderr: {result.stderr}")
    return result


async def summarize_result(result: subprocess.CompletedProcess, isolate: Optional[str] = None) -> dict | str:
    """
    Summarize the Orion result into a dictionary.

    Args:
        result: The json output from the Orion command.
        isolate: Optional metric name to isolate for backwards compatibility.

    Returns:
        A dictionary containing the summary of the Orion analysis with full run data preserved.
    """
    summary = {}
    try:
        if result.returncode == 3:
            return {}

        data = json.loads(result.stdout)
        if len(data) == 0:
            return {}

        # Store all runs with full data
        summary["runs"] = data

        # For backwards compatibility, also provide metric-focused summary
        for run in data:
            for metric_name, metric_data in run["metrics"].items():
                summary["timestamp"] = run["timestamp"]
                # Isolate specific metric if specified
                if isolate is not None:
                    if isolate != metric_name:
                        print(f"Skipping {metric_name} because it doesn't contain {isolate}")
                        continue
                if metric_name not in summary:
                    summary[metric_name] = {}
                    summary[metric_name] = {
                        "value": [metric_data["value"]],
                    }
                else:
                    summary[metric_name]["value"].append(metric_data["value"])
    except Exception as e:
        return f"Error : {e}"
    return summary


def get_data_source() -> str:
    """
    Provide the data source URL for Orion analysis.

    Checks ES_SERVER in this order:
    1. Context variable (from encrypted request header)
    2. Environment variable (fallback)

    Returns:
        The OpenSearch URL as a string.
    """
    # Check context variable first (set from encrypted header)
    es_config = current_es_config.get()
    if es_config and "es_server" in es_config:
        print("Using ES_SERVER from encrypted request header")
        return es_config["es_server"]

    # Fall back to environment variable
    value = os.environ.get("ES_SERVER")
    if value is None:
        raise EnvironmentError("ES_SERVER environment variable is not set")
    print("Using ES_SERVER from environment variable")
    return value


def get_es_metadata_index() -> str:
    """
    Get es_metadata_index from context or environment with fallback.

    Checks in this order:
    1. Context variable (from encrypted request header)
    2. Environment variables (es_metadata_index or ES_METADATA_INDEX)
    3. Default: "perf_scale_ci*"

    Returns:
        The metadata index pattern as a string.
    """
    # Check context variable first
    es_config = current_es_config.get()
    if es_config and "es_metadata_index" in es_config:
        print("Using es_metadata_index from encrypted request header")
        return es_config["es_metadata_index"]

    # Fall back to environment variable
    print("Using es_metadata_index from environment/default")
    return resolve_env_var("es_metadata_index", "ES_METADATA_INDEX", "perf_scale_ci*")


def get_es_benchmark_index() -> str:
    """
    Get es_benchmark_index from context or environment with fallback.

    Checks in this order:
    1. Context variable (from encrypted request header)
    2. Environment variables (es_benchmark_index or ES_BENCHMARK_INDEX)
    3. Default: "ripsaw-kube-burner-*"

    Returns:
        The benchmark index pattern as a string.
    """
    # Check context variable first
    es_config = current_es_config.get()
    if es_config and "es_benchmark_index" in es_config:
        print("Using es_benchmark_index from encrypted request header")
        return es_config["es_benchmark_index"]

    # Fall back to environment variable
    print("Using es_benchmark_index from environment/default")
    return resolve_env_var("es_benchmark_index", "ES_BENCHMARK_INDEX", "ripsaw-kube-burner-*")


async def orion_metrics(config_list: list, version: str = "4.20") -> dict | str:
    """
    Provide the metrics for Orion analysis.
    Args:
        config_list: List of Orion configuration files.
    Returns:
        A dictionary containing the metrics for Orion analysis.
        the key is the config the metric is associated with
        the value is a list of all the metric names that are available for that config
    """
    metrics = {} 
    for config in config_list:
        result = await run_orion(
            config=config,
            version=version,
            lookback="15"
        )
        try:
            sum_result = await summarize_result(result)
            print(f"Sum result: {sum_result}")
            if isinstance(sum_result, dict):
                # Exclude helper keys so callers do not mistake metadata fields like runs/timestamp for queryable metrics.
                metrics[config] = [
                    key for key in sum_result.keys() if key not in {"runs", "timestamp"}
                ]
            else:
                return f"Error processing result for {config}: {sum_result}"
        except (KeyError, ValueError, TypeError) as e:
            return f"Error processing result for {config}: {e}"

    return metrics 
    

# Correlation helper functions

def compute_correlation(values1: list[float], values2: list[float]) -> float:
    """
    Compute the Pearson correlation coefficient between two numeric lists.

    Args:
        values1: First list of numeric values.
        values2: Second list of numeric values.

    Returns:
        The Pearson correlation coefficient. Returns ``float('nan')`` if the
        lists are of unequal length, contain fewer than two items, or if
        either array has zero variance (all identical values).
    """
    if len(values1) != len(values2) or len(values1) < 2:
        return float("nan")

    # Check for zero variance (all identical values)
    if np.var(values1) == 0 or np.var(values2) == 0:
        return float("nan")

    # Use NumPy for a robust computation
    return float(np.corrcoef(values1, values2)[0, 1])


GITHUB_CONFIGS_URL = "https://api.github.com/repos/cloud-bulldozer/orion/contents/examples"

logger = logging.getLogger(__name__)


def list_orion_configs() -> list[str]:
    """
    List the Orion configuration files.

    Tries in order:
    1. GitHub API (cloud-bulldozer/orion examples directory)
    2. Local /orion/examples/ directory
    """
    try:
        resp = httpx.get(GITHUB_CONFIGS_URL, timeout=10)
        resp.raise_for_status()
        configs = [
            item["name"]
            for item in resp.json()
            if item["type"] == "file" and item["name"].endswith(".yaml")
        ]
        if configs:
            return configs
    except Exception as e:
        logger.warning("Failed to fetch configs from GitHub: %s", e)

    try:
        return [f for f in os.listdir(ORION_CONFIGS_PATH) if f.endswith(".yaml")]
    except (FileNotFoundError, OSError):
        return []

def generate_correlation_plot(
    values1: list[float],
    values2: list[float],
    metric1: str,
    metric2: str,
    title_prefix: str = "",
) -> bytes:
    """
    Create a scatter-plot that visualises the relationship between two metrics
    and return it as a base64-encoded PNG image.

    Args:
        values1: Values for ``metric1`` placed on the Y-axis.
        values2: Values for ``metric2`` placed on the X-axis.
        metric1: Name of the first metric.
        metric2: Name of the second metric.
        title_prefix: Optional string to prepend to the plot title.

    Returns:
        Base64-encoded PNG bytes.
    """

    corr = compute_correlation(values1, values2)

    plt.figure(figsize=(8, 6))
    plt.scatter(values2, values1, alpha=0.7, color="steelblue")
    plt.title(f"{title_prefix}Correlation between {metric1} and {metric2}\nPearson r = {corr:.3f}")
    plt.xlabel(metric2)
    plt.ylabel(metric1)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    plt.close()
    buffer.seek(0)
    return base64.b64encode(buffer.read())
 
# Multi-line plot helper
def generate_multi_line_plot(
    series_dict: dict[str, list[float]],
    metric: str,
    title_prefix: str = "",
) -> bytes:
    """Generate a multi-line plot where each key in *series_dict* becomes a
    separate line.

    Args:
        series_dict: Mapping of *label* → list of numeric values.
        metric: Metric name (used for y-axis label/title).
        title_prefix: Optional string placed before the title.

    Returns:
        Base64-encoded PNG image bytes.
    """

    if not series_dict:
        raise ValueError("series_dict is empty—nothing to plot")

    plt.figure(figsize=(12, 7))
    cmap = plt.colormaps["tab10"]
    color_cycle = [cmap(i) for i in range(cmap.N)]  # list of RGBA tuples

    for idx, (label, values) in enumerate(series_dict.items()):
        if not values:
            continue
        plt.plot(
            range(len(values)),
            values,
            marker="o",
            linestyle="-",
            color=color_cycle[idx % len(color_cycle)],
            label=label,
        )

    plt.title(f"{title_prefix}{metric} over time", fontsize=16)
    plt.xlabel("Measurement Index", fontsize=14)
    plt.ylabel(metric, fontsize=14)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read())


# Nightly version parsing utilities

@dataclass
class NightlyVersionInfo:
    """Information parsed from a nightly or GA version string."""
    full_version: str           # "4.18.0-0.nightly-2025-01-15-203335" or "4.18"
    major_version: str          # "4.18"
    nightly_date: Optional[datetime]  # datetime(2025, 1, 15, 20, 33, 35) for nightlies, None for GA
    is_nightly: bool            # True for nightlies, False for GA


def parse_nightly_version(version_string: str) -> NightlyVersionInfo:
    """
    Parse a nightly or GA version string into structured information.

    Nightly format: X.Y.Z-0.nightly-YYYY-MM-DD-HHMMSS (e.g., 4.18.0-0.nightly-2025-01-15-203335)
    GA format: X.Y or X.Y.Z (e.g., 4.17 or 4.17.0)

    Args:
        version_string: The version string to parse.

    Returns:
        NightlyVersionInfo with parsed details.

    Raises:
        ValueError: If the version string format is invalid.
    """
    version_string = version_string.strip()

    # Try to match nightly format: X.Y.Z-0.nightly-YYYY-MM-DD-HHMMSS
    nightly_pattern = r'^(\d+)\.(\d+)\.(\d+)-0\.nightly-(\d{4})-(\d{2})-(\d{2})-(\d{6})$'
    nightly_match = re.match(nightly_pattern, version_string)

    if nightly_match:
        major = nightly_match.group(1)
        minor = nightly_match.group(2)
        year = int(nightly_match.group(4))
        month = int(nightly_match.group(5))
        day = int(nightly_match.group(6))
        time_str = nightly_match.group(7)  # HHMMSS format
        hour = int(time_str[0:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6])

        return NightlyVersionInfo(
            full_version=version_string,
            major_version=f"{major}.{minor}",
            nightly_date=datetime(year, month, day, hour, minute, second),
            is_nightly=True,
        )

    # Try to match GA format: X.Y or X.Y.Z
    ga_pattern = r'^(\d+)\.(\d+)(?:\.(\d+))?$'
    ga_match = re.match(ga_pattern, version_string)

    if ga_match:
        major = ga_match.group(1)
        minor = ga_match.group(2)

        return NightlyVersionInfo(
            full_version=version_string,
            major_version=f"{major}.{minor}",
            nightly_date=None,
            is_nightly=False,
        )

    raise ValueError(
        f"Invalid version format: '{version_string}'. "
        "Expected nightly format (e.g., '4.18.0-0.nightly-2025-01-15-123456') "
        "or GA format (e.g., '4.17' or '4.17.0')."
    )


def parse_timestamp(timestamp_val) -> Optional[datetime]:
    """
    Parse a timestamp value into a datetime object.

    Args:
        timestamp_val: Unix timestamp (int/float), ISO string, or numeric string.

    Returns:
        Parsed datetime, or None if unparseable.
    """
    try:
        if isinstance(timestamp_val, (int, float)):
            return datetime.fromtimestamp(timestamp_val)
        if isinstance(timestamp_val, str):
            try:
                return datetime.fromtimestamp(float(timestamp_val))
            except ValueError:
                ts_clean = timestamp_val.replace("Z", "").split("+")[0].split(".")[0]
                return datetime.fromisoformat(ts_clean)
    except (ValueError, TypeError, OSError):
        pass
    return None


def filter_data_by_timestamp(data: list[dict], cutoff_datetime: datetime) -> list[dict]:
    """
    Filter Orion results to only include entries on or before the cutoff datetime.

    Args:
        data: List of Orion run dictionaries, each containing a 'timestamp' field.
        cutoff_datetime: The cutoff datetime; entries after this are excluded.

    Returns:
        Filtered list containing only entries with timestamps on or before cutoff_datetime.
    """
    filtered = []
    for entry in data:
        entry_dt = parse_timestamp(entry.get("timestamp"))
        if entry_dt and entry_dt <= cutoff_datetime:
            filtered.append(entry)
    return filtered
    
