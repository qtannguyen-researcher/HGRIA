"""Health check endpoint."""

from flask import Blueprint, current_app, jsonify


health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint returning server status."""
    state_manager = current_app.config.get("HG_STATE_MANAGER")
    state = state_manager.state.value if state_manager else "unknown"

    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "pipeline_state": state,
    }), 200


@health_bp.route("/api/debug", methods=["GET"])
def debug_info():
    """Diagnostic endpoint — shows exactly where frames are being dropped."""
    config      = current_app.config.get("HG_CONFIG")
    pipeline    = current_app.config.get("HG_PIPELINE")

    # ── Config snapshot ────────────────────────────────────────────────────
    colab_mode   = bool(config.camera.colab_mode)  if config else None
    colab_fallback = bool(getattr(config.camera, "colab_fallback", False)) if config else None
    blur_thresh  = config.gesture_recognition.noise_filter_blur_threshold if config else None
    smooth_win   = config.gesture_recognition.smoothing_window_size        if config else None
    conf_thresh  = config.gesture_recognition.confidence_threshold         if config else None
    preview_enabled = (
        bool(config.is_preview_enabled())
        if config and hasattr(config, "is_preview_enabled")
        else None
    )
    strict_camera = (
        bool(config.is_strict_camera())
        if config and hasattr(config, "is_strict_camera")
        else None
    )
    evaluation_mode = (
        bool(config.is_evaluation_mode())
        if config and hasattr(config, "is_evaluation_mode")
        else None
    )
    dynamic_enabled = (
        bool(config.is_dynamic_gestures_enabled())
        if config and hasattr(config, "is_dynamic_gestures_enabled")
        else None
    )

    # ── FrameStore status ──────────────────────────────────────────────────
    frame_store_has_frame = False
    try:
        from backend.pipeline.camera import FrameStore
        frame_store_has_frame = FrameStore().get_latest() is not None
    except Exception:
        pass

    # ── Pipeline stats ─────────────────────────────────────────────────────
    stats = dict(pipeline.stats) if pipeline else {}
    blur_history = list(pipeline._blur_history) if pipeline else []
    avg_blur = round(sum(blur_history) / len(blur_history), 2) if blur_history else None

    dropped_frames = 0
    try:
        from backend.pipeline.camera import FrameStore
        dropped_frames = FrameStore().dropped_frames
    except Exception:
        dropped_frames = stats.get("dropped_frames", 0)

    instrumentation = {}
    if pipeline is not None and hasattr(pipeline, "instrumentation_debug"):
        instrumentation = pipeline.instrumentation_debug()
    else:
        instrumentation = {
            "processed_frames": stats.get("frames_captured", 0),
            "commands_sent": stats.get("commands_sent", 0),
            "dropped_frames": dropped_frames,
            "avg_total_server_ms": None,
            "latest_timing": {},
        }

    return jsonify({
        "config": {
            "colab_mode":   colab_mode,
            "colab_fallback": colab_fallback,
            "strict_camera": strict_camera,
            "preview_enabled": preview_enabled,
            "evaluation_mode": evaluation_mode,
            "dynamic_gestures_enabled": dynamic_enabled,
            "blur_threshold_effective": (
                blur_thresh // 4 if colab_mode else blur_thresh
            ),
            "smoothing_window": smooth_win,
            "confidence_threshold": conf_thresh,
            "opencv_baseline_invalid_if_colab_mode": True,
        },
        "frame_store_has_frame": frame_store_has_frame,
        "pipeline_stats": stats,
        "processed_frames": instrumentation.get("processed_frames", stats.get("frames_captured", 0)),
        "commands_sent": instrumentation.get("commands_sent", stats.get("commands_sent", 0)),
        "dropped_frames": instrumentation.get("dropped_frames", dropped_frames),
        "latest_timing": instrumentation.get("latest_timing", {}),
        "avg_total_server_ms": instrumentation.get("avg_total_server_ms"),
        "instrumentation": instrumentation,
        "avg_blur_last_30_frames": avg_blur,
        "diagnosis": _diagnose(stats, colab_mode, frame_store_has_frame, colab_fallback),
    }), 200


def _diagnose(stats: dict, colab_mode, frame_store_has_frame, colab_fallback=None) -> str:
    """Return a plain-English summary of where the pipeline is stuck."""
    if not stats:
        return "Pipeline not attached to app — check HG_PIPELINE in app.config"

    if colab_mode:
        suffix = (
            " INVALID as a local OpenCV baseline (colab_mode=true"
            + (", fallback from failed camera open)" if colab_fallback else ").")
        )
    else:
        suffix = ""

    captured = stats.get("frames_captured", 0)
    if captured == 0:
        if colab_mode and not frame_store_has_frame:
            return (
                "NO FRAMES: colab_mode=True but FrameStore is empty — browser is not "
                "POSTing to /api/frame, or WebcamBridge is not running." + suffix
            )
        if not colab_mode:
            return "NO FRAMES: colab_mode=False — OpenCV camera may not be producing frames"
        return "NO FRAMES: unknown reason." + suffix

    no_hand   = stats.get("frames_no_hand",         0)
    noise     = stats.get("frames_filtered_noise",  0)
    temporal  = stats.get("frames_filtered_temporal", 0)
    cooldown  = stats.get("frames_cooldown",         0)
    commands  = stats.get("commands_sent",           0)

    if commands > 0:
        return f"OK — {commands} command(s) sent so far.{suffix}"

    hand_frames = captured - no_hand
    if hand_frames == 0:
        return "STUCK at Stage 3: MediaPipe detects no hand in any frame — check lighting and hand position"
    if noise > hand_frames * 0.8:
        return "STUCK at NoiseFilter: >80% of hand frames rejected — likely blurry_frame (JPEG from browser has low Laplacian score)"
    if temporal > hand_frames * 0.5:
        return f"STUCK at TemporalFilter: majority-vote window not filling — need {stats.get('smoothing_window', '?')} consistent frames"
    if cooldown > 0 and commands == 0:
        return "STUCK at Cooldown: gestures recognised but all on cooldown"
    return "Gestures reaching pipeline but no command emitted — check gesture mapping"
