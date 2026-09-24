"""PRAHARI ANPR: FrameSample -> PlateEvent.

    pipeline.py  PlatePipeline (detector + OCR + two-line + grammar + evidence)
    dedup.py     PlateDeduper (one event per vehicle pass, per camera/epoch)
    ccap.py      CameraProfiler (is this camera ANPR-viable?)
    models.py    model registry / downloader (weights under <repo>/models)
    synth.py     synthetic Indian plates and scenes for tests
    evaluate.py  synthetic accuracy report
    bench.py     throughput benchmark
"""
