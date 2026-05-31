# Agent Routing Rules

## Quick Reference

| Intent signal | Route to |
|---------------|----------|
| buat video, create reel, bikin konten, make content | reelbot |
| riset, research, trending, tren, competitor, saingan | researcher |
| script, caption, hook, judul, tulis, write | writer |
| analytics, performa, views, engagement, insight | analyst |
| error, broken, gagal, tidak jalan, help debug | support |
| (everything else) | assistant |

## Handoff Format

When routing, always say:
> "Menghubungkan ke [Agent Name]... / Routing to [Agent Name]..."

Then hand off the full context including the original user message.

## Escalation

If an agent cannot handle the request after 2 attempts, route to `assistant` with a summary of what was tried.
