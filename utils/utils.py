"""
Utility functions for the orion-mcp server.

This module contains helper functions for running Orion analysis,
converting data formats, and generating visualizations.
"""

import asyncio
import base64
import io
import json
import os
import shutil
import subprocess
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

# Define ORION_CONFIGS_PATH locally to avoid circular import
ORION_CONFIGS_PATH = "/orion/examples/"


async def run_command_async(command: list[str] | str, env: Optional[dict] = None, shell: bool = False) -> subprocess.CompletedProcess:
    """
    Run a command line tool asynchronously and return a CompletedProcess-like result.
    Args:
        command: List of command arguments or a single string for shell=True.
        env: Optional environment variables to set for the command.
        shell: Whether to use the shell to execute the command.
    Returns:
        A subprocess.CompletedProcess-like object with args, returncode, stdout, stderr.
    """
    print(f"Running command: {command}")
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
                env=env_vars
            )
        else:
            if not isinstance(command, list):
                raise TypeError("command must be a list when shell=False")
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars
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
    lookback: str,
    config: str,
    data_source: str,
    version: str,
) -> subprocess.CompletedProcess:
    """
    Execute Orion to analyze performance data for regressions.

    Args:
        lookback: Days to look back for performance data.
        config: Path to the Orion configuration file to use for analysis.
        data_source: Location of the data (OpenSearch URL) to analyze.
        version: Version to analyze.

    Returns:
        The result of the Orion command execution, including stdout and stderr.
    """
    if data_source == "":
        raise ValueError("Data source is not set")
    command = []
    if not shutil.which("orion"):
        print("Using orion from podman")
        command = [
            "podman",
            "run",
            "--env-host",
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
    env = {
        "ES_SERVER": data_source,
        "version": version,
        "es_metadata_index": "perf_scale_ci*",
        "es_benchmark_index": "ripsaw-kube-burner-*"
    }
    result = await run_command_async(command, env=env)
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

    Returns:
        A dictionary containing the summary of the Orion analysis.
    """
    summary = {}
    try:
        data = json.loads(result.stdout)
        if len(data) == 0:
            return {}
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
    print(summary)
    return summary


def get_data_source() -> str:
    """
    Provide the data source URL for Orion analysis.

    User must launch MCP server with the environment variable ES_SERVER
    set to the OpenSearch URL.

    Returns:
        The OpenSearch URL as a string.
    """
    value = os.environ.get("ES_SERVER")
    if value is None:
        raise EnvironmentError("ES_SERVER environment variable is not set")
    return value


async def orion_metrics(config_list: list) -> dict | str:
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
        metrics[config] = []
        result = await run_orion(
            lookback="15", 
            config=config,
            data_source=get_data_source(),
            version="4.19"
        )
        try:
            sum_result = await summarize_result(result)
            print(f"Sum result: {sum_result}")
            if isinstance(sum_result, dict):
                metrics[config].append(list(sum_result.keys()))
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


def list_orion_configs() -> list[str]:
    """
    List the Orion configuration files in the orion/examples directory.
    """
    return os.listdir(ORION_CONFIGS_PATH)

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
    cmap = plt.cm.get_cmap("tab10")
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
    
