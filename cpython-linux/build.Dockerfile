{% include 'base.Dockerfile' %}
RUN apt-get install \
    file \
    libc6-dev \
    libx11-dev \
    make \
    patch \
    perl \
    tar \
    xz-utils \
    unzip
