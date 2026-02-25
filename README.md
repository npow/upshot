# upshot

[![CI](https://github.com/npow/upshot/actions/workflows/ci.yml/badge.svg)](https://github.com/npow/upshot/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/upshot)](https://pypi.org/project/upshot/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Get the key takeaways from all your newsletters and feeds in one daily briefing.

## The problem

You subscribe to 10+ newsletters and RSS feeds. Every morning you face a wall of overlapping content — three sources covering the same story, buried insights mixed with filler. You either spend an hour triaging or give up and miss things that matter.

## Quick start

```bash
pip install upshot
upshot add https://example-newsletter.substack.com
upshot run
upshot digest
```

## Install

```bash
pip install upshot
```

From source:

```bash
git clone https://github.com/npow/upshot.git
cd upshot
pip install -e ".[dev]"
```

## Usage

Run the full pipeline for today:

```bash
upshot run
```

Add a newsletter or blog feed:

```bash
upshot add https://simonwillison.net
```

View today's briefing:

```bash
upshot digest
```

Run specific stages (e.g., just re-synthesize):

```bash
upshot run --stages synthesize --no-resume
```

## How it works

```
Gmail + RSS feeds
       ↓
    ingest        Fetch new emails and feed items
       ↓
    extract       Pull articles, resolve URLs, fetch full text
       ↓
   transcribe     Whisper transcription for podcasts
       ↓
   deduplicate    Embed content → cluster by similarity
       ↓
   synthesize     Single Claude call → cohesive markdown briefing
```

All content is deduplicated by semantic similarity, then sent to Claude in one call. Claude synthesizes a briefing grouped by theme — not by source — with inline links to the originals.

## Configuration

Copy and edit `config.yaml`:

```yaml
claude:
  model: "sonnet"
  base_url: "http://localhost:18082"  # claude-relay
  max_briefing_words: 80000

gmail:
  labels: ["Newsletters"]

dedup:
  distance_threshold: 0.35
```

Set secrets via environment variables:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GMAIL_CREDENTIALS_PATH=credentials.json
```

## Development

```bash
git clone https://github.com/npow/upshot.git
cd upshot
pip install -e ".[dev]"
pytest -v
```

## License

[Apache-2.0](LICENSE)
