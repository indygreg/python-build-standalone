{% include 'base.Dockerfile' %}
RUN apt-get install \
    libc6-dev \
    libc6-dev:i386 \
    libffi-dev \
    make \
    patch \
    tar \
    xz-utils \
    unzip \
    zlib1g-dev
