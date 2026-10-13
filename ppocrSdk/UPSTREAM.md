# PaddleOCR upstream SDK

The generated `src/main/java/com/paddle/ocr/` sources are pulled from the official
PaddleOCR Android SDK, revision `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf`:
https://github.com/PaddlePaddle/PaddleOCR/tree/dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf/deploy/ppocr-android/ppocr-sdk

The SDK is licensed under Apache-2.0; its original source copyright and license
headers remain intact. Sources and ONNX weights are prepared by
`scripts/prepare-android-ocr.sh`, ignored by Git, and bundled into the APK.
The app integrates through its own `OcrAdapter`; it does not fork upstream
inference or preprocessing algorithms.
