extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/opt.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}

#include <memoir/recording_session.h>
#include <memoir/meta_format.h>
#include <stdexcept>
#include <string>
#include <fstream>
#include <chrono>
#include <cstring>

namespace memoir {

// ---------------------------------------------------------------------------

struct RecordingSession::Impl {
    Config          config;
    RecordingInfo   info;

    AVFormatContext* fmtCtx  = nullptr;
    AVCodecContext*  encCtx  = nullptr;
    AVStream*        stream  = nullptr;
    SwsContext*      swsCtx  = nullptr;
    AVFrame*         frame   = nullptr;
    AVPacket*        packet  = nullptr;

    uint32_t lastSrcW = 0;
    uint32_t lastSrcH = 0;

    uint64_t recordFrameIndex = 0;
    bool     finalized        = false;

    // Metadata file
    std::ofstream metaFile;

    // -----------------------------------------------------------------------
    void InitMeta() {
        metaFile.open(info.meta_path,
                      std::ios::binary | std::ios::trunc);
        if (!metaFile)
            throw std::runtime_error(
                "Failed to open meta file: " + info.meta_path);

        // Header
        ReplayMetaFileHeaderV1 hdr{};
        std::memcpy(hdr.magic, "RCMETA1", 8); // includes null terminator
        hdr.version = 1;
        hdr.reserved0 = 0;
        auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        hdr.created_unix_ns = static_cast<uint64_t>(now_ns);
        hdr.key_count = static_cast<uint32_t>(config.key_map.size());
        hdr.reserved1 = 0;
        metaFile.write(reinterpret_cast<const char*>(&hdr), sizeof(hdr));

        // Key table
        for (const auto& k : config.key_map) {
            ReplayMetaKeyEntryV1 entry{};
            entry.bit_index   = k.bit_index;
            entry.virtual_key = k.virtual_key;
            std::memcpy(entry.name, k.name, sizeof(entry.name));
            metaFile.write(reinterpret_cast<const char*>(&entry),
                           sizeof(entry));
        }
    }

    // -----------------------------------------------------------------------
    void WriteMetaRow(uint64_t frame_id, int64_t capture_qpc,
                      int64_t host_accept_qpc, uint64_t keyboard_mask,
                      uint32_t width, uint32_t height, uint32_t stride) {
        ReplayMetaV1 row{};
        row.frame_id           = frame_id;
        row.record_frame_index = recordFrameIndex; // set before increment
        row.capture_qpc        = capture_qpc;
        row.host_accept_qpc    = host_accept_qpc;
        row.keyboard_mask      = keyboard_mask;
        row.width              = width;
        row.height             = height;
        row.analysis_stride    = stride;
        row.flags              = 0;
        metaFile.write(reinterpret_cast<const char*>(&row), sizeof(row));
    }

    // -----------------------------------------------------------------------
    // Apply encoder-specific options and attempt to open the codec.
    // Returns true on success, false if this encoder can't be used.
    bool TryOpenEncoder(const AVCodec* codec, const char* name) {
        encCtx = avcodec_alloc_context3(codec);
        if (!encCtx) return false;

        encCtx->width       = static_cast<int>(config.record_width);
        encCtx->height      = static_cast<int>(config.record_height);
        encCtx->pix_fmt     = AV_PIX_FMT_YUV444P;
        encCtx->color_range = AVCOL_RANGE_JPEG;
        encCtx->time_base   = AVRational{1, static_cast<int>(config.fps)};
        encCtx->gop_size    = static_cast<int>(config.gop);
        encCtx->max_b_frames = 0;

        if (std::strcmp(name, "hevc_nvenc") == 0) {
            av_opt_set(encCtx->priv_data, "preset", "p7", 0);
            av_opt_set(encCtx->priv_data, "tune",   "ll", 0);
            av_opt_set(encCtx->priv_data, "rc",     "constqp", 0);
            av_opt_set_int(encCtx->priv_data, "qp",  0, 0);
            av_opt_set(encCtx->priv_data, "profile", "rext", 0);
        } else if (std::strcmp(name, "hevc_amf") == 0) {
            av_opt_set(encCtx->priv_data, "usage",   "lowlatency", 0);
            av_opt_set(encCtx->priv_data, "quality", "quality", 0);
            av_opt_set(encCtx->priv_data, "rc",      "cqp", 0);
            av_opt_set_int(encCtx->priv_data, "qp_i", 0, 0);
            av_opt_set_int(encCtx->priv_data, "qp_p", 0, 0);
        } else if (std::strcmp(name, "libx265") == 0) {
            av_opt_set(encCtx->priv_data, "preset", "ultrafast", 0);
            av_opt_set(encCtx->priv_data, "x265-params",
                       "lossless=1:log-level=warning", 0);
        }

        int ret = avcodec_open2(encCtx, codec, nullptr);
        if (ret < 0) {
            avcodec_free_context(&encCtx);
            encCtx = nullptr;
            return false;
        }
        return true;
    }

    // -----------------------------------------------------------------------
    void Init() {
        info.base_path  = config.base_path;
        info.video_path = config.video_path.empty()
                            ? config.base_path + ".mp4"
                            : config.video_path;
        info.meta_path  = config.meta_path.empty()
                            ? config.base_path + ".meta"
                            : config.meta_path;
        info.width      = config.record_width;
        info.height     = config.record_height;

        // --- Encoder (try hardware first, fall back to software) ---
        static constexpr const char* encoder_names[] = {
            "hevc_nvenc", "hevc_amf", "libx265"
        };

        const AVCodec* codec = nullptr;
        const char* selected_name = nullptr;

        if (!config.encoder.empty()) {
            // Forced encoder
            codec = avcodec_find_encoder_by_name(config.encoder.c_str());
            if (!codec)
                throw std::runtime_error(
                    "Encoder not found: " + config.encoder);
            if (!TryOpenEncoder(codec, config.encoder.c_str()))
                throw std::runtime_error(
                    "Failed to open encoder: " + config.encoder);
            selected_name = config.encoder.c_str();
        } else {
            // Auto: try each in priority order
            for (const char* name : encoder_names) {
                codec = avcodec_find_encoder_by_name(name);
                if (!codec) continue;
                if (TryOpenEncoder(codec, name)) {
                    selected_name = name;
                    break;
                }
            }
        }

        if (!selected_name)
            throw std::runtime_error(
                "No HEVC encoder available — install a GPU driver with "
                "hardware encoding support, or build FFmpeg with libx265");

        info.codec = selected_name;

        // --- Muxer ---
        int ret = avformat_alloc_output_context2(
            &fmtCtx, nullptr, "mp4", info.video_path.c_str());
        if (ret < 0 || !fmtCtx)
            throw std::runtime_error("Failed to create MP4 context");

        stream = avformat_new_stream(fmtCtx, codec);
        if (!stream) throw std::runtime_error("Failed to create stream");

        avcodec_parameters_from_context(stream->codecpar, encCtx);
        stream->time_base = encCtx->time_base;

        ret = avio_open(&fmtCtx->pb, info.video_path.c_str(),
                        AVIO_FLAG_WRITE);
        if (ret < 0) {
            char buf[256]{};
            av_strerror(ret, buf, sizeof(buf));
            throw std::runtime_error(
                std::string("Failed to open ") + info.video_path +
                ": " + buf);
        }

        ret = avformat_write_header(fmtCtx, nullptr);
        if (ret < 0) throw std::runtime_error("Failed to write MP4 header");

        // --- Reusable frame + packet ---
        frame = av_frame_alloc();
        frame->format = AV_PIX_FMT_YUV444P;
        frame->width  = encCtx->width;
        frame->height = encCtx->height;
        av_frame_get_buffer(frame, 0);

        packet = av_packet_alloc();

        // Metadata file
        InitMeta();
    }

    // -----------------------------------------------------------------------
    void EnsureSws(uint32_t srcW, uint32_t srcH) {
        if (swsCtx && lastSrcW == srcW && lastSrcH == srcH) return;
        if (swsCtx) sws_freeContext(swsCtx);

        swsCtx = sws_getContext(
            static_cast<int>(srcW), static_cast<int>(srcH),
            AV_PIX_FMT_BGRA,
            encCtx->width, encCtx->height, AV_PIX_FMT_YUV444P,
            SWS_LANCZOS, nullptr, nullptr, nullptr);
        if (!swsCtx)
            throw std::runtime_error("Failed to create swscale context");

        // Force full-range on both input (RGB 0-255) and output (Y 0-255)
        // Without this, swscale compresses to limited range (16-235)
        const int* bt709 = sws_getCoefficients(SWS_CS_ITU709);
        sws_setColorspaceDetails(swsCtx,
            bt709, 1,   // source: BT.709, full range
            bt709, 1,   // dest:   BT.709, full range
            0, 1 << 16, 1 << 16); // brightness=0, contrast=1.0, saturation=1.0

        lastSrcW = srcW;
        lastSrcH = srcH;
    }

    // -----------------------------------------------------------------------
    void DrainPackets() {
        while (avcodec_receive_packet(encCtx, packet) == 0) {
            av_packet_rescale_ts(packet, encCtx->time_base,
                                 stream->time_base);
            packet->stream_index = stream->index;
            av_interleaved_write_frame(fmtCtx, packet);
            av_packet_unref(packet);
        }
    }

    // -----------------------------------------------------------------------
    void Cleanup() {
        if (packet)  { av_packet_free(&packet);  packet  = nullptr; }
        if (frame)   { av_frame_free(&frame);    frame   = nullptr; }
        if (metaFile.is_open()) metaFile.close();
        if (swsCtx)  { sws_freeContext(swsCtx);  swsCtx  = nullptr; }
        if (encCtx)  { avcodec_free_context(&encCtx); }
        if (fmtCtx) {
            if (fmtCtx->pb) avio_closep(&fmtCtx->pb);
            avformat_free_context(fmtCtx);
            fmtCtx = nullptr;
        }
    }
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

RecordingSession::RecordingSession(const Config& cfg)
    : impl_(std::make_unique<Impl>()) {
    impl_->config = cfg;
    impl_->Init();
}

RecordingSession::~RecordingSession() {
    if (!impl_->finalized) {
        try { Finalize(); } catch (...) {}
    }
    impl_->Cleanup();
}

void RecordingSession::RecordFrame(
    const uint8_t* bgra_data, uint32_t stride,
    uint32_t src_width, uint32_t src_height,
    uint64_t frame_id, int64_t capture_qpc,
    int64_t host_accept_qpc, uint64_t keyboard_mask) {

    if (impl_->finalized)
        throw std::runtime_error("Session already finalized");

    impl_->EnsureSws(src_width, src_height);

    // BGRA → NV12 + resize
    const uint8_t* srcSlice[] = {bgra_data};
    int srcStride[] = {static_cast<int>(stride)};
    av_frame_make_writable(impl_->frame);
    sws_scale(impl_->swsCtx, srcSlice, srcStride, 0,
              static_cast<int>(src_height),
              impl_->frame->data, impl_->frame->linesize);

    impl_->frame->pts = static_cast<int64_t>(impl_->recordFrameIndex);

    int ret = avcodec_send_frame(impl_->encCtx, impl_->frame);
    if (ret < 0) throw std::runtime_error("avcodec_send_frame failed");

    impl_->DrainPackets();

    // Write metadata row (before incrementing index)
    impl_->WriteMetaRow(frame_id, capture_qpc, host_accept_qpc,
                        keyboard_mask, src_width, src_height, stride);

    impl_->recordFrameIndex++;
}

void RecordingSession::Finalize() {
    if (impl_->finalized) return;
    impl_->finalized = true;

    // Flush encoder
    avcodec_send_frame(impl_->encCtx, nullptr);
    impl_->DrainPackets();

    if (impl_->fmtCtx)
        av_write_trailer(impl_->fmtCtx);

    // Close metadata file
    if (impl_->metaFile.is_open())
        impl_->metaFile.close();
}

RecordingInfo RecordingSession::GetInfo() const {
    return impl_->info;
}

uint64_t RecordingSession::GetFrameCount() const {
    return impl_->recordFrameIndex;
}

} // namespace memoir
