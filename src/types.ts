export type Page = 'project'|'render'|'library'|'settings';
export type ProjectStatus = 'validating'|'queued'|'rendering'|'done'|'error'|'interrupted';
export type DurationMode = 'exact'|'whole-track';
export type LoopMode = 'image'|'crossfade'|'pingpong'|'original';
export type EffectMode = 'chromakey'|'luma'|'screen';
export type EncoderPreference = 'auto'|'quality'|'speed';
export type EffectUsageMode = 'off'|'always'|'interval';
export type SubscribeFirstAppearance = 'after-interval'|'immediate'|'custom';

export interface AnchorPoint {
  x: number;
  y: number;
  width?: number;
  height?: number;
  source?: 'manual'|'auto';
  confidence?: number;
}
export type SceneAnchors = Record<string, AnchorPoint>;

export interface ProjectScanItem {
  id: string;
  name: string;
  path: string;
  media: string[];
  audio: string[];
  valid: boolean;
  error?: string;
  anchors?: SceneAnchors;
  selectedEffectId?: string;
}

export interface RenderProject extends ProjectScanItem {
  status: ProjectStatus;
  progress: number;
  stage: string;
  startedAt?: number;
  elapsedSec: number;
  etaSec?: number;
  resultPath?: string;
  resultBytes?: number;
  actualVideoBitrate?: number;
  cpuPct?: number;
  ramBytes?: number;
  ramTotalBytes?: number;
  ramAvailableBytes?: number;
  gpuPct?: number;
  engineTimings?: Record<string,number>;
  encoder?: string;
  attempt?: number;
  smartSize?: boolean;
  targetVideoKbps?: number;
  originalFidelity?: boolean;
  audioOriginal?: boolean;
  audioLossless?: boolean;
}

export interface EffectPreset {
  id: string;
  name: string;
  source: string;
  enabled: boolean;
  mode: EffectMode;
  keyColor: string;
  similarity: number;
  blend: number;
  despill: number;
  lumaThreshold: number;
  lumaTolerance: number;
  saturation: number;
  x: number;
  y: number;
  scale: number;
  fullscreen: boolean;
  previewFrameTime: number;
  startSec: number;
  endSec: number | null;
  cacheKey?: string;
  cacheReady?: boolean;
  usageMode?: EffectUsageMode;
  intervalSec?: number;
  usageDurationSec?: number;
  target?: string;
  offsetX?: number;
  offsetY?: number;
  opacity?: number;
}

export interface SubscribePreset extends EffectPreset {
  firstAtSec: number;
  secondAtSec: number;
  repeatEverySec: number;
  firstAppearance?: SubscribeFirstAppearance;
  customFirstAtSec?: number;
  showDurationSec?: number;
}

export interface RenderSettings {
  width: number;
  height: number;
  fps: 24|30|60;
  codec: 'h264'|'h265';
  bitrateMbps: number;
  durationHours: number;
  durationMode: DurationMode;
  loopMode: LoopMode;
  crossfadeSec: number;
  normalizeLufs: boolean;
  outputDir: string;
  preset: 'ultrafast'|'superfast'|'fast'|'medium';
  encoderPreference: EncoderPreference;
}

export interface BackgroundMusicSettings {
  volumePct: number;
  bassDb: number;
  midDb: number;
  trebleDb: number;
}

export interface LibraryPayload {
  effects: EffectPreset[];
  subscribes: SubscribePreset[];
  ambient?: string;
  ambientSettings?: Partial<BackgroundMusicSettings>;
}

export interface RecoveryPayload {
  interrupted?: boolean;
  active?: QueueJob | null;
  pending?: QueueJob[];
  interruptedProjectName?: string;
}

export interface QueueJob {
  project: ProjectScanItem;
  settings: RenderSettings;
  effects: EffectPreset[];
  subscribes: SubscribePreset[];
  ambient?: string;
  ambientSettings: BackgroundMusicSettings;
}

export interface BenchmarkResult {
  selected?: string | null;
  candidates: Array<{encoder:string;ok:boolean;listed?:boolean;seconds?:number|null;note?:string}>;
  successful?: number;
  platform: string;
  arch?: string;
  ffmpegProbeOk?: boolean;
  ffmpegProbeError?: string | null;
}

export interface LicenseStatus {
  valid: boolean;
  type?: 'owner-lifetime'|'monthly'|'trial'|'development';
  plan?: string|null;
  licenseId?: string|null;
  licenseStatus?: 'active'|'paused'|'revoked'|'expired'|string|null;
  expiresAt?: string | null;
  maskedKey?: string;
  deviceId?: string|null;
  deviceRecordId?: string|null;
  deviceStatus?: 'active'|'blocked'|'detached'|string|null;
  realtimeTopic?: string|null;
  connection?: 'online'|'offline-grace'|'offline-blocked'|'blocked'|'not-activated'|string;
  connectionError?: string|null;
  reason?: string|null;
  code?: string|null;
  lastServerOkAt?: number|null;
  offlineUntil?: string | null;
}
