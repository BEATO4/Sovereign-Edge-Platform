# Multi-stage Rust build for ultra-minimal, high-performance edge auth container
FROM rust:1.78-alpine as builder
WORKDIR /usr/src/edge-auth
RUN apk add --no-cache musl-dev
COPY Cargo.toml ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo build --release || true
COPY src ./src
RUN cargo build --release

FROM alpine:3.19
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /usr/src/edge-auth/target/release/edge-auth-rust /app/edge-auth-rust
EXPOSE 9001
CMD ["/app/edge-auth-rust"]
