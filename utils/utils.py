"""
Utility functions for the orion-mcp server.

This module contains helper functions for running Orion analysis,
converting data formats, and generating visualizations.
"""

import base64
import io
import os
import subprocess
import json
import shutil
import asyncio
import matplotlib.pyplot as plt


async def run_command_async(command: list[str] | str, env: dict = None, shell: bool = False) -> subprocess.CompletedProcess:
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
            "cmd",
            "--lookback", f"{lookback}d",
            "--hunter-analyze",
            "--config", config,
            "-o", "json"
        ]
    else:
        print("Using orion from path")
        command = [
            "orion",
            "cmd",
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
    return result


def convert_results_to_csv(results: list) -> str:
    """
    Convert the results of the Orion analysis into a CSV format.

    Args:
        results: The list of results from the Orion analysis.

    Returns:
        A string containing the CSV representation of the results.
    """
    csv_lines = []
    for result in results:
        for config, data in result.items():
            if not data:
                continue
            for metric, values in data.items():
                if metric == "timestamp":
                    continue
                csv_lines.append(f"{config},{metric},{','.join(map(str, values['value']))}")
    return "\n".join(csv_lines)


async def csv_to_graph(csv_data: str) -> list[bytes]:
    """
    Convert CSV data into a graph representation.

    Args:
        csv_data: The CSV data to convert.

    Returns:
        List of base64 encoded graph images.
    """

    # Dictionary to store parsed data:
    # Key: (file_path, metric_name) tuple
    # Value: List of numerical data points
    parsed_metrics_data = {}

    # Group the data by workload and metric
    grouped_data = {}
    for line in csv_data.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.strip().split(',')
        if len(parts) < 3:
            continue
        file_path = parts[0]
        metric_name = parts[1]
        value = parts[2:]

        if file_path not in grouped_data:
            grouped_data[file_path] = {}
        if metric_name not in grouped_data[file_path]:
            grouped_data[file_path][metric_name] = value

    # Split the input string into individual lines
    lines = csv_data.strip().split('\n')

    for line_num, line in enumerate(lines):
        if not line.strip():  # Skip empty lines
            continue

        parts = line.strip().split(',')
        if len(parts) < 3:  # Ensure at least path, metric_name, and one value
            print(f"Warning: Skipping malformed line {line_num + 1}: '{line}'. "
                  f"Expected at least 3 comma-separated parts.")
            continue

        file_path = parts[0]
        metric_name = parts[1]
        raw_values = parts[2:]

        # Convert raw_values to floats, handling 'None' values
        numerical_values = []
        for val_str in raw_values:
            try:
                # Convert 'None' string to actual None, then filter out
                numerical_values.append(float(val_str) if val_str.lower() != 'none' else None)
            except ValueError:
                print(f"Warning: Could not convert '{val_str}' to a number in line {line_num + 1}. "
                      f"Skipping this value.")
                numerical_values.append(None)

        # Filter out actual None values from the list before storing
        numerical_values = [val for val in numerical_values if val is not None]

        if not numerical_values:
            print(f"Warning: No valid numerical data found for metric '{metric_name}' "
                  f"in '{file_path}'. Skipping plot for this entry.")
            continue

        # Store the data using a tuple as key for unique identification
        key = (file_path, metric_name)
        parsed_metrics_data[key] = numerical_values

    if not parsed_metrics_data:
        print("No valid metric data found to generate graphs.")
        return []

    imgs = []

    # Generate a line graph for each metric entry
    for (file_path, metric_name), values in parsed_metrics_data.items():
        plt.figure(figsize=(12, 7))  # Set a good figure size
        # The X-axis will just be the index of the measurement
        plt.plot(range(len(values)), values, marker='o', linestyle='-', color='skyblue', linewidth=2)

        # Sanitize file_path for use in filename (replace slashes and dots with underscores)
        # and limit length to avoid overly long filenames
        sanitized_file_path = file_path.replace('/', '_').replace('.', '_').strip('_')
        if len(sanitized_file_path) > 50:  # Limit length
            sanitized_file_path = sanitized_file_path[-50:]  # Take last 50 chars

        # Add labels and title
        plt.title(
            f'{metric_name} Values\n(Workload: {file_path})',
            fontsize=16
        )
        plt.xlabel('Measurement Index', fontsize=18)
        plt.ylabel(f'{metric_name} Value', fontsize=18)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tick_params(axis='x', labelsize=12)
        plt.tick_params(axis='y', labelsize=12)
        plt.ylim(min(values)-min(values)*0.1, max(values)+max(values)*0.1)

        # Add a tight layout to prevent labels from overlapping
        plt.tight_layout()

        # Save the plot
        try:
            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            img_data = base64.b64encode(img.read())
            imgs.append(img_data)
        except Exception as e:
            print(f"Error with graph : {e}")
        plt.close()  # Close the figure to free up memory

    # Add a small delay to prevent blocking
    await asyncio.sleep(0.01)
    return imgs


def extract_json_block(log_text: str):
    lines = log_text.strip().splitlines()

    # Exit early if UUID is missing
    for line in lines:
        if "No UUID present for given metadata" in line:
            print("❌ Error: No UUID present for given metadata. Exiting.")
            sys.exit(1)

    # Look for the JSON block start
    json_start_index = None
    for i, line in enumerate(lines):
        if line.strip().startswith("="):
            json_start_index = i + 1
            break

    if json_start_index is None:
        print("❌ Error: JSON delimiter not found. Exiting.")
        sys.exit(1)

    json_text = "\n".join(lines[json_start_index:]).strip()

    if not json_text:
        print("❌ Error: JSON block is empty. Exiting.")
        sys.exit(1)

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Failed to parse JSON: {e}")
        sys.exit(1)

async def summarize_result(result: subprocess.CompletedProcess, isolate: str = None) -> dict | str:
    """
    Summarize the Orion result into a dictionary.

    Args:
        result: The json output from the Orion command.

    Returns:
        A dictionary containing the summary of the Orion analysis.
    """
    summary = {}
    print(result.stdout)
    try:
        extracted_json = extract_json_block(result.stdout)
        if len(extracted_json) == 0:
            return {}
        for run in extracted_json:
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
    return os.environ.get("ES_SERVER") 


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
            lookback="3",
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
    
