#include "recorder/recorder_core.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace recorder;

namespace {

void Check(bool condition, const char* message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

void CheckNear(float actual, float expected, float tolerance, const char* message) {
    if (std::fabs(actual - expected) > tolerance) {
        std::fprintf(stderr, "FAIL: %s actual=%.4f expected=%.4f\n", message, actual, expected);
        std::exit(1);
    }
}

std::array<int16_t, kFrameSamples> ConstantFrame(int16_t value) {
    std::array<int16_t, kFrameSamples> frame{};
    frame.fill(value);
    return frame;
}

void TestLevelDetector() {
    auto half_scale = ConstantFrame(16384);
    const LevelStats half = LevelDetector::Analyze(half_scale.data(), half_scale.size());
    CheckNear(half.rms_dbfs, -6.0206f, 0.01f, "half-scale RMS dBFS");
    CheckNear(half.peak_dbfs, -6.0206f, 0.01f, "half-scale peak dBFS");

    auto silence = ConstantFrame(0);
    const LevelStats floor = LevelDetector::Analyze(silence.data(), silence.size());
    CheckNear(floor.rms_dbfs, -90.3090f, 0.01f, "silence RMS floor");
    CheckNear(floor.peak_dbfs, -90.3090f, 0.01f, "silence peak floor");

    auto min_sample = ConstantFrame(-32768);
    const LevelStats full = LevelDetector::Analyze(min_sample.data(), min_sample.size());
    CheckNear(full.peak_dbfs, 0.0f, 0.01f, "int16 min absolute peak");
}

void TestStartHold() {
    TriggerState trigger;
    TriggerResult result;
    for (int i = 0; i < kStartHoldFrames - 1; ++i) {
        result = trigger.Update(-30.0f, -40.0f);
        Check(result.event == TriggerEvent::kNone, "start must not fire before 500ms");
    }
    result = trigger.Update(-30.0f, -40.0f);
    Check(result.event == TriggerEvent::kStartRecording, "start fires at 500ms");
    Check(trigger.mode() == TriggerMode::kRecording, "mode is recording after start");

    trigger.Reset();
    for (int i = 0; i < kStartHoldFrames - 1; ++i) {
        trigger.Update(-30.0f, -40.0f);
    }
    result = trigger.Update(-50.0f, -40.0f);
    Check(result.event == TriggerEvent::kNone, "below threshold cancels candidate");
    Check(trigger.mode() == TriggerMode::kQuiet, "candidate returns to quiet when sound drops");
}

void StartRecording(TriggerState& trigger) {
    TriggerResult result;
    for (int i = 0; i < kStartHoldFrames; ++i) {
        result = trigger.Update(-30.0f, -40.0f);
    }
    Check(result.event == TriggerEvent::kStartRecording, "test setup enters recording");
}

void TestSilenceStop() {
    TriggerState trigger;
    StartRecording(trigger);
    TriggerResult result;
    for (int i = 0; i < kStopSilenceFrames - 1; ++i) {
        result = trigger.Update(-60.0f, -40.0f);
        Check(result.event == TriggerEvent::kNone, "silence stop must not fire early");
    }
    result = trigger.Update(-60.0f, -40.0f);
    Check(result.event == TriggerEvent::kStopRecording, "silence stop fires at 3000ms");
    Check(result.close_reason == CloseReason::kSilenceTimeout, "silence close reason");

    StartRecording(trigger);
    for (int i = 0; i < kStopSilenceFrames - 1; ++i) {
        trigger.Update(-60.0f, -40.0f);
    }
    result = trigger.Update(-30.0f, -40.0f);
    Check(result.event == TriggerEvent::kNone, "sound resets silence counter");
    Check(trigger.mode() == TriggerMode::kRecording, "still recording after sound resumes");
}

void TestButtonAndMaxDuration() {
    TriggerState trigger;
    TriggerResult result = trigger.ButtonStop();
    Check(result.event == TriggerEvent::kNone, "button stop outside recording does not emit stop");

    StartRecording(trigger);
    result = trigger.ButtonStop();
    Check(result.event == TriggerEvent::kStopRecording, "button stop emits stop while recording");
    Check(result.close_reason == CloseReason::kButtonStop, "button close reason");

    StartRecording(trigger);
    for (int i = 0; i < kMaxSegmentFrames - 1; ++i) {
        result = trigger.Update(-30.0f, -40.0f);
        Check(result.event == TriggerEvent::kNone, "max duration must not fire early");
    }
    result = trigger.Update(-30.0f, -40.0f);
    Check(result.event == TriggerEvent::kStopRecording, "max duration emits stop");
    Check(result.close_reason == CloseReason::kMaxDuration, "max duration close reason");
}

void TestPreRollOrder() {
    PreRollBuffer pre_roll;
    std::array<int16_t, kFrameSamples> frame{};
    for (int value = 1; value <= kPreRollFrames + 5; ++value) {
        frame.fill(static_cast<int16_t>(value));
        pre_roll.PushFrame(frame.data());
    }
    Check(pre_roll.full(), "pre-roll is full after overflow pushes");

    std::vector<int> first_samples;
    pre_roll.ForEachOldestFrame([&first_samples](const int16_t* samples, size_t count) {
        Check(count == kFrameSamples, "pre-roll visitor receives a full frame");
        first_samples.push_back(samples[0]);
    });
    Check(static_cast<int>(first_samples.size()) == kPreRollFrames, "pre-roll drains 75 frames");
    Check(first_samples.front() == 6, "oldest frame after wrap is preserved");
    Check(first_samples.back() == kPreRollFrames + 5, "newest frame after wrap is last");
    for (size_t i = 1; i < first_samples.size(); ++i) {
        Check(first_samples[i] == first_samples[i - 1] + 1, "pre-roll order is oldest to newest");
    }

    pre_roll.Clear();
    Check(pre_roll.frame_count() == 0, "pre-roll clear resets count");
}

}  // namespace

int main() {
    TestLevelDetector();
    TestStartHold();
    TestSilenceStop();
    TestButtonAndMaxDuration();
    TestPreRollOrder();
    std::puts("recorder_core_test passed");
    return 0;
}
