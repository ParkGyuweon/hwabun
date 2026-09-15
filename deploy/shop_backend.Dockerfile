FROM eclipse-temurin:21-jdk AS build

WORKDIR /app
COPY shop_backend/ .
RUN chmod +x gradlew && ./gradlew bootJar --no-daemon

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar

EXPOSE 8090
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
