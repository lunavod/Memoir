#pragma once

#include <memoir/types.h>
#include <memoir/frame_packet.h>
#include <memoir/recording_session.h>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace memoir {

class CaptureEngine {
public:
    explicit CaptureEngine(const EngineConfig& config);
    ~CaptureEngine();

    CaptureEngine(const CaptureEngine&) = delete;
    CaptureEngine& operator=(const CaptureEngine&) = delete;

    void Start();
    void Stop();

    std::shared_ptr<FramePacket> GetNextFrame(int timeout_ms = -1);

    // Recording
    RecordingInfo StartRecording(const std::string& base_path,
                                 const std::string& encoder = "");
    RecordingInfo StartRecording(const std::string& base_path,
                                 const std::string& video_path,
                                 const std::string& meta_path,
                                 const std::string& encoder = "");
    void StopRecording();
    bool IsRecording() const;

    EngineStats  GetStats() const;
    EngineState  GetState() const;
    std::optional<std::string> GetLastError() const;

    void SubmitAnalysisResult(uint64_t frame_id, uint32_t flags,
                              const std::vector<uint8_t>& payload);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace memoir
