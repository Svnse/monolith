# Monolith

Stop chatting with AI. Start commanding it.

A local-first AI workstation for running LLMs, Stable Diffusion, and audio generation through a modular kernel.

## Quick Start

**Windows:**
1. Clone repo
2. Run `install.bat`
3. Run `start.bat`

**Linux/Mac:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Status

Early alpha. Built for myself. Sharing in case others want it.

## Features

- Local LLM chat (GGUF models via llama.cpp)
- Stable Diffusion image generation
- Audio generation (via AudioCraft)
- Persistent chat history
- Modular kernel architecture
- Dark mode

## Requirements

- Python 3.10+
- CUDA GPU recommended (for SD/Audio)
- ~10GB disk space for models

## Architecture

Kernel + Engines + Addons model.

Engines run isolated processes. Addons control them. Kernel enforces contracts.

See `/monokernel/kernel_contract.md` for details or V2 (current).

---

Built by Eryndel | eryndel.us
