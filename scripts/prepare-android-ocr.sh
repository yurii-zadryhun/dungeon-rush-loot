#!/usr/bin/env bash
# Idempotent build-time installation of the official PaddleOCR Android SDK
# and PP-OCRv6 Small ONNX models. None of this downloads at app runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="$ROOT/ppocrSdk"
REV="dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf"
SOURCE="https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

if [[ ! -f "$SDK/src/.source-revision" ]] || [[ "$(cat "$SDK/src/.source-revision")" != "$REV" ]]; then
  git init -q "$TEMP/upstream"
  git -C "$TEMP/upstream" remote add origin https://github.com/PaddlePaddle/PaddleOCR.git
  git -C "$TEMP/upstream" sparse-checkout init --cone
  git -C "$TEMP/upstream" sparse-checkout set deploy/ppocr-android/ppocr-sdk/src/main
  git -C "$TEMP/upstream" -c protocol.version=2 fetch --depth=1 --filter=blob:none origin "$REV"
  git -C "$TEMP/upstream" checkout -q --detach FETCH_HEAD
  mkdir -p "$SDK/src"
  cp -a "$TEMP/upstream/deploy/ppocr-android/ppocr-sdk/src/main" "$SDK/src/"
  printf '%s\n' "$REV" > "$SDK/src/.source-revision"
fi

install_model() {
  local kind="$1" archive="$2"
  local destination="$SDK/src/main/assets/models/$kind"
  if [[ -s "$destination/inference.onnx" ]] &&
      { [[ "$kind" == det ]] || [[ -s "$destination/inference.yml" ]]; }; then
    echo "PaddleOCR $kind model already present."
    return
  fi
  local temp="$TEMP/$kind"
  mkdir -p "$temp"
  curl --fail --location --retry 3 --retry-delay 2 --silent --show-error \
    "$SOURCE/$archive" -o "$temp/model.tar"
  tar -xf "$temp/model.tar" -C "$temp"
  local weights config
  weights="$(find "$temp" -type f -name inference.onnx -print -quit)"
  [[ -n "$weights" ]] || { echo "Missing inference.onnx in $archive" >&2; exit 1; }
  mkdir -p "$destination"
  cp "$weights" "$destination/inference.onnx"
  if [[ "$kind" == rec ]]; then
    config="$(find "$temp" -type f -name inference.yml -print -quit)"
    [[ -n "$config" ]] || { echo "Missing inference.yml in $archive" >&2; exit 1; }
    cp "$config" "$destination/inference.yml"
  fi
  sha256sum "$destination/inference.onnx"
}

install_model det PP-OCRv6_small_det_onnx_infer.tar
install_model rec PP-OCRv6_small_rec_onnx_infer.tar
