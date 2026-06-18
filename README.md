# Kids Daily Story Agent

A standalone LangGraph agent that creates personalized children's stories for parents, pauses for human approval, and sends the approved story by email.

## What It Demonstrates

- Stateful LangGraph workflow
- LangGraph interrupt and checkpointing for parent approval
- Child profile memory
- Pinecone-backed story history
- Same-child repetition detection
- Safety and reading-level validation
- Human-in-the-loop approval
- Revision feedback loop
- Guarded email sending
- Optional calls to existing MCP tools
- Optional OpenAI Image MCP illustration generation
- Nebius Token Factory / Nebius AI Studio as the default LLM provider

## Run

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run src\story_app.py --server.port 8502
```

By default, email runs in mock mode and logs the send result locally.

## Daily 8:30 PM Email

The daily scheduler entry point generates one story for `demo-child`, approves it for the scheduled job, sends the email, and records the date locally so a rerun will not send duplicates.

Run it once manually:

```bash
.\.venv\Scripts\python.exe -m src.daily_story_job
```

Register it with Windows Task Scheduler for 8:30 PM:

```powershell
$action = New-ScheduledTaskAction -Execute "$PWD\.venv\Scripts\python.exe" -Argument "-m src.daily_story_job" -WorkingDirectory "$PWD"
$trigger = New-ScheduledTaskTrigger -Daily -At 8:30PM
Register-ScheduledTask -TaskName "KidsDailyStoryAgent" -Action $action -Trigger $trigger -Description "Send the daily kids story email at 8:30 PM."
```

## Gmail SMTP Setup

The agent sends real email through Gmail SMTP only after parent approval.

For demos, keep:

```text
STORY_AGENT_MOCK_EMAIL=true
```

For real Gmail sending, create a Gmail app password, then set:

```text
STORY_AGENT_MOCK_EMAIL=false
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_character_app_password
STORY_AGENT_FROM_EMAIL=your_email@gmail.com
```

Gmail SMTP defaults are used automatically:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

The email node still refuses to send unless the parent clicks **Approve and Send**.

## OpenAI Image Setup

After parent approval, the graph creates a child-safe illustration prompt and tries to generate a story image. If an existing OpenAI Image MCP endpoint is configured, the agent calls that MCP tool:

```text
OPENAI_IMAGE_MCP_URL=http://localhost:3001/mcp
OPENAI_IMAGE_MCP_TRANSPORT=streamable_http
OPENAI_IMAGE_MCP_TOOL_NAME=generate_image
```

This project includes a local OpenAI image MCP adapter:

```bash
.\.venv\Scripts\python.exe src\openai_image_mcp_server.py
```

That server exposes a `generate_image` MCP tool and calls the OpenAI Images API using `OPENAI_API_KEY` from `.env`.

If no MCP endpoint is configured, the agent can use the OpenAI Images API directly:

```text
OPENAI_API_KEY=your_openai_api_key
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1024x1024
OPENAI_IMAGE_QUALITY=low
```

The image step is non-blocking for the workflow. If image generation is not configured or fails, the approved story email still sends. If the image tool returns a URL, the email includes that URL. If it returns base64 image data, the agent saves the image under `data/generated_images` and embeds it inline in the HTML email.

## ElevenLabs Audio Setup

Parents can optionally check **Include audio narration** before approving a story. When selected, the agent creates an MP3 narration with ElevenLabs and attaches it to the same email.

```text
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
```

Audio files are saved under `data/story_agent/story_audio`.

## Nebius Setup

Copy `.env.example` to `.env` and set your Nebius key:

```text
LLM_PROVIDER=nebius
NEBIUS_API_KEY=your_nebius_api_key
NEBIUS_BASE_URL=https://api.studio.nebius.com/v1
LLM_MODEL=Qwen/Qwen3-30B-A3B
```

The agent calls the Nebius OpenAI-compatible chat completions endpoint for story generation. If no Nebius key is configured, the app falls back to a deterministic local story so the human-approval workflow still demos correctly.

## Pinecone Setup

Story history is stored in Pinecone. Each approved/sent story is embedded and upserted with metadata including `child_id`, `story_id`, theme, characters, setting, summary, and story text.

```text
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=kids-daily-story-history
PINECONE_DIMENSION=384
PINECONE_AUTO_CREATE_INDEX=false
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
```

Create the Pinecone index with dimension `384` and metric `cosine`, or set `PINECONE_AUTO_CREATE_INDEX=true` and provide the cloud/region values.

The similarity query is filtered by child:

```text
filter={"child_id": {"$eq": current_child_id}}
```

So a similar story can be used for another child, but the same child will not repeatedly receive a similar story.

## Mem0 Setup

Mem0 is optional long-term child preference memory. It uses the same stable `child_id` as Pinecone so both systems refer to the same child:

```text
Pinecone metadata child_id = demo-child
Pinecone vector id = demo-child:story-202606...
Mem0 user_id = demo-child
```

Set:

```text
MEM0_API_KEY=your_mem0_api_key
```

Pinecone is still used for story similarity and repetition checks. Mem0 is used for durable preferences such as favorite character types, themes, parent feedback, reading level, and story style.

## Agent Flow

```text
Load child profile
-> Load recent stories
-> Choose daily theme
-> Generate story with Nebius
-> Validate story and query Pinecone for same-child repetition
-> Ask parent for approval
-> Approve/send, revise, or reject
-> Generate optional illustration with OpenAI Image MCP or OpenAI Images API
-> Upsert story history into Pinecone
```

## Human Approval

The agent never sends an email unless the parent chooses **Approve and Send**. If the parent requests a revision, the feedback is stored in graph state and routed back into the story generation node.

The approval step uses LangGraph `interrupt()` with a `MemorySaver` checkpointer. The graph pauses at the human review node, stores state under a `thread_id`, and resumes the same graph thread when the parent chooses approve, revise, or reject.

## Optional MCP

This project does not create an MCP server. If you already have a remote MCP server, set `STORY_AGENT_MCP_URL` in `.env`. The app can then call Gmail-style MCP tools such as `search_threads` and `get_thread` to check for approval replies.
