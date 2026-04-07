#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <cstring>
#include <memoir/version.h>
#include <memoir/capture_engine.h>
#include <memoir/frame_packet.h>
#include <memoir/types.h>

namespace py = pybind11;
using namespace memoir;

// Helper: iterator returned by CaptureEngine.frames()
struct FrameIterator {
    CaptureEngine* engine;
};

PYBIND11_MODULE(_native, m) {
    m.doc() = "memoir-capture \xe2\x80\x93 capture/replay module";
    m.attr("__version__") = MEMOIR_VERSION_STRING;

    m.def("ping", []() {
        return std::string("memoir-capture ") + MEMOIR_VERSION_STRING + " loaded OK";
    }, "Health-check function");

    // ------------------------------------------------------------------
    // FramePacket
    // ------------------------------------------------------------------
    py::class_<FramePacket, std::shared_ptr<FramePacket>>(m, "FramePacket")
        .def_readonly("frame_id",        &FramePacket::frame_id)
        .def_readonly("capture_qpc",     &FramePacket::capture_qpc)
        .def_readonly("host_accept_qpc", &FramePacket::host_accept_qpc)
        .def_readonly("keyboard_mask",   &FramePacket::keyboard_mask)
        .def_readonly("width",           &FramePacket::width)
        .def_readonly("height",          &FramePacket::height)
        .def_readonly("stride",          &FramePacket::stride)
        .def_readonly("channels",        &FramePacket::channels)
        .def_property_readonly("cpu_bgra",
            [](FramePacket& self) -> py::object {
                if (self.IsReleased())
                    throw py::value_error("Packet already released");
                return py::array_t<uint8_t>(
                    {static_cast<py::ssize_t>(self.height),
                     static_cast<py::ssize_t>(self.width),
                     static_cast<py::ssize_t>(self.channels)},
                    {static_cast<py::ssize_t>(self.stride),
                     static_cast<py::ssize_t>(self.channels),
                     static_cast<py::ssize_t>(1)},
                    self.pixel_data.data(),
                    py::cast(self));   // base keeps packet alive
            })
        .def("release", &FramePacket::Release)
        .def("__enter__",
             [](py::object self) -> py::object { return self; })
        .def("__exit__",
             [](FramePacket& self, py::object, py::object, py::object) {
                 self.Release();
             });

    // ------------------------------------------------------------------
    // _FrameIterator (internal, used by CaptureEngine.frames())
    // ------------------------------------------------------------------
    py::class_<FrameIterator>(m, "_FrameIterator")
        .def("__iter__",
             [](FrameIterator& self) -> FrameIterator& { return self; })
        .def("__next__",
             [](FrameIterator& self) -> std::shared_ptr<FramePacket> {
                 py::gil_scoped_release release;
                 auto pkt = self.engine->GetNextFrame(-1);
                 if (!pkt) throw py::stop_iteration();
                 return pkt;
             });

    // ------------------------------------------------------------------
    // CaptureEngine
    // ------------------------------------------------------------------
    py::class_<CaptureEngine>(m, "CaptureEngine")
        .def(py::init(
            [](py::dict target, double max_fps, uint32_t queue_capacity,
               const std::string& /*analysis_format*/,
               py::object key_map_obj,
               const std::string& /*drop_policy*/, bool capture_cursor,
               uint32_t record_width, uint32_t record_height,
               uint32_t record_gop,
               const std::string& /*record_codec*/) {
                EngineConfig cfg;

                auto type_str = target["type"].cast<std::string>();
                if (type_str == "monitor_index") {
                    cfg.target.type = CaptureTargetType::MonitorIndex;
                    cfg.target.monitor_index =
                        target["value"].cast<int32_t>();
                } else if (type_str == "window_title") {
                    cfg.target.type = CaptureTargetType::WindowTitleRegex;
                    auto v = target["value"].cast<std::string>();
                    cfg.target.value_wstr =
                        std::wstring(v.begin(), v.end());
                } else if (type_str == "window_exe") {
                    cfg.target.type = CaptureTargetType::WindowExeRegex;
                    auto v = target["value"].cast<std::string>();
                    cfg.target.value_wstr =
                        std::wstring(v.begin(), v.end());
                } else {
                    throw py::value_error(
                        "Unknown target type: " + type_str);
                }

                cfg.max_fps                = max_fps;
                cfg.analysis_queue_capacity = queue_capacity;
                cfg.capture_cursor         = capture_cursor;
                cfg.record_width           = record_width;
                cfg.record_height          = record_height;
                cfg.record_gop             = record_gop;

                // Parse key_map: list of (bit_index, virtual_key, name)
                if (!key_map_obj.is_none()) {
                    auto key_list = key_map_obj.cast<py::list>();
                    for (auto item : key_list) {
                        auto t = item.cast<py::tuple>();
                        if (t.size() != 3)
                            throw py::value_error(
                                "key_map entries must be "
                                "(bit_index, virtual_key, name)");
                        KeySpec k{};
                        k.bit_index   = t[0].cast<uint32_t>();
                        k.virtual_key = t[1].cast<uint32_t>();
                        auto name = t[2].cast<std::string>();
                        std::strncpy(k.name, name.c_str(),
                                     sizeof(k.name) - 1);
                        cfg.key_map.push_back(k);
                    }
                }

                return std::make_unique<CaptureEngine>(cfg);
            }),
            py::arg("target"),
            py::arg("max_fps") = 10.0,
            py::arg("analysis_queue_capacity") = 1,
            py::arg("analysis_format") = "bgra",
            py::arg("key_map") = py::none(),
            py::arg("drop_policy") = "drop_new",
            py::arg("capture_cursor") = false,
            py::arg("record_width") = 1920,
            py::arg("record_height") = 1080,
            py::arg("record_gop") = 1,
            py::arg("record_codec") = "hevc")
        // lifecycle (GIL released for potentially slow operations)
        .def("start", [](CaptureEngine& self) {
            py::gil_scoped_release rel;
            self.Start();
        })
        .def("stop", [](CaptureEngine& self) {
            py::gil_scoped_release rel;
            self.Stop();
        })
        .def("close", [](CaptureEngine& self) {
            py::gil_scoped_release rel;
            self.Stop();
        })
        // frame delivery
        .def("get_next_frame",
             [](CaptureEngine& self, int timeout_ms)
                 -> std::shared_ptr<FramePacket> {
                 py::gil_scoped_release rel;
                 return self.GetNextFrame(timeout_ms);
             },
             py::arg("timeout_ms") = -1)
        .def("frames",
             [](CaptureEngine& self) { return FrameIterator{&self}; })
        // recording
        .def("start_recording",
             [](CaptureEngine& self, const std::string& base_path,
                const std::string& encoder) {
                 RecordingInfo info;
                 { py::gil_scoped_release rel;
                   info = self.StartRecording(base_path, encoder); }
                 py::dict d;
                 d["base_path"]  = info.base_path;
                 d["video_path"] = info.video_path;
                 d["meta_path"]  = info.meta_path;
                 d["codec"]      = info.codec;
                 d["width"]      = info.width;
                 d["height"]     = info.height;
                 return d;
             },
             py::arg("base_path"),
             py::arg("encoder") = "")
        .def("start_recording_split",
             [](CaptureEngine& self,
                const std::string& base_path,
                const std::string& video_path,
                const std::string& meta_path,
                const std::string& encoder) {
                 RecordingInfo info;
                 { py::gil_scoped_release rel;
                   info = self.StartRecording(base_path, video_path,
                                              meta_path, encoder); }
                 py::dict d;
                 d["base_path"]  = info.base_path;
                 d["video_path"] = info.video_path;
                 d["meta_path"]  = info.meta_path;
                 d["codec"]      = info.codec;
                 d["width"]      = info.width;
                 d["height"]     = info.height;
                 return d;
             },
             py::arg("base_path"),
             py::arg("video_path"),
             py::arg("meta_path"),
             py::arg("encoder") = "")
        .def("stop_recording", [](CaptureEngine& self) {
            py::gil_scoped_release rel;
            self.StopRecording();
        })
        .def("is_recording",   &CaptureEngine::IsRecording)
        // diagnostics
        .def("stats",
             [](CaptureEngine& self) {
                 auto s = self.GetStats();
                 py::dict d;
                 d["frames_seen"]     = s.frames_seen;
                 d["frames_accepted"] = s.frames_accepted;
                 d["frames_dropped_queue_full"] =
                     s.frames_dropped_queue_full;
                 d["frames_dropped_internal_error"] =
                     s.frames_dropped_internal_error;
                 d["frames_recorded"]       = s.frames_recorded;
                 d["python_queue_depth"]    = s.python_queue_depth;
                 d["recording_active"]      = s.recording_active;
                 return d;
             })
        .def("get_last_error",
             [](CaptureEngine& self) -> py::object {
                 auto e = self.GetLastError();
                 return e ? py::cast(*e) : py::none();
             })
        .def("submit_analysis_result",
             [](CaptureEngine&, uint64_t, uint32_t, py::object) {
                 // stub
             },
             py::arg("frame_id"), py::arg("flags") = 0,
             py::arg("payload") = py::none());
}
