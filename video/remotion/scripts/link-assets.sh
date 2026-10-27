#!/bin/sh
# Remotion copies public/ into its bundle and does not follow symlinks, so assets are HARD links (same volume, no extra space).
# Re-run after any source file is re-made: a re-made file is a new inode and the old hard link keeps the stale copy.
# A story-audio file deleted at the source stays here until removed by hand.
set -e
R=/Users/vmt/MicroSaaS/match-voice
P="$R/video/remotion/public"
mkdir -p "$P/faces" "$P/founder" "$P/audio/story-audio" "$P/shots"
for f in A B C D1 D2 D3; do
  if [ -f "$R/video/founder/${f}_blur.mp4" ]; then
    ln -f "$R/video/founder/${f}_blur.mp4" "$P/founder/${f}_blur.mp4"
  else
    echo "missing ${f}_blur.mp4 (never use the unblurred take)"
  fi
done
for f in "$R"/ui/public/insert/story-audio/*.mp3; do ln -f "$f" "$P/audio/story-audio/"; done
for f in "$R"/ui/public/faces/*.jpg; do ln -f "$f" "$P/faces/"; done
ln -f "$R/ui/public/audio/stadium-roar.mp3" "$P/audio/stadium-roar.mp3"
for f in "$R"/video/shots/*.mp4; do
  [ -f "$f" ] && ln -f "$f" "$P/shots/"
done
# crowd bed, low-passed like mock4.html (BiquadFilter lowpass 900 Hz, Q 1 dB = 1.122 linear), from 40 s of the file like the page
if [ ! -f "$P/audio/stadium-bed-lp900.wav" ]; then
  ffmpeg -y -loglevel error -ss 40 -t 160 -i "$R/ui/public/audio/stadium-bed.mp3" \
    -af "lowpass=f=900:width_type=q:width=1.122,afade=t=in:d=0.02" -ar 48000 -ac 2 -c:a pcm_s16le "$P/audio/stadium-bed-lp900.wav"
fi
echo ok
