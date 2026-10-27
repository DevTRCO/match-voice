#!/usr/bin/env python3
"""Level the baked commentary files used in the film: static gain to a target loudness, then a peak limiter.
The page plays them unlevelled (-16 to -29 LUFS); in the film a quiet line would drown under the founder.
Writes public/audio/story-lv/<ch>-<m>.wav. Usage: level-voices.py <ch-m> ...  (goal calls end in -162)."""
import re, subprocess, sys
SRC = '/Users/vmt/MicroSaaS/match-voice/ui/public/insert/story-audio'
DST = '/Users/vmt/MicroSaaS/match-voice/video/remotion/public/audio/story-lv'
def loud(path):
    e = subprocess.run(['ffmpeg', '-hide_banner', '-i', path, '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', e)[-1])
for k in sys.argv[1:]:
    target = -13.0 if k.endswith('-162') else -18.0  # goal calls lifted 2026-10-27: above the founder (-16 + master)
    i = loud(f'{SRC}/{k}.mp3')
    g = target - i
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'{SRC}/{k}.mp3', '-af', f'volume={g:.2f}dB,alimiter=limit={0.71 if k.endswith("-162") else 0.79}:attack=2:release=40:level=disabled',
                    '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', f'{DST}/{k}.wav'], check=True)
    print(k, f'{i:.1f} LUFS', f'gain {g:+.1f} dB', '->', f'{loud(f"{DST}/{k}.wav"):.1f} LUFS')
