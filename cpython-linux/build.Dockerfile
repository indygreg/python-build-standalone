{% include 'base.Dockerfile' %}
RUN apt-get install \
    file \
    libc6-dev \
    make \
    patch \
    perl \
    pkg-config \
    tar \
    xz-utils \
    unzip
