# ESP 240x240 Display Layout Contract

## Purpose

Define the MVP display contract for the ESP snore/audio recorder on the `zhengchen-1.54tft-wifi` 240x240 ST7789 LCD.

This document is a design contract only. It does not implement firmware code.

## Source Evidence

- Target board display size is `DISPLAY_WIDTH 240` and `DISPLAY_HEIGHT 240` in `main/boards/zhengchen-1.54tft-wifi/config.h`.
- Target board uses ST7789 SPI LCD through `ZHENGCHEN_LcdDisplay -> SpiLcdDisplay -> LcdDisplay`.
- LVGL SPI display buffer is `width * 20` pixels, single buffered, RGB565, DMA-capable internal RAM in `main/display/lcd_display.cc`.
- `zhengchen-1.54tft-wifi` currently selects `font_puhui_basic_20_4` and `font_awesome_20_4` in `main/CMakeLists.txt`.
- `font_puhui_basic_20_4` line height is `25`; `font_awesome_20_4` line height is `23`.
- Static mockup is `docs/snore-recorder/display-mockup.html` and has been accepted as direction.

## Hard Display Limits

```text
screen_width = 240 px
screen_height = 240 px
color_format = RGB565
lvgl_buffer = 240 * 20 px = 4800 px = 9600 bytes
double_buffer = false
```

Rules:

- Avoid full-screen high-frequency redraws.
- Avoid GIFs, large images, scrolling chat bubbles, and dynamic object creation in the recorder UI.
- Prefer fixed LVGL objects updated in place.
- Display update frequency for audio animation must be capped.

## UI Regions

Recommended layout:

```text
0..31     top bar: network, time/date, battery
32..199   main area: state, time/level bars, elapsed/error
200..239  bottom bar: threshold, hint, failure instruction
```

Region heights:

```text
top_bar_h = 32
bottom_bar_h = 40
main_h = 168
```

Rules:

- Top and bottom bars are always allocated, even if bottom text is empty.
- Main area changes content by state, but does not recreate whole screen per frame.
- Use a dark background for contrast and lower visual noise at night.

## Object Budget

Keep the recorder screen under this approximate LVGL object budget:

```text
screen/container: 1
top bar: 1
top labels: 3
main container: 1
main labels: 3
audio bars: 8
bottom bar: 1
bottom label: 1
optional error badge/dot: 1
total target: <= 20 objects
```

Rules:

- Create all objects once during setup.
- Hide/show or update text/height/color in place.
- Do not create/delete bars per audio frame.
- Do not use chat message containers for recorder status.

## Fonts

Current board font selection:

```text
text_font = font_puhui_basic_20_4   line_height 25
icon_font = font_awesome_20_4       line_height 23
```

MVP text sizing rule:

- Use current text font for most labels.
- Use label scaling/alternate built-in font only if already available without adding large font assets.
- Do not add new large C font assets for MVP unless current font is unreadable on hardware.

Approximate text roles:

```text
top labels:     existing 20px font, short text only
main status:    existing 20px font, bold/colored pill if possible
time display:   use existing font first; avoid adding huge font until hardware review
bottom hint:    existing 20px font may be tight; keep text short
```

Chinese copy must be short because 240px width is limited.

## States And Required Text

### `TIME_SYNCING`

Top:

```text
Wi-Fi | 联网 | battery
```

Main:

```text
--:--
校时中
```

Bottom:

```text
未校时不录制
```

### `STANDBY`

Top:

```text
Wi-Fi | date or HH:MM | battery
```

Main:

```text
HH:MM
待机
```

Bottom:

```text
中 -40dBFS
```

### `MONITORING`

Top:

```text
Wi-Fi | HH:MM:SS | battery
```

Main:

```text
8 audio bars
监听中
当前 -43dBFS
```

Bottom:

```text
阈值 -40dBFS
```

### `RECORDING`

Top:

```text
Wi-Fi | HH:MM:SS | battery
```

Main:

```text
8 audio bars
录制中 00:12
上传中
```

Bottom:

```text
静音3s结束
```

### `THRESHOLD_CHANGED`

This is an overlay/state message shown for about 1200 ms after volume-.

Main:

```text
灵敏度
高 -45dBFS
```

Bottom:

```text
超高→高→中→低
```

### `ERROR`

Main:

```text
上传失败
服务器不可达
```

Bottom:

```text
音量+返回
```

Rules:

- Never show `保存成功` unless Mac finalized the segment or explicitly returned playable partial.
- Network/time/upload errors must be visible and not overwritten immediately by normal clock refresh.

## Audio Bars

Bars:

```text
bar_count = 8
bar_width = 10..12 px
bar_gap = 4..5 px
bar_max_h = 88 px
bar_min_h = 4 px
```

Mapping:

```text
normalized = clamp((rms_dbfs - floor_dbfs) / (ceil_dbfs - floor_dbfs), 0, 1)
floor_dbfs = -60
ceil_dbfs = -20
bar_height = bar_min_h + normalized * (bar_max_h - bar_min_h)
```

Rules:

- Animation input uses RMS/peak stats from recorder audio, independent of trigger state.
- Update bars at max `10 Hz`.
- Use a small smoothing filter to avoid harsh flicker:
  ```text
  shown = shown * 0.65 + target * 0.35
  ```
- Color may change to amber when `rms_dbfs >= threshold_dbfs`.

## Refresh Rates

```text
clock label:       1 Hz
record elapsed:    1 Hz
audio bars:        <= 10 Hz
threshold overlay: event-based, about 1200 ms
network/battery:   event or low-rate polling
```

Rules:

- Do not update LVGL from the audio interrupt/hot path.
- Audio task should publish compact level stats; UI task consumes latest stats.
- Dropping intermediate animation samples is allowed.
- Dropping recording/upload state transitions is not allowed.

## Color Contract

Use a simple night-safe palette:

```text
background: near black / dark green
normal:     green
sync:       cyan/blue
recording:  amber + red dot
error:      red
text:       off-white
```

Rules:

- Avoid bright white full-screen backgrounds at night.
- Error red is reserved for actual failure.
- Recording should be visually distinct from monitoring.

## Power Save Behavior

- In `STANDBY`, screen may dim after board power-save timeout.
- In `MONITORING` and `RECORDING`, keep screen awake unless Jason later requests screen-off night mode.
- Button press wakes display before applying action.

## L2 Implementation Shape

Preferred owner:

```text
RecorderDisplayController
```

Responsibilities:

- Own recorder-specific LVGL objects.
- Render state transitions.
- Update audio bars from latest level stats.
- Render threshold overlay.
- Render hard errors.

It should not:

- Own audio detection.
- Own HTTP upload.
- Own time sync.
- Create chat bubbles.

## Readiness Findings

- Current generic `LcdDisplay` is chat-oriented. Recorder UI should not reuse chat message container behavior as the main layout.
- Existing SPI LVGL buffer is small and single-buffered, so recorder animation must be lightweight and bounded.
- Current selected Chinese font line height is 25 px, so bottom text must be short; long explanatory strings will crowd the screen.

## Verification Gates For Future L2

Implementation is not complete until:

- Hardware screen shows all six states: time sync, standby, monitoring, recording, threshold change, error.
- Audio bars update smoothly without creating LVGL objects per frame.
- Text is readable on the 240x240 physical display.
- Error message persists long enough to diagnose upload/time/network failure.
- Screen remains responsive while audio capture and upload are active.

