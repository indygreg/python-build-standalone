{% include 'base.Dockerfile' %}
RUN apt-get install \
    libc6-dev \
    patch \
    python \
    tar \
    xz-utils \
    unzip \
    zlib1g-dev
