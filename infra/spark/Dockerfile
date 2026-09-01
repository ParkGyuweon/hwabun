ARG SPARK_VERSION=3.5.6
FROM apache/spark:${SPARK_VERSION}-python3

USER root

RUN mkdir -p /opt/project/data /opt/spark-events /opt/spark/.ivy2 \
    && chmod -R g=u /opt/project /opt/spark-events /opt/spark/.ivy2

COPY conf/spark-defaults.conf /opt/spark/conf/spark-defaults.conf
