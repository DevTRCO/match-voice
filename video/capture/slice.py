"""Cut S2 and S3 out of the en/expert master take (M_enx) frame-exact, with their own logs.
python3 slice.py
"""
import json, subprocess, os

SH = '/Users/vmt/MicroSaaS/match-voice/video/shots'
FPS = 30


def first_frame(ws, w):
    for s in ws:
        if s['w'] is not None and s['w'] >= w - 1e-6:
            return s['f']
    return ws[-1]['f']


def cut(master, out, fa, fb, note):
    M = json.load(open(f'{SH}/{master}.json'))
    t0, t1 = fa / FPS, fb / FPS  # [fa, fb)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'{SH}/{master}.mp4', '-vf', f'trim=start_frame={fa}:end_frame={fb},setpts=PTS-STARTPTS',
                    '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-movflags', '+faststart', f'{SH}/{out}.mp4'], check=True)
    ev = M['audioEvents']
    carry = []
    # audio elements already sounding at the slice start: a synthetic play at 0 with the offset they have reached
    state = {}
    for e in ev:
        if e['tS'] >= t0 - 1e-9:
            break
        state.setdefault(e['src'], []).append(e)
    for src, es in state.items():
        if src == 'audio/stadium-bed.mp3':
            g = [e for e in es if e['ev'] == 'gain']
            st = [e for e in es if e['ev'] == 'bedstart']
            if st:
                carry.append({'tS': 0.0, 'src': src, 'ev': 'bedstate', 'offsetS': round(40 + (t0 - st[-1]['tS']), 4), 'synthetic': True,
                              'lastGain': g[-1] if g else None, 'note': 'bed running since master tS %.4f; last gain event shown (master time)' % st[-1]['tS']})
            continue
        # one element per create; take the last element of this src
        last = es[-1]
        plays = [e for e in es if e['ev'] in ('play', 'seek')]
        if last['ev'] in ('play', 'seek') and plays:
            p = plays[-1]
            off = (p['offsetS'] or 0) + (t0 - p['tS'])
            dur = next((e.get('dur') for e in reversed(es) if e.get('dur')), None)
            if dur is None or off < dur:
                carry.append({'tS': 0.0, 'src': src, 'ev': 'play', 'offsetS': round(off, 4), 'volume': p.get('volume'), 'dur': dur, 'synthetic': True})
    inside = [dict(e, tS=round(e['tS'] - t0, 4)) for e in ev if t0 - 1e-9 <= e['tS'] < t1 - 1e-9]
    cues = []
    for c in M['subtitleCues']:
        a, b = max(c['startS'], t0), min(c['endS'], t1)
        if b > a + 1e-6:
            cues.append(dict(c, startS=round(a - t0, 4), endS=round(b - t0, 4), clippedStart=c['startS'] < t0 - 1e-9, clippedEnd=c['endS'] > t1 + 1e-9))
    O = dict(M)
    O.update(id=out, frames=fb - fa, durationS=round((fb - fa) / FPS, 4), frame0Epoch=M['frame0Epoch'] + t0 * 1000,
             slicedFrom={'take': master, 'startFrame': fa, 'endFrameExclusive': fb, 'startS': round(t0, 4), 'note': note},
             audioEvents=carry + inside,
             wSamples=[dict(s, f=s['f'] - fa, tS=round(s['tS'] - t0, 4)) for s in M['wSamples'][fa:fb]],
             frameState=[dict(s, f=s['f'] - fa) for s in M['frameState'][fa:fb]], subtitleCues=cues)
    json.dump(O, open(f'{SH}/{out}.json', 'w'), indent=1, ensure_ascii=False)
    print(out, fa, fb, (fb - fa) / FPS, 's', len(cues), 'cues')


def end_frame(M):
    e = [x['f'] for x in M['frameState'] if x['end']]
    return min(M['frames'], (e[0] + 60) if e else M['frames'])


M = json.load(open(f'{SH}/M_enx.json'))
ws = M['wSamples']
# S2: the idle start screen (2 s handle), Play, scene 1 card, set-up and montage, the story line; ends on the last frame before the dark cut (w 16.0)
cut('M_enx', 'S2_scene1_analysis_enx', 0, first_frame(ws, 16.0), 'idle start screen 2 s, Play at frame 60, scene 1 through the story line, ends before the cut to scene 2')
# S3: 2 s before the scene 2 card (w 14.0) through the end of the clip and 2 s of the end card
cut('M_enx', 'S3_scene2_goal_enx', first_frame(ws, 14.0), end_frame(M), 'w 14.0 (2 s before the scene 2 card) to the end of the clip plus 2 s of the end card')
# S5: the whole en/beginner run, idle 2 s to the end of the clip plus 2 s of the end card (same clock as M_enx: frame n of S5 = frame n of M_enx)
B = json.load(open(f'{SH}/M_enb.json'))
cut('M_enb', 'S5_en_beginner', 0, end_frame(B), 'whole en/beginner run, same frame clock as M_enx (Play at frame 60)')
