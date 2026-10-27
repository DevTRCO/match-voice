// Reads the real recorded run (ui/public/insert/story.json) at bundle time. Nothing here is typed by hand
// except the English glosses, which are translations for the viewer.
import story from '../../../../ui/public/insert/story.json';

type Msg = {k: string; ch?: number; m?: number; step?: string; agent?: string; text?: string; who?: string; t?: number; c?: string; d?: {key?: string; text?: string; why?: string}};
const msgs = (story as unknown as {messages: Msg[]}).messages;
const channels = (story as unknown as {hello: {channels: {id: number; key: string; lead: {name: string}}}}).hello.channels as unknown as {
  id: number;
  key: string;
  lead: {name: string};
}[];

export const channelId = (key: string): number => {
  const c = channels.find((x) => x.key === key);
  if (!c) throw new Error(`no channel ${key}`);
  return c.id;
};

export const leadOf = (key: string): string => channels.find((x) => x.key === key)?.lead.name ?? '';

/** Match minute shown on the board at story time t (last frame message at or before t). */
export const minuteAt = (t: number): string => {
  const f = msgs.filter((m) => m.k === 'f' && (m.t ?? 0) <= t && m.c).pop();
  return f?.c ?? '';
};

export type VerifierCatchData = {
  key: string;
  moment: number;
  minute: string;
  rejected: string;
  why: string;
  accepted: string;
  acceptedBy: string;
};

/** The verifier rejection of `key` and the accepted line for the same moment. Throws if the log changed. */
export const verifierCatch = (key: string, flaggedWord: string): VerifierCatchData => {
  const rej = msgs.find((m) => m.k === 'log' && m.step === 'rejected' && m.d?.key === key && (m.d?.text ?? '').includes(flaggedWord));
  if (!rej || rej.m == null) throw new Error(`no rejection for ${key} with '${flaggedWord}' in story.json`);
  const ch = channelId(key);
  const ok = msgs.find((m) => m.k === 'say' && m.ch === ch && m.m === rej.m);
  if (!ok) throw new Error(`no accepted line for ${key} moment ${rej.m}`);
  return {
    key,
    moment: rej.m,
    minute: minuteAt(rej.t ?? 0),
    rejected: rej.d!.text!,
    why: rej.d!.why!,
    accepted: ok.text!,
    acceptedBy: ok.who ?? leadOf(key),
  };
};
