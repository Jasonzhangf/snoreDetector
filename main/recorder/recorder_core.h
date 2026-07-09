#ifndef RECORDER_CORE_H
#define RECORDER_CORE_H

#include <array>
#include <cstddef>
#include <cstdint>

namespace recorder {

constexpr int kSampleRate = 16000;
constexpr int kFrameMs = 20;
constexpr int kFrameSamples = kSampleRate * kFrameMs / 1000;
constexpr int kPreRollMs = 1500;
constexpr int kPreRollFrames = kPreRollMs / kFrameMs;
constexpr int kStartHoldMs = 500;
constexpr int kStartHoldFrames = kStartHoldMs / kFrameMs;
constexpr int kStopSilenceMs = 3000;
constexpr int kStopSilenceFrames = kStopSilenceMs / kFrameMs;
constexpr int kMaxSegmentMs = 10 * 60 * 1000;
constexpr int kMaxSegmentFrames = kMaxSegmentMs / kFrameMs;

struct LevelStats {
    float rms_dbfs = -90.0f;
    float peak_dbfs = -90.0f;
};

class LevelDetector {
public:
    static LevelStats Analyze(const int16_t* samples, size_t sample_count);

private:
    static float ToDbfs(double linear);
};

enum class TriggerMode {
    kQuiet,
    kCandidateSound,
    kRecording,
};

enum class TriggerEvent {
    kNone,
    kStartRecording,
    kStopRecording,
};

enum class CloseReason {
    kNone,
    kSilenceTimeout,
    kButtonStop,
    kMaxDuration,
};

struct TriggerResult {
    TriggerMode mode = TriggerMode::kQuiet;
    TriggerEvent event = TriggerEvent::kNone;
    CloseReason close_reason = CloseReason::kNone;
};

class TriggerState {
public:
    TriggerResult Update(float rms_dbfs, float threshold_dbfs);
    TriggerResult ButtonStop();
    void Reset();

    TriggerMode mode() const { return mode_; }
    int over_threshold_frames() const { return over_threshold_frames_; }
    int silence_frames() const { return silence_frames_; }
    int recording_frames() const { return recording_frames_; }

private:
    TriggerMode mode_ = TriggerMode::kQuiet;
    int over_threshold_frames_ = 0;
    int silence_frames_ = 0;
    int recording_frames_ = 0;
};

class PreRollBuffer {
public:
    void PushFrame(const int16_t* samples);
    void Clear();

    int frame_count() const { return frame_count_; }
    bool full() const { return frame_count_ == kPreRollFrames; }

    template <typename Visitor>
    void ForEachOldestFrame(Visitor visitor) const {
        const int count = frame_count_;
        const int first = full() ? write_index_ : 0;
        for (int i = 0; i < count; ++i) {
            const int frame_index = (first + i) % kPreRollFrames;
            visitor(FrameData(frame_index), kFrameSamples);
        }
    }

private:
    const int16_t* FrameData(int frame_index) const {
        return &frames_[frame_index * kFrameSamples];
    }

    std::array<int16_t, kPreRollFrames * kFrameSamples> frames_{};
    int write_index_ = 0;
    int frame_count_ = 0;
};

const char* ToString(TriggerMode mode);
const char* ToString(CloseReason reason);

}  // namespace recorder

#endif  // RECORDER_CORE_H
