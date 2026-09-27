# Models: the T7, Hugging Face, Qwen and DeepSeek

The ending first: **nothing in the build changes.** Ollama stays the runner.
Hugging Face is the library the models come from. The T7 is where they
live. Qwen is the model today; DeepSeek is a model name you type later.

## What each thing is, in one line

| Thing | What it is here |
| --- | --- |
| **Ollama** | The program on the Mac that runs a model. Homei talks to it and nothing else. |
| **Hugging Face** | The public library of model files. Ollama can fetch from it directly. No account needed to download. |
| **Qwen** | The model family Homei uses now: `qwen3:4b` to talk, `qwen3-embedding:0.6b` to index. |
| **DeepSeek** | Another model family. The full one is far too big for any laptop. The small ones that run on a Mac are `deepseek-r1:7b` and `deepseek-r1:14b`. |
| **T7** | The external drive. Already the weekly backup. It can also hold the models, so the Mac's own disk does not fill. |

## What was right in the plan

- One local runner, one swap point (`Model` in `workers/cxi_spine.py`),
  nothing leaves the machine. That holds for every model named here.
- The T7 as the backup drive.

## What was missing

1. **Where the models live.** Each model is 2 to 9 GB. Ollama puts them on
   the Mac's disk unless told otherwise. One setting moves them to the T7.
2. **Which DeepSeek.** "Homei on DeepSeek" has to mean a small one.
   Nothing else fits in a Mac's memory.
3. **Hugging Face is not a separate step.** Ollama pulls from it by name.
   No new program, no new account, no new plan.
4. **Order.** Models before corpus before seats. `MAC_SESSION_1.md` already
   has that order; this file only adds the T7 setting to its Job 3.

## The steps, in order

Each step has one check. Do the next step only when the check passes.

1. **Plug in the T7.** Check: `/Volumes/T7` exists in Finder.
2. **Tell Ollama to keep models on the T7.** Once, in Terminal or by Claude Code on the Mac:
   ```sh
   mkdir -p /Volumes/T7/ollama
   launchctl setenv OLLAMA_MODELS /Volumes/T7/ollama
   ```
   Then quit and reopen the Ollama app. Check: `ollama list` runs and shows an empty list (or the models already moved).
3. **Fetch the two Qwen models.**
   ```sh
   ollama pull qwen3:4b
   ollama pull qwen3-embedding:0.6b
   ```
   Check: `ollama list` shows both, and `/Volumes/T7/ollama/blobs` is not empty.
4. **Fetch a DeepSeek for later.** Pick by the Mac's memory:

   | Mac memory | DeepSeek to pull | Qwen to talk with |
   | --- | --- | --- |
   | 8 GB | `deepseek-r1:7b` (tight) | `qwen3:4b` |
   | 16 GB | `deepseek-r1:7b` | `qwen3:8b` |
   | 32 GB or more | `deepseek-r1:14b` | `qwen3:14b` |

   Check: `ollama run deepseek-r1:7b "say ready"` answers.
5. **Swap Homei to it when you want to.** No code. One setting in the shell
   that starts the spine: `CXI_CHAT_MODEL=deepseek-r1:7b ./scripts/start.sh`.
   Check: Homei's log line names the model.
6. **Any other model on Hugging Face.** Same runner, one line:
   `ollama pull hf.co/<owner>/<repo>` for any repo that ships GGUF files.
   Check: `ollama list` shows it.

## The one thing to know

If the T7 is unplugged, Ollama has no models and Homei goes quiet until it
is plugged back in. The spine, the chat, the register and Handi keep
running; only the model seat waits.
