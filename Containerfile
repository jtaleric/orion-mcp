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
    && rm -rf /var/lib/apt/lists/*

ENV PATH="~/bin:$PATH"

ADD . orion-mcp/
WORKDIR orion-mcp

RUN git clone --depth 1 --branch v0.1.0 http://github.com/cloud-bulldozer/orion

RUN pip install -r requirements.txt

WORKDIR orion 
RUN pip install setuptools && \
    pip install -r requirements.txt && \
    python setup.py install && \
    pip install . && \
    ln -s ../venv/bin/orion ~/bin

RUN mkdir /orion
RUN cp -r examples /orion/examples

WORKDIR ../
CMD ["python3.11", "orion_mcp.py"]
