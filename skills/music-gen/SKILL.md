---
name: music-gen
description: >-
  Generate music from text descriptions using ACE-Step 1.5 locally.
  Use when the user asks to generate music, create a song, compose audio,
  make beats, produce instrumentals, or generate any kind of music/audio content.
argument-hint: <description> [--lyrics <text>] [--duration <secs>] [--output <file>] [--instrumental] [--format mp3|wav|flac]
allowed-tools: Bash Read
user-invocable: true
---

# music-gen: Local AI Music Generation

Generate music from text prompts using ACE-Step 1.5 with SFT DiT model + 1.7B Language Model on Apple Silicon (MLX backend).

## Installation

Binary at `~/.local/share/ace-step-1.5/`. Wrapper script: `generate_music.py`.
Models stored in `~/.local/share/ace-step-1.5/checkpoints/`.

## Command

```bash
cd ~/.local/share/ace-step-1.5 && uv run python generate_music.py \
  --caption "<description>" \
  [options...]
```

**Output paths are printed to stdout** (one per line). Status/progress goes to stderr.

## Parameters

| Flag                | Type   | Default     | Description                                      |
| ------------------- | ------ | ----------- | ------------------------------------------------ |
| `--caption`         | string | *required*  | Music style/mood description                     |
| `--lyrics`          | string | `""`        | Lyrics with structure tags, or path to .txt file |
| `--instrumental`    | flag   | false       | Generate instrumental (no vocals)                |
| `--duration`        | float  | -1 (auto)   | Duration in seconds (10-600)                     |
| `--output`          | string | auto        | Output file path (e.g., `~/Music/song.mp3`)      |
| `--format`          | string | `mp3`       | Audio format: mp3, wav, flac, wav32, opus, aac   |
| `--save-dir`        | string | `./output`  | Output directory (when `--output` not set)       |
| `--seed`            | int    | -1 (random) | Reproducibility seed                             |
| `--batch-size`      | int    | 1           | Number of variations to generate                 |
| `--bpm`             | int    | auto        | Tempo (30-300)                                   |
| `--key`             | string | auto        | Musical key (e.g., "C Major", "Am")              |
| `--time-sig`        | string | auto        | Time signature (2/4, 3/4, 4/4, 6/8)              |
| `--language`        | string | auto        | Vocal language code (en, zh, ja, ko, fr, etc.)   |
| `--inference-steps` | int    | 50          | Diffusion steps (50 for SFT)                     |
| `--guidance-scale`  | float  | 7.0         | Prompt adherence strength                        |
| `--no-thinking`     | flag   | false       | Disable LM reasoning (faster, lower quality)     |
| `--verbose`         | flag   | false       | Show detailed logs                               |

## Lyrics Format

Use structure tags to organize lyrics:

```
[Verse]
Walking down the street at night
Stars are shining oh so bright

[Chorus]
We're alive, we're free tonight
Dancing under city lights

[Bridge]
And the world keeps spinning round

[Outro]
Fading out into the sound
```

For instrumental: use `--instrumental` flag or set lyrics to `[Instrumental]`.

## Argument Handling

Parse `$ARGUMENTS` as follows:
- Bare text (no flags) = the caption/description
- `--lyrics <text>` = lyrics content or path to .txt file
- `--duration <N>` = duration in seconds; default auto
- `--output <file>` = output file path; default auto-generated in ./output/
- `--format <fmt>` = audio format; default mp3
- `--instrumental` = generate instrumental music
- `--seed <N>` = seed for reproducibility
- `--batch-size <N>` = number of variations
- `--bpm <N>` = tempo
- `--key <str>` = musical key
- `--no-thinking` = skip LM reasoning for faster generation

## Workflow

1. Parse the user's request to extract: description, lyrics, duration, output path, format, and musical parameters
2. If the user provides lyrics inline, write them to a temp file first
3. Construct the `generate_music.py` command with appropriate flags
4. Run the command (generation takes 1-5 minutes depending on duration)
5. Parse stdout for output file paths
6. Report the output file path(s) and generation time to the user

## Examples

**Simple instrumental:**
```bash
cd ~/.local/share/ace-step-1.5 && uv run python generate_music.py \
  --caption "chill lo-fi hip hop beat with jazzy piano and vinyl crackle" \
  --instrumental --duration 120 --format mp3 \
  --output ~/Music/lofi-beat.mp3
```

**Song with lyrics:**
```bash
cd ~/.local/share/ace-step-1.5 && uv run python generate_music.py \
  --caption "upbeat indie pop with acoustic guitar and hand claps" \
  --lyrics /tmp/my-lyrics.txt --duration 180 --format flac \
  --output ~/Music/indie-pop.flac
```

**Quick generation (no LM):**
```bash
cd ~/.local/share/ace-step-1.5 && uv run python generate_music.py \
  --caption "epic orchestral trailer music" \
  --instrumental --duration 60 --no-thinking \
  --output ~/Music/epic-trailer.mp3
```

**Multiple variations:**
```bash
cd ~/.local/share/ace-step-1.5 && uv run python generate_music.py \
  --caption "funky disco groove" \
  --instrumental --duration 30 --batch-size 3 \
  --save-dir ~/Music/disco-variations/
```

## Notes

- First run may take extra time to download models (~10GB total)
- Generation with LM thinking takes 2-5 minutes depending on duration
- With `--no-thinking`, generation is faster but quality/coherence may be lower
- The SFT model uses 50 inference steps by default for best quality
- Output files are printed to stdout for easy parsing
- All progress/status messages go to stderr
