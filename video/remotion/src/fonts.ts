import {continueRender, delayRender, staticFile} from 'remotion';

// Local copies of the Google Fonts files mock4.html loads (Schibsted Grotesk variable 400-700, Barlow Condensed 700),
// so rendering needs no network. Japanese falls back to Hiragino Sans from the system.
const faces: Array<[string, string, string, string]> = [
  ['Schibsted Grotesk', 'fonts/schibsted-latin.woff2', '400 700', 'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD'],
  ['Schibsted Grotesk', 'fonts/schibsted-latin-ext.woff2', '400 700', 'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF'],
  ['Barlow Condensed', 'fonts/barlowc-700-latin.woff2', '700', 'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD'],
  ['Barlow Condensed', 'fonts/barlowc-700-latin-ext.woff2', '700', 'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF'],
];

let loaded = false;
export const loadFonts = (): void => {
  if (loaded || typeof document === 'undefined') return;
  loaded = true;
  const handle = delayRender('fonts');
  Promise.all(
    faces.map(([family, file, weight, range]) => {
      const f = new FontFace(family, `url(${staticFile(file)}) format('woff2')`, {weight, unicodeRange: range});
      (document.fonts as unknown as {add: (x: FontFace) => void}).add(f);
      return f.load();
    }),
  )
    .then(() => continueRender(handle))
    .catch((e) => {
      console.error('font load failed', e);
      continueRender(handle);
    });
};
