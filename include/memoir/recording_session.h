#pragma once

#include <memoir/types.h>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace memoir {

enum class RecordingState {
    Inactive,
    Starting,
    Active,
    Stopping,
    Failed
};

struct RecordingInfo {
    std::string base_path;
    std::string video_path;
    std::string meta_path;
    std::string codec;
    uint32_t width  = 0;
    uint32_t height = 0;
};

class RecordingSession {
public:
    struct Config {
        std::string base_path;
        std::string video_path;   // if non-empty, overrides base_path + ".mp4"
        std::string meta_path;    // if non-empty, overrides base_path + ".meta"
        uint32_t record_width  = 1920;
        uint32_t record_height = 1080;
        uint32_t gop = 1;
        double fps = 10.0;
        std::string encoder;  // empty = auto (try nvenc → amf → mf → libx265)
        std::vector<KeySpec> key_map;
    };

    explicit RecordingSession(const Config& cfg);
    ~RecordingSession();

    RecordingSession(const RecordingSession&) = delete;
    RecordingSession& operator=(const RecordingSession&) = delete;

    void RecordFrame(const uint8_t* bgra_data, uint32_t stride,
                     uint32_t src_width, uint32_t src_height,
                     uint64_t frame_id, int64_t capture_qpc,
                     int64_t host_accept_qpc, uint64_t keyboard_mask);

    void Finalize();

    RecordingInfo GetInfo() const;
    uint64_t GetFrameCount() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace memoir
