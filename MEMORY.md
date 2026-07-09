# MEMORY.md

## ESP32-S3 Wi-Fi Board Build And Flash

- 当前已验证板型：`zhengchen-1.54tft-wifi`。
- 当前已验证编译环境：ESP-IDF `v5.5.2`，Python venv `~/esp/esp-idf-venv`，IDF 路径 `~/esp/esp-idf`。
- 当前已验证编译命令：
  ```bash
  cd /Users/fanzhang/Documents/github/xiaozhi-esp32-2.2.4
  . ~/esp/esp-idf-venv/bin/activate
  export IDF_PYTHON_ENV_PATH=$HOME/esp/esp-idf-venv
  . ~/esp/esp-idf/export.sh
  python scripts/release.py zhengchen-1.54tft-wifi
  ```
- 当前已验证产物：`build/merged-binary.bin`，大小 `9981049` bytes，SHA256 `a1e5fb1407deec53dc1e59469bee6512dc45b57f49f7732e6c18cb80fd44445e`。
- Mac 本机烧录优先用 `scripts/flash_zhengchen_wifi.sh /dev/cu.wchusbserialXXXX`，底层写入 `0x0 build/merged-binary.bin`。
- 当前板子的 WCH USB 串口在 macOS 下需要 `CH34xVCPDriver`，并且 esptool 连接必须用 `--before usb_reset`；`default_reset` 已验证会报 `Invalid head of packet`。
- `https://www.16302.com/xiaozhiinit` 在线页本质是 Web Serial + esptool-js 烧录器，不是必须依赖的固件下载器；本地工具不应复制其打包代码，优先复用本项目产物和 ESP 官方/开源烧录工具链。

## Snore Recorder MVP Specification

- 项目方向：将 XiaoZhi ESP32 固件改造为 ESP32-S3 Wi-Fi 打呼/音频事件记录仪，保留 `zhengchen-1.54tft-wifi` 板级硬件、Wi-Fi 配网、按钮、音频输入、LCD、电源管理，替换原聊天应用层。
- MVP 状态机：`BOOT -> PROVISIONING -> WIFI_CONNECTING -> TIME_SYNCING -> STANDBY -> MONITORING -> RECORDING -> ERROR`。
- 控制规则：音量+ 在待机下 toggle 监听/停止；录音中按音量+ 要先结束当前段；音量- 循环灵敏度阈值并在屏幕底部显示。
- MVP 音频格式：ESP 上传 PCM `16 kHz / 16-bit / mono` chunk；Mac HTTP 服务必须把一个录音段写成一个可播放 `.wav` 文件，并配一个 `.json` metadata 文件。
- 时间规则：Wi-Fi 连接后必须独立 SNTP 校时，不依赖小智 OTA；段开始/结束时间用 RFC3339/ISO8601 UTC；文件名用 `YYYYMMDDTHHMMSSZ_deviceid.wav`；段内 chunk 用 `offset_ms`，持续时间用 `esp_timer` 单调时间。
- MCU 编码约束：空间有限，代码要简洁；音频热路径优先固定缓冲和有界队列，避免堆分配、频繁字符串构造、每帧 JSON、重型 UI 资源和无必要抽象。
- L1 loop 已定为 `snore-recorder-l1-design-review` report-only：运行前读 `LOOP.md`、`STATE.md`、`loop-constraints.md`、`loop-budget.md`、`loop-run-log.md`；L1 只允许检查和报告，禁止修改 firmware、Mac server、build/sdkconfig、烧录脚本或启动后台任务。
- Mac HTTP 存储/回放 contract 真源：`docs/snore-recorder/mac-http-storage-contract.md`。MVP 使用 `POST /api/segments/start`、`POST /api/segments/{segment_id}/chunk`、`POST /api/segments/{segment_id}/stop`；ESP 上传 raw PCM chunk，Mac 写单个 playable WAV 和 JSON metadata，partial 上传必须 finalize 为 playable partial 或删除空段。
- Mac HTTP 存储/回放实现真源：`tools/snore_server/server.py`，验证客户端：`tools/snore_server/synthetic_client.py`。当前实现无外部 Python 依赖，默认端口 `8765`，默认目录 `recordings/`，浏览器入口 `GET /`。
- Mac HTTP 服务已验证：真实 HTTP start/chunk/stop 可生成一个 16kHz/mono/16-bit playable WAV 和一个 matching JSON；`GET /api/segments` 返回 audio_url；`GET /` 渲染 `<audio controls>`；Playwright 已验证浏览器页面列出片段，audio URL 返回 HTTP 200、`audio/wav`、32044 bytes；乱序 chunk 被 409 拒绝且不重排；空片段 stop 被 409 拒绝且不生成假录音。
- ESP 音频捕获/阈值/上传 contract 真源：`docs/snore-recorder/esp-audio-capture-upload-contract.md`。MVP 使用 `20ms` PCM frame、`100ms` upload batch、`1500ms` pre-roll、RMS/peak dBFS、`500ms` start hold、`3000ms` silence stop；最终实现需避免音频热路径 per-frame heap allocation/string/JSON。
- ESP 录音核心纯逻辑实现真源：`main/recorder/recorder_core.h` 和 `main/recorder/recorder_core.cc`。当前 owner 只覆盖 `LevelDetector`、`TriggerState`、`PreRollBuffer`，禁止在此层引入 Wi-Fi、LVGL、HTTP client 或 AudioService 绑定。
- ESP 录音核心 host 测试真源：`tools/snore_recorder_tests/recorder_core_test.cc`。已验证 RMS/peak dBFS、静音 floor、`int16_t` 最小值峰值、500ms start hold 正反、3000ms silence stop 正反、button stop、max duration、75 帧 pre-roll oldest-to-newest 顺序。
- ESP 录音核心固件构建已验证：`idf.py build` 实际编译 `recorder/recorder_core.cc.obj` 并成功生成 `build/xiaozhi.bin`；binary size `0x2a93b0`，smallest app partition `0x3f0000`，free `0x146c50`（32%）。
- ESP 时间同步 contract 真源：`docs/snore-recorder/esp-time-sync-contract.md`。Wi-Fi connected 后进入 `TIME_SYNCING`，SNTP 成功且 UTC 年 >=2025 才进入 `STANDBY`；MVP 阻止未校时录制；segment wall time 用 RFC3339 UTC，duration/chunk offset 用 `esp_timer` 单调时间；禁止 fallback 到 OTA time、Mac receive time、build time。
- ESP 显示布局 contract 真源：`docs/snore-recorder/esp-display-layout-contract.md`；已确认静态 mockup `docs/snore-recorder/display-mockup.html`。240x240 UI 分 top/main/bottom 三块，对象预算 <=20，音频柱 8 根，动画 <=10Hz，时钟/elapsed 1Hz，避免聊天气泡、GIF、动态创建 LVGL 对象。

## Repository Baseline

- Git upstream: `https://github.com/Jasonzhangf/snoreDetector.git`.
- Local branch: `main`, tracking `origin/main`.
- Initial pushed commit: `4f60ade feat: initialize snore detector firmware`.
- Commit hygiene baseline: do not commit `build/`, `build.*`, `build.stale-*`, `managed_components/`, `releases/`, `recordings/`, `sdkconfig`, `dependencies.lock`, generated `lang_config.h`, `.DS_Store`, `__pycache__/`, `*.pyc`, `*.bin`, `*.elf`, `*.map`, or `*.zip`.
- Pre-push verification used for the baseline: host recorder core test passed, Python snore server py_compile passed, clean `idf.py build` passed for ESP32-S3 and generated `build/xiaozhi.bin`, then build artifacts were removed before commit.
