#include "recorder_core.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace recorder {

float LevelDetector::ToDbfs(double linear) {
    const double clamped = std::max(linear, 1.0);
    return static_cast<float>(20.0 * std::log10(clamped / 32768.0));
}

LevelStats LevelDetector::Analyze(const int16_t* samples, size_t sample_count) {
    if (samples == nullptr || sample_count == 0) {
        return {};
    }

    int64_t sum_squares = 0;
    int peak = 0;
    for (size_t i = 0; i < sample_count; ++i) {
        const int sample = samples[i];
        const int abs_sample = sample == std::numeric_limits<int16_t>::min() ? 32768 : std::abs(sample);
        sum_squares += static_cast<int64_t>(sample) * sample;
        peak = std::max(peak, abs_sample);
    }

    const double mean_square = static_cast<double>(sum_squares) / static_cast<double>(sample_count);
    const double rms = std::sqrt(mean_square);
    return {
        .rms_dbfs = ToDbfs(rms),
        .peak_dbfs = ToDbfs(static_cast<double>(peak)),
    };
}

TriggerResult TriggerState::Update(float rms_dbfs, float threshold_dbfs) {
    const bool over_threshold = rms_dbfs >= threshold_dbfs;

    if (mode_ == TriggerMode::kQuiet) {
        over_threshold_frames_ = over_threshold ? 1 : 0;
        silence_frames_ = 0;
        if (over_threshold) {
            mode_ = TriggerMode::kCandidateSound;
        }
        return {.mode = mode_};
    }

    if (mode_ == TriggerMode::kCandidateSound) {
        if (!over_threshold) {
            Reset();
            return {.mode = mode_};
        }
        ++over_threshold_frames_;
        if (over_threshold_frames_ >= kStartHoldFrames) {
            mode_ = TriggerMode::kRecording;
            recording_frames_ = 0;
            silence_frames_ = 0;
            return {.mode = mode_, .event = TriggerEvent::kStartRecording};
        }
        return {.mode = mode_};
    }

    ++recording_frames_;
    if (recording_frames_ >= kMaxSegmentFrames) {
        Reset();
        return {
            .mode = mode_,
            .event = TriggerEvent::kStopRecording,
            .close_reason = CloseReason::kMaxDuration,
        };
    }

    if (over_threshold) {
        silence_frames_ = 0;
    } else {
        ++silence_frames_;
        if (silence_frames_ >= kStopSilenceFrames) {
            Reset();
            return {
                .mode = mode_,
                .event = TriggerEvent::kStopRecording,
                .close_reason = CloseReason::kSilenceTimeout,
            };
        }
    }

    return {.mode = mode_};
}

TriggerResult TriggerState::ButtonStop() {
    if (mode_ != TriggerMode::kRecording) {
        Reset();
        return {.mode = mode_};
    }
    Reset();
    return {
        .mode = mode_,
        .event = TriggerEvent::kStopRecording,
        .close_reason = CloseReason::kButtonStop,
    };
}

void TriggerState::Reset() {
    mode_ = TriggerMode::kQuiet;
    over_threshold_frames_ = 0;
    silence_frames_ = 0;
    recording_frames_ = 0;
}

void PreRollBuffer::PushFrame(const int16_t* samples) {
    if (samples == nullptr) {
        return;
    }
    std::memcpy(&frames_[write_index_ * kFrameSamples], samples, kFrameSamples * sizeof(int16_t));
    write_index_ = (write_index_ + 1) % kPreRollFrames;
    if (frame_count_ < kPreRollFrames) {
        ++frame_count_;
    }
}

void PreRollBuffer::Clear() {
    write_index_ = 0;
    frame_count_ = 0;
}

const char* ToString(TriggerMode mode) {
    switch (mode) {
    case TriggerMode::kQuiet:
        return "quiet";
    case TriggerMode::kCandidateSound:
        return "candidate_sound";
    case TriggerMode::kRecording:
        return "recording";
    }
    return "unknown";
}

const char* ToString(CloseReason reason) {
    switch (reason) {
    case CloseReason::kNone:
        return "none";
    case CloseReason::kSilenceTimeout:
        return "silence_timeout";
    case CloseReason::kButtonStop:
        return "button_stop";
    case CloseReason::kMaxDuration:
        return "max_duration";
    }
    return "unknown";
}

}  // namespace recorder
