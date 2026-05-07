FROM ubuntu:20.04
ARG DEBIAN_FRONTEND=noninteractive
### Stage 1 - add/remove packages ###
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    m4 \
    scons \
    zlib1g \
    zlib1g-dev \ 
    libprotobuf-dev \
    protobuf-compiler \ 
    libprotoc-dev \ 
    libgoogle-perftools-dev \
    python3-dev \
    python-is-python3 \
    libboost-all-dev \ 
    pkg-config \ 
    graphviz \
    libhdf5-dev \
    libpng-dev \
    python3-pip \
    cmake \
    wget

RUN python3 -m pip install pydot
RUN python3 -m pip install scons==3.1.2
RUN cd /mold && wget https://github.com/rui314/mold/releases/download/v2.41.0/mold-2.41.0-x86_64-linux.tar.gz
RUN cp -r mold-2.41.0-x86_64-linux/bin /usr
RUN cp -r mold-2.41.0-x86_64-linux/lib /usr
RUN cp -r mold-2.41.0-x86_64-linux/libexec /usr
RUN cp -r mold-2.41.0-x86_64-linux/share /usr
WORKDIR /ezh
RUN git config --global --add safe.directory /ezh
RUN git config --global --add safe.directory /ezh/gem5
CMD ["/bin/bash"]