{% include 'base.Dockerfile' %}
RUN apt-get install \
    file \
    libc6-dev \
    make \
    patch \
    patchelf \
    perl \
    pkg-config \
    tar \
    xz-utils \
    unzip

RUN apt-get install crossbuild-essential-arm64 &&\
    apt-get install crossbuild-essential-armhf
