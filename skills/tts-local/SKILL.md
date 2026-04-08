---
name: tts-local
description: Generate speech from text using local TTS models. Routes to kitten-tts (English) or qwen3-tts (non-English / voice cloning). Use when the user asks to generate speech, convert text to audio, read text aloud, or do voice cloning.
argument-hint: <text> [--lang <code>] [--voice <name>] [--output <file>] [--ref_audio <file>] [--speed <n>] [--fast] [--format mp3|wav]
allowed-tools: Bash Read
---

# tts-local: Local Text-to-Speech

Generate speech from text using locally installed TTS models.

## Routing Rules

| Condition | Engine | Why |
|-----------|--------|-----|
| English text, no voice cloning | **kitten-tts** | Fastest, best English quality |
| Non-English text (any language) | **qwen3-tts** | Multilingual support (52 languages) |
| Voice cloning (any language, including English) | **qwen3-tts** | Supports `--ref_audio` for zero-shot cloning |

## Engine 1: kitten-tts (English only)

Binary at `~/.cargo/bin/kitten-tts`. Model at `~/.local/share/kitten-tts/kitten-tts-mini/`.

```bash
kitten-tts ~/.local/share/kitten-tts/kitten-tts-mini "<text>" \
  --voice <voice> \
  --speed <speed> \
  --output <output_file>
```

**Voices**: Bella, Jasper, Luna, Bruno (default), Rosie, Hugo, Kiki, Leo
**Default output**: `output.wav`

**Note**: kitten-tts only outputs WAV. For MP3 output, generate WAV first then convert (see Post-Processing section).

## Engine 2: qwen3-tts (Multilingual + Voice Cloning)

Installed as global uv tool `mlx-audio`. Two model variants available:

| Variant | Path | Params | Size | Use when |
|---------|------|--------|------|----------|
| **1.7B CustomVoice** (default) | `~/.local/share/qwen3-tts/models/1.7B-CustomVoice` | 1.7B | 4.2 GB | Best quality, emotion control, voice cloning |
| **0.6B Base** (fast) | `~/.local/share/qwen3-tts/models/0.6B` | 0.6B | 2.4 GB | When user wants `--fast` or speed over quality |

**Default**: Use 1.7B-CustomVoice unless the user passes `--fast`.

### Standard synthesis (non-English)

```bash
# Default (1.7B CustomVoice)
mlx_audio.tts.generate \
  --model ~/.local/share/qwen3-tts/models/1.7B-CustomVoice \
  --text "<text>" \
  --voice <voice> \
  --lang_code <lang_code> \
  --output_path <output_dir> \
  --file_prefix <prefix> \
  --audio_format wav

# Fast mode (0.6B Base)
mlx_audio.tts.generate \
  --model ~/.local/share/qwen3-tts/models/0.6B \
  --text "<text>" \
  --voice <voice> \
  --lang_code <lang_code> \
  --output_path <output_dir> \
  --file_prefix <prefix> \
  --audio_format wav
```

**1.7B CustomVoice voices**: serena (default), vivian, uncle_fu, ryan, aiden, ono_anna, sohee, eric, dylan
**0.6B Base voices**: Chelsie (default), Ethan, Vivian
**Lang codes**: zh (Mandarin), en (English), ja (Japanese), ko (Korean), fr (French), de (German), es (Spanish), etc.

**Note**: Output files get a `_000` suffix automatically (e.g., `output_000.wav`).

### Voice cloning (any language)

Always uses 1.7B CustomVoice (ignore `--fast` for cloning tasks).

```bash
mlx_audio.tts.generate \
  --model ~/.local/share/qwen3-tts/models/1.7B-CustomVoice \
  --text "<text>" \
  --ref_audio <path_to_reference_wav> \
  --ref_text "<transcript of reference audio>" \
  --lang_code <lang_code> \
  --output_path <output_dir> \
  --file_prefix <prefix> \
  --audio_format wav
```

When `--ref_audio` is provided, the model clones the voice from the reference audio. The `--ref_text` should be the transcript of the reference audio for best results. If the user doesn't provide a transcript, omit `--ref_text` and the STT model will auto-transcribe it.

### Emotion / style control

Use `--instruct` to control emotion and speaking style (1.7B CustomVoice only):

```bash
mlx_audio.tts.generate \
  --model ~/.local/share/qwen3-tts/models/1.7B-CustomVoice \
  --text "<text>" \
  --voice serena \
  --instruct "Speak with excitement and energy" \
  --lang_code zh \
  --output_path . \
  --file_prefix output \
  --audio_format wav
```

## Post-Processing: MP3 Conversion

**Default output format is MP3** for smaller file size (~85% reduction vs WAV). Both engines produce WAV natively, so always convert to MP3 after generation unless the user explicitly requests WAV via `--format wav`.

```bash
# Convert WAV to MP3 using ffmpeg (VBR quality 4 ≈ 128-165 kbps)
ffmpeg -i input.wav -codec:a libmp3lame -q:a 4 output.mp3 -y -loglevel error

# Then remove the intermediate WAV
rm input.wav
```

For kitten-tts workflow:
```bash
# 1. Generate WAV (kitten-tts only outputs WAV)
kitten-tts ~/.local/share/kitten-tts/kitten-tts-mini "<text>" \
  --voice Hugo --output /tmp/_tts_temp.wav

# 2. Convert to MP3
ffmpeg -i /tmp/_tts_temp.wav -codec:a libmp3lame -q:a 4 output.mp3 -y -loglevel error

# 3. Clean up temp WAV
rm /tmp/_tts_temp.wav
```

For qwen3-tts workflow:
```bash
# 1. Generate WAV
mlx_audio.tts.generate --model ~/.local/share/qwen3-tts/models/1.7B-CustomVoice \
  --text "<text>" --voice serena --lang_code en \
  --output_path /tmp --file_prefix _tts_temp --audio_format wav

# 2. Convert to MP3
ffmpeg -i /tmp/_tts_temp_000.wav -codec:a libmp3lame -q:a 4 output.mp3 -y -loglevel error

# 3. Clean up temp WAV
rm /tmp/_tts_temp_000.wav
```

## Argument Handling

Parse `$ARGUMENTS` as follows:
- Bare text (no flags) → the text to synthesize
- `--lang <code>` → language code; if omitted, auto-detect from text content
- `--voice <name>` → voice name; defaults depend on engine
- `--output <file>` → output file path; default `output.mp3` (was `output.wav`)
- `--format <mp3|wav>` → output format; default `mp3`. Use `wav` only if user explicitly requests it
- `--ref_audio <file>` → reference audio for voice cloning (forces qwen3-tts)
- `--ref_text <text>` → transcript of reference audio
- `--speed <n>` → speech speed multiplier (kitten-tts only)
- `--fast` → use 0.6B Base model instead of 1.7B CustomVoice (faster, lower quality; ignored for voice cloning)
- `--instruct <text>` → emotion/style instruction (qwen3-tts 1.7B CustomVoice only)
- `--play` → play audio after generation (qwen3-tts only)
- `--stream` → stream audio in real-time (qwen3-tts only)

## Language Auto-Detection

If no `--lang` is specified:
- If text contains only ASCII / Latin characters → English → **kitten-tts**
- If text contains CJK characters (Chinese, Japanese, Korean) → detect specific language → **qwen3-tts**
- If text contains other non-Latin scripts → **qwen3-tts**
- If `--ref_audio` is provided → always **qwen3-tts** regardless of language

## Workflow

1. Parse the user's request to extract: text, language, voice, output path, format, reference audio
2. Apply routing rules to select engine
3. Construct and run the TTS command (always generates WAV internally)
4. If output format is MP3 (default): convert WAV→MP3 with ffmpeg, remove temp WAV
5. Report the output file path, format, and duration to the user
