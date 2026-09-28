# At-Desktop-Assets

Large, SD-card-deployed UI assets for the At-Desktop firmware. Nothing here
lands in NAND directly; `source/ui/pack.ui` stages these trees into
`out/assets/` for deployment to `/mnt/sdcard/dt/assets/`.

## robot_emotion/

AI chat-robot emotion ball animations (Lottie JSON, 160x160 @ 30 fps),
rendered on device by LVGL `lv_lottie` + ThorVG (software engine).

Design references: xAI Grok bot (monochrome ink-on-disc + orbital swoosh
ring), Emotion Ball / grok-ball emotion engine (breathing squash-stretch
body, gaze micro-drift, emotionId taxonomy, enter transitions), Vector/Emo
glossy squircle eye language. Artwork is original.

### Themes

Every emotion ships in two variants, selected by the global `dark_theme`
UI subject (`ui_resources.c`):

- `dark/NN_name.json` — white ink on a near-black disc (default)
- `light/NN_name.json` — dark ink on a white disc

The firmware driver picks the directory automatically and reloads the
running emotion live when the theme is toggled
(`emotion_theme_changed_cb` in
`source/ui/src/components/cards/chat_pages/chat_page.c`).

### Files

Files are named by emotionId: `NN_name.json` — tens digit is the group
(`00` lifecycle, `10` emotions, `30` agent states), matching the Emotion
Ball convention so the AI/backend can switch expressions by id.

| File               | Loop | Used for                               |
|--------------------|------|----------------------------------------|
| `00_sleep.json`    | 5.0s | standby / sleep (Z's, snore bubble)    |
| `02_idle.json`     | 4.0s | `NET_CHAT_STATE_IDLE`                  |
| `10_happy.json`    | 2.0s | happy reaction                         |
| `11_love.json`     | 3.0s | love reaction (heart eyes)             |
| `12_angry.json`    | 2.4s | angry reaction                         |
| `13_surprised.json`| 2.0s | surprised reaction                     |
| `14_sad.json`      | 4.0s | sad reaction (droopy eyes + tear)      |
| `15_confused.json` | 4.0s | `NET_CHAT_STATE_RECONNECTING`          |
| `30_thinking.json` | 3.0s | `NET_CHAT_STATE_THINKING`              |
| `31_listening.json`| 2.4s | `NET_CHAT_STATE_LISTENING`             |
| `32_speaking.json` | 1.6s | `NET_CHAT_STATE_SPEAKING`              |
| `33_scanning.json` | 2.0s | `NET_CHAT_STATE_CONNECTING` (searching)|
| `40_error.json`    | 2.4s | `NET_CHAT_STATE_ERROR` (X eyes)        |
| `41_celebrate.json`| 3.0s | task done (confetti burst)             |

### Playback segments

Every file has the same two segments:

- frames `0..14` — **enter**: uniform elastic squash-and-pop transition,
  played once when the emotion is switched in
- frames `15..op-1` — **loop**: seamless, repeats while the state is active

The firmware driver (`s_chat_emotions` / `emotion_play()` in
`source/ui/src/components/cards/chat_pages/chat_page.c`) skips re-triggering
for an unchanged state and rewinds the animation range to the loop segment
500 ms after a switch, so the enter pop never interrupts a long-lived state
(e.g. continuous listening/speaking).

### Compatibility constraints

Kept deliberately within the ThorVG 0.15.3 feature set used by the device:

- shape layers only (rect / ellipse / path / nested groups)
- solid and linear-gradient fills, round-cap strokes
- keyframed position / scale / rotation / opacity
- **no** expressions, image assets, text, masks/mattes, or trim paths
- lottie paint order is first-item-on-top (features precede the ball plate)

### Regenerating

```
python3 robot_emotion/generate.py
```

`generate.py` is the single source of truth: palette, geometry, timings,
easing, and the emotion definitions. Re-run it after edits, then
`./build.sh ui` (or `source/ui/pack.ui`) to restage the SD assets.
