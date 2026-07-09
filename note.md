# note.md

## 2026-07-09

- 本项目开发板按用户确认走 Wi-Fi 版，当前本地产物为 `build/merged-binary.bin`，适合用 `esptool.py write_flash 0x0` 烧录。
- 调查 `https://www.16302.com/xiaozhiinit`：页面是 Nuxt/Vite 静态前端，烧录核心是浏览器 Web Serial + esptool-js；关键资源包含 `BuS9P53r.js`、`BrZCNVHf.js`、`DU0RAPmS.js`、`D2mnM_UD.js`。
- 已确认页面通过 `navigator.serial.requestPort()` 选设备，最终调用 `writeFlash({ fileArray, flashSize, flashMode, flashFreq, eraseAll:false, compress:true })`，文件项使用 `address: parseInt(offset)`。
- 工程结论：不建议复制第三方站点打包代码做本地产品代码；本项目本机烧录优先用 `esptool.py` 包装成本地脚本，若要浏览器工具再基于开源 `esptool-js` 独立实现。
- Mac 实机烧录验证：WCH 串口为 `/dev/cu.wchusbserial110`，`default_reset` 会失败并报 `Invalid head of packet`；改用 `--before usb_reset` 后可连接 ESP32-S3 并完成写入。
- 新项目 MVP 规格已确定：把小智聊天应用替换为 ESP32-S3 打呼/音频事件记录仪；保留 `zhengchen-1.54tft-wifi` 硬件、Wi-Fi 配网、按钮、音频输入、LCD、电源管理。
- 录音链路设计：ESP 配网后联网校时，进入待机；音量+ 在待机下 toggle 监听/停止；音量- 循环灵敏度阈值；超过阈值后向 Mac HTTP 服务上传 PCM chunk，但 Mac 必须保存为一个录音段一个 `.wav` 文件加一个 `.json` metadata。
- 时间规格：段开始/结束时间使用 RFC3339/ISO8601 UTC，文件名用 `YYYYMMDDTHHMMSSZ_deviceid.wav`；段内 chunk 使用 `offset_ms`，持续时间用 `esp_timer` 单调时间，不用墙钟差值。
- MCU 约束已写入项目 `AGENTS.md`：单片机空间有限，代码必须简洁、固定缓冲/有界队列优先，音频热路径避免堆分配、字符串 churn 和每帧 JSON。
- L1 loop 规则已建立：`snore-recorder-l1-design-review` 为 report-only，只允许读规格/代码并报告发现；禁止 L1 修改 firmware、Mac server、build/sdkconfig/烧录脚本。治理文件：`LOOP.md`、`STATE.md`、`loop-constraints.md`、`loop-budget.md`、`loop-run-log.md`。
- L1 Mac HTTP 存储/回放 contract 已落到 `docs/snore-recorder/mac-http-storage-contract.md`：ESP 传 PCM chunk，Mac 一个段写一个 WAV + 一个 JSON；接口为 `/start`、`/chunk`、`/stop`、列表、metadata、WAV 回放；partial 上传必须 finalize 为可播放 WAV 或删除空段。
- L1 ESP 音频捕获/阈值/上传 contract 已落到 `docs/snore-recorder/esp-audio-capture-upload-contract.md`：MVP 使用 20ms PCM frame、100ms batch、1.5s pre-roll、RMS/peak dBFS、start hold 500ms、silence stop 3000ms；现有 `AudioService::ReadAudioData` 和 `NoAudioCodec::Read` 可定位 PCM 边界，但最终热路径需避免 per-frame vector 分配。
- L1 ESP 时间同步 contract 已落到 `docs/snore-recorder/esp-time-sync-contract.md`：Wi-Fi connected 后进入 TIME_SYNCING，SNTP 成功且 UTC 年 >=2025 才进入 STANDBY；MVP 阻止未校时录制；segment start/end 用 RFC3339 UTC，duration/chunk offset 用 `esp_timer` 单调时间；禁止 fallback 到 OTA time、Mac receive time、build time。
- 静态显示示意图已创建：`docs/snore-recorder/display-mockup.html`，覆盖待机、校时、监听、录制、阈值切换、错误六种 240x240 屏幕状态，用于后续确认 UI 布局，不是固件实现。
- L1 ESP 显示布局 contract 已落到 `docs/snore-recorder/esp-display-layout-contract.md`：240x240 屏分 top/main/bottom 三块；对象预算 <=20；音频柱 8 根、10Hz 上限；时钟/elapsed 1Hz；使用当前 `font_puhui_basic_20_4` 字体，避免聊天气泡、GIF、动态创建对象。
- L2 Slice 1 Mac HTTP 存储/回放服务已实现到 `tools/snore_server/`：`server.py` 提供 `/api/segments/start`、`/chunk`、`/stop`、`/api/segments`、metadata、`/audio/*.wav`、`/` 播放页；`synthetic_client.py` 可上传合成 PCM；服务无外部 Python 依赖。
- Mac HTTP 服务验证：`python3 -m py_compile tools/snore_server/server.py tools/snore_server/synthetic_client.py` 通过；同进程真实 HTTP 测试通过，生成 1 个 16kHz/mono/16-bit WAV + 1 个 JSON，WAV 帧数 16000，API 列表返回 audio_url，HTML 含 `<audio controls>`；乱序 chunk 返回 409，空片段 stop 返回 409 且没有生成假录音文件。
- Mac HTTP 回放页验证：临时启动 `server.py`，运行 `synthetic_client.py` 上传 1000ms 合成 PCM；Playwright 打开 `http://127.0.0.1:8765/`，页面 title 为 `Snore Recorder`，列表显示片段，存在 `<audio preload="metadata">`，音频 URL 返回 HTTP 200、`Content-Type: audio/wav`、大小 32044 bytes。
- L2 Slice 2 录音核心纯逻辑已实现到 `main/recorder/recorder_core.h` 和 `main/recorder/recorder_core.cc`，并接入 `main/CMakeLists.txt`。当前只包含 `LevelDetector`、`TriggerState`、`PreRollBuffer`，不含 Wi-Fi/LVGL/HTTP/AudioService 绑定。
- Slice 2 host 测试已落到 `tools/snore_recorder_tests/recorder_core_test.cc`。验证命令：`c++ -std=c++17 -Wall -Wextra -Werror -I main main/recorder/recorder_core.cc tools/snore_recorder_tests/recorder_core_test.cc -o /tmp/xiaozhi-snore-tests/recorder_core_test && /tmp/xiaozhi-snore-tests/recorder_core_test`，结果 `recorder_core_test passed`。
- Slice 2 固件构建验证：ESP-IDF `5.5` 环境下运行 `idf.py build`，Ninja 实际编译 `recorder/recorder_core.cc.obj` 并成功生成 `build/xiaozhi.bin`；binary size `0x2a93b0`，smallest app partition `0x3f0000`，free `0x146c50`（32%）。
