# AGENTS.md — Content Automation Pipeline Agents

## Agent: orchestrator
**Role:** Entry point. Receives all Telegram messages and routes to correct pipeline.

**Triggers:**
- User sends a YouTube URL → start research pipeline
- User sends a topic/keyword → start research pipeline with search
- User sends "approve {run_id}" → trigger publish
- User sends "stats" or "analytics" → show dashboard link
- User sends "status" → show what is currently running

**Tools:**
- http: GET http://pipeline-api:8000/health
- http: GET http://pipeline-api:8000/analytics/summary

**On receiving a YouTube URL or topic:**
1. Extract the URL or topic from the message
2. Identify requested platforms (default: youtube)
3. Extract preferred voice if mentioned (default: male_neutral)
4. POST to pipeline-api with:
   ```json
   {
     "topic": "user's angle/topic",
     "user_id": "telegram_user_id",
     "platforms": ["youtube"],
     "voice": "male_neutral"
   }
   ```
5. Reply: "⏳ Starting pipeline for: [topic]. I'll update you at each step."

**On receiving "stats":**
1. GET http://pipeline-api:8000/analytics/summary
2. Format and reply with totals + top insights
3. Add: "Full dashboard: https://analytics.general-creation.xyz"

---

## Agent: researcher
**Role:** Searches YouTube, extracts transcripts, understands video content.

**Model:** gemini/gemini-2.5-flash (1M context window for long transcripts)

**Called by:** orchestrator

**Input:**
```json
{
  "youtube_url": "https://youtube.com/... or search URL",
  "topic": "user's angle"
}
```

**Process:**
1. Use yt-dlp to search or fetch video metadata
2. Try to get transcript (manual subs → auto-captions → Whisper)
3. If no transcript, use video-analyzer on frames
4. Extract: title, key points, story structure, tone, pacing, style

**Output:**
```json
{
  "source_video": { "title": "...", "url": "...", "channel": "..." },
  "transcript_excerpt": "first 2000 chars...",
  "key_points": ["point1", "point2"],
  "tone": "educational",
  "style": "documentary",
  "text_source": "auto_captions"
}
```

---

## Agent: content-writer
**Role:** Writes original scripts inspired by research. Never copies source content.

**Model:** gemini/gemini-2.5-flash (best writing quality)

**Called by:** orchestrator after researcher completes

**Rules:**
- ALWAYS write completely original content — never paraphrase the source
- Match the emotional tone and pacing of the source video
- Include timestamps and B-roll suggestions for each scene
- Write for the platform (YouTube = longer, TikTok = punchy, Instagram = hook-first)
- Inject analytics feedback if available from GET /analytics/feedback

**Input:**
```json
{
  "research": { ... researcher output ... },
  "topic": "user's angle",
  "analytics_feedback": "optional previous performance insights"
}
```

**Output:**
```json
{
  "title": "...",
  "hook": "first sentence that grabs attention",
  "tone": "educational/funny/dramatic",
  "estimated_duration_min": 8,
  "segments": [
    {
      "title": "segment title",
      "narration": "full narration text",
      "broll_suggestion": "what to show visually",
      "duration_sec": 60
    }
  ],
  "conclusion": "...",
  "cta": "call to action",
  "instagram_caption": "...",
  "tiktok_caption": "max 150 chars",
  "twitter": "max 280 chars",
  "tags": ["tag1", "tag2"]
}
```

---

## Agent: seo
**Role:** Generates optimized metadata for each platform.

**Model:** gemini/gemini-2.5-flash (cheapest — simple text task)

**Called by:** orchestrator after content-writer

**Generates:**
- YouTube: title (60 chars), description (5000 chars), tags (30 max), chapters
- TikTok: caption (150 chars), hashtags (30 max)
- Instagram: caption (2200 chars), hashtags (30 max)

**Input:** script JSON from content-writer

**Output:**
```json
{
  "youtube": {
    "title": "...",
    "description": "...",
    "tags": ["..."],
    "chapters": [{"time": "0:00", "title": "Intro"}]
  },
  "tiktok": { "caption": "...", "hashtags": ["..."] },
  "instagram": { "caption": "...", "hashtags": ["..."] }
}
```

---

## Agent: publisher
**Role:** Handles post-publish tasks and user notifications.

**Model:** gemini/gemini-2.5-flash (simple task)

**Called by:** orchestrator after pipeline-api /publish endpoint completes

**Responsibilities:**
1. Format publish results into readable Telegram message
2. Save final analytics record via POST /analytics/save
3. Send summary to user

**Telegram message format:**
```
✅ Video published!

📹 {title}
📺 YouTube: {url} (private — review before making public)
🎵 TikTok: check inbox for draft
📸 Instagram: published as Reel

📊 Quality score: {score}/100
⏱ Total time: {minutes} minutes

View analytics: https://analytics.general-creation.xyz
```
