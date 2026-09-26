# Detection plugins

`backend/app/detection.py` defines `FrameContext`, `DetectionResult`, and the `DetectorPlugin` protocol. A result names camera, UTC capture time, frame size, event type, normalized geometry, optional track/confidence, detector/version, structured metadata, and its simulation flag. Plugins advertise availability and supported event types.

`SimulatedScenarioPlugin` operates only on the generated synthetic source and returns reproducible fixture geometry for obstruction, person-down, or smoke/fire. It does not inspect real camera frames. `UnavailableRealDetector` explicitly reports unavailable and returns no events. Do not enable a simulated plugin on RTSP or file sources.

An integration should implement a plugin beside the existing adapter, preserve a separately testable temporal/rule evaluator, and return typed results without directly writing incidents. Temporal evaluation, deduplication/persistence, and notification delivery belong to separate worker services. Fall/ground and route obstruction detection require time-based evidence and should not be implemented as one-frame labels.

For a real model, document upstream repository, exact model/version/hash, license and commercial-use conditions, preprocessing, supported event types, hardware needs, calibration, validation set provenance, and evaluation metrics. Report model availability honestly. Vigilon is not a replacement for certified fire or life-safety systems and makes no accuracy or intent-prediction claim.
