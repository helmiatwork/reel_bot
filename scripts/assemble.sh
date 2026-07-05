#!/usr/bin/env bash
# assemble.sh — render a narrated compilation from an EDL JSON (from auto-editor / editor agent).
# Deterministic: the agent decides the edit, this script just runs ffmpeg.
#
#   ./assemble.sh edl.json final.mp4
#
# EDL shape:
#   { title, aspect:"1080x1920", fps:30,
#     clips:[{src,in,out}], voiceover:"vo.mp3",
#     music:{file,gain_db}, sfx:[{file,at,gain_db}], captions:[{start,end,text}] }
#
# Needs: ffmpeg, ffprobe, jq.
set -euo pipefail

EDL="${1:?usage: assemble.sh <edl.json> <output.mp4>}"
OUT="${2:?usage: assemble.sh <edl.json> <output.mp4>}"
command -v jq >/dev/null     || { echo "need jq"; exit 1; }
command -v ffmpeg >/dev/null || { echo "need ffmpeg"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ASPECT=$(jq -r '.aspect // "1080x1920"' "$EDL")
FPS=$(jq -r '.fps // 30' "$EDL")
W="${ASPECT%x*}"; H="${ASPECT#*x}"

# ---- 1. cut + normalize each clip to the same codec/size/fps ----
echo "[1/5] cutting clips → 9:16 ${ASPECT}@${FPS}"
n=$(jq '.clips | length' "$EDL")
: > "$WORK/list.txt"
for i in $(seq 0 $((n-1))); do
  src=$(jq -r ".clips[$i].src" "$EDL")
  in=$(jq -r ".clips[$i].in"  "$EDL")
  out=$(jq -r ".clips[$i].out" "$EDL")
  dur=$(awk "BEGIN{print $out-$in}")
  part="$WORK/part_$(printf %03d $i).mp4"
  ffmpeg -nostdin -y -loglevel error -ss "$in" -t "$dur" -i "$src" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},setsar=1,fps=${FPS}" \
    -an -c:v libx264 -preset veryfast -pix_fmt yuv420p "$part"
  echo "file '$part'" >> "$WORK/list.txt"
done

# ---- 2. concat video track ----
echo "[2/5] concat video"
ffmpeg -nostdin -y -loglevel error -f concat -safe 0 -i "$WORK/list.txt" \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p "$WORK/video.mp4"
VDUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/video.mp4")

# ---- 3. captions → SRT ----
echo "[3/5] captions → srt"
SRT="$WORK/cap.srt"; : > "$SRT"
cn=$(jq '.captions | length' "$EDL")
ts(){ awk "BEGIN{t=$1;h=int(t/3600);m=int((t%3600)/60);s=t-int(t/60)*60;printf \"%02d:%02d:%06.3f\",h,m,s}" | sed 's/\./,/'; }
for i in $(seq 0 $((cn-1))); do
  st=$(jq -r ".captions[$i].start" "$EDL"); en=$(jq -r ".captions[$i].end" "$EDL")
  tx=$(jq -r ".captions[$i].text" "$EDL")
  { echo $((i+1)); echo "$(ts "$st") --> $(ts "$en")"; echo "$tx"; echo; } >> "$SRT"
done

# ---- 4. build audio mix: VO + music(gain) + sfx(adelay+gain) ----
echo "[4/5] mixing audio (VO + music + SFX)"
# NOTE: ffmpeg input 0 is the video track; audio inputs therefore start at input
# index 1. The filtergraph must reference [$((idx+1)):a], not [$idx:a].
INPUTS=(); FC=""; LABELS=""; idx=0
VO=$(jq -r '.voiceover // empty' "$EDL")
if [ -n "$VO" ]; then INPUTS+=(-i "$VO"); FC+="[$((idx+1)):a]aresample=44100[a$idx];"; LABELS+="[a$idx]"; idx=$((idx+1)); fi
MUSIC=$(jq -r '.music.file // empty' "$EDL")
if [ -n "$MUSIC" ]; then
  mg=$(jq -r '.music.gain_db // -18' "$EDL")
  INPUTS+=(-i "$MUSIC"); FC+="[$((idx+1)):a]volume=${mg}dB,aresample=44100[a$idx];"; LABELS+="[a$idx]"; idx=$((idx+1))
fi
sn=$(jq '.sfx | length' "$EDL")
for j in $(seq 0 $((sn-1)) 2>/dev/null || true); do
  [ "$sn" -eq 0 ] && break
  f=$(jq -r ".sfx[$j].file" "$EDL"); at=$(jq -r ".sfx[$j].at" "$EDL"); g=$(jq -r ".sfx[$j].gain_db // -6" "$EDL")
  ms=$(awk "BEGIN{print int($at*1000)}")
  INPUTS+=(-i "$f"); FC+="[$((idx+1)):a]volume=${g}dB,adelay=${ms}|${ms},aresample=44100[a$idx];"; LABELS+="[a$idx]"; idx=$((idx+1))
done

if [ "$idx" -gt 0 ]; then
  FC+="${LABELS}amix=inputs=${idx}:duration=longest:normalize=0[aout]"
  ffmpeg -nostdin -y -loglevel error -i "$WORK/video.mp4" "${INPUTS[@]}" \
    -filter_complex "$FC" -map 0:v -map "[aout]" \
    -c:v copy -c:a aac -shortest "$WORK/mixed.mp4"
else
  cp "$WORK/video.mp4" "$WORK/mixed.mp4"
fi

# ---- 5. burn captions → final ----
echo "[5/5] burn captions → $OUT"
HAS_SUBS=$(ffmpeg -hide_banner -filters 2>/dev/null | grep -c ' subtitles ' || true)
if [ "$cn" -gt 0 ] && [ "$HAS_SUBS" -gt 0 ]; then
  ffmpeg -nostdin -y -loglevel error -i "$WORK/mixed.mp4" \
    -vf "subtitles=${SRT}:force_style='Fontsize=16,Bold=1,Alignment=2,MarginV=120,Outline=2'" \
    -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a copy "$OUT"
else
  [ "$cn" -gt 0 ] && echo "  (ffmpeg has no 'subtitles' filter / libass — shipping without burned captions; SRT kept at $SRT)"
  cp "$WORK/mixed.mp4" "$OUT"
  [ "$cn" -gt 0 ] && cp "$SRT" "${OUT%.mp4}.srt" 2>/dev/null || true
fi

echo "done → $OUT  (video ${VDUR}s, ${n} clips)"
