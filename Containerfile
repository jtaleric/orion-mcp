FROM python:3.11.8-slim-bookworm
# So that STDOUT/STDERR is printed
ENV PYTHONUNBUFFERED="1"

# First let's just get things updated.
# Install System dependencies
RUN apt-get update --assume-yes && \
    apt-get install -o 'Dpkg::Options::=--force-confnew' -y --force-yes -q \
    git \
    openssh-client \
    gcc \
    clang \
    build-essential \
    make \
    curl \
    virtualenv \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="~/bin:$PATH"

# Create base directory structure
RUN mkdir -p /app/orion /app/orion-mcp

# Clone Orion repository
RUN git clone --depth 1 --branch v0.1.5 http://github.com/cloud-bulldozer/orion /app/orion-repo

# Create virtual environment for Orion
RUN python -m venv /app/orion-venv
ENV ORION_VENV="/app/orion-venv"

# Install Orion in its virtual environment
WORKDIR /app/orion-repo
RUN /app/orion-venv/bin/pip install --upgrade pip setuptools && \
    /app/orion-venv/bin/pip install -r requirements.txt && \
    /app/orion-venv/bin/pip install .

# Create symlink for orion command
RUN ln -sf /app/orion-venv/bin/orion /usr/local/bin/orion

# Create virtual environment for orion-mcp
RUN python -m venv /app/orion-mcp-venv
ENV ORION_MCP_VENV="/app/orion-mcp-venv"

# Copy only requirements.txt first to leverage layers cache
COPY requirements.txt /app/orion-mcp/requirements.txt

# Install orion-mcp dependencies in its virtual environment
WORKDIR /app/orion-mcp
RUN /app/orion-mcp-venv/bin/pip install --upgrade pip && \
    /app/orion-mcp-venv/bin/pip install -r requirements.txt

# Copy orion-mcp source code
COPY . /app/orion-mcp/

# Create /orion/examples directory and copy examples from the cloned orion repo
RUN mkdir -p /orion && cp -r /app/orion-repo/examples /orion/examples

# Create a wrapper script to run orion-mcp with its virtual environment
RUN echo '#!/bin/bash\n/app/orion-mcp-venv/bin/python /app/orion-mcp/orion_mcp.py "$@"' > /usr/local/bin/orion-mcp && \
    chmod +x /usr/local/bin/orion-mcp

WORKDIR /app/orion-mcp

# Use the orion-mcp virtual environment by default
ENV PATH="/app/orion-mcp-venv/bin:$PATH"

CMD ["/app/orion-mcp-venv/bin/python", "orion_mcp.py"]
