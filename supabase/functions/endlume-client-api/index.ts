import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const db = createClient(URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-endlume-session",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Content-Type": "application/json",
  "Cache-Control": "no-store",
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: CORS });
const now = () => new Date();
const iso = () => now().toISOString();
const clamp = (n: unknown, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number(n) || 0));

async function sha256Hex(value: string) {
  const bytes = new TextEncoder().encode(value);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function normalizeKey(value: unknown) {
  return String(value ?? "").trim().toUpperCase().replace(/\s+/g, "");
}
function randomToken() {
  const b = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
function effectiveStatus(license: any) {
  if (!license) return "missing";
  if (license.status !== "active") return license.status;
  if (!license.owner && license.plan !== "owner" && license.expires_at && Date.parse(license.expires_at) <= Date.now()) return "expired";
  return "active";
}
async function expireIfNeeded(license: any) {
  const status = effectiveStatus(license);
  if (status === "expired" && license.status === "active") {
    await db.from("endlume_licenses").update({ status: "expired", updated_at: iso() }).eq("id", license.id);
    license.status = "expired";
  }
  return status;
}
async function authSession(req: Request) {
  const token = req.headers.get("x-endlume-session")?.trim() ?? "";
  if (!token) return { ok: false as const, code: "session_missing" };
  const tokenHash = await sha256Hex(token);
  const { data: session, error } = await db.from("endlume_sessions").select("*").eq("token_hash", tokenHash).maybeSingle();
  if (error || !session) return { ok: false as const, code: "session_invalid" };
  if (session.revoked_at || Date.parse(session.expires_at) <= Date.now()) return { ok: false as const, code: "session_expired" };
  const [{ data: license }, { data: device }] = await Promise.all([
    db.from("endlume_licenses").select("*").eq("id", session.license_id).maybeSingle(),
    db.from("endlume_devices").select("*").eq("id", session.device_id).maybeSingle(),
  ]);
  if (!license || !device) return { ok: false as const, code: "binding_missing" };
  if (String(device.license_id) !== String(session.license_id)) return { ok: false as const, code: "binding_mismatch" };
  const licenseStatus = await expireIfNeeded(license);
  const allowed = licenseStatus === "active" && device.status === "active";
  return { ok: true as const, tokenHash, session, license, device, licenseStatus, allowed };
}
function publicState(a: any) {
  return {
    allowed: a.allowed,
    licenseId: a.license.id,
    licenseStatus: a.licenseStatus,
    plan: a.license.plan,
    owner: !!a.license.owner,
    expiresAt: a.license.expires_at,
    maxDevices: a.license.max_devices,
    deviceRecordId: a.device.id,
    deviceId: a.device.device_id,
    deviceStatus: a.device.status,
    realtimeTopic: a.license.realtime_topic,
    serverTime: iso(),
  };
}
async function activate(body: any) {
  const rawKey = String(body.key ?? "");
  if (rawKey.length > 128) return json({ ok: false, code: "key_format" }, 400);
  const key = normalizeKey(rawKey);
  const deviceId = String(body.device_id ?? "").trim();
  const platform = String(body.platform ?? "").trim().toLowerCase();
  const architecture = String(body.architecture ?? "").trim().toLowerCase();
  const appVersion = String(body.app_version ?? "").trim();
  const deviceName = String(body.device_name ?? "").trim().slice(0, 160) || null;
  const parts = key.split("-");
  const validKey = parts[0] === "ENDLUME" && (parts.length === 5 || parts.length === 9) && parts.slice(1).every((g) => /^[A-Z0-9]{4}$/.test(g));
  if (!validKey) return json({ ok: false, code: "key_format" }, 400);
  if (!deviceId || deviceId.length > 160 || !platform || !architecture || !appVersion) return json({ ok: false, code: "device_metadata" }, 400);
  const keyHash = await sha256Hex(key);
  const { data: license, error } = await db.from("endlume_licenses").select("*").eq("key_hash", keyHash).maybeSingle();
  if (error) return json({ ok: false, code: "db_error" }, 500);
  if (!license) return json({ ok: false, code: "key_invalid" }, 401);
  const licenseStatus = await expireIfNeeded(license);
  if (licenseStatus !== "active") return json({ ok: false, code: `license_${licenseStatus}`, licenseStatus }, 403);

  let { data: device } = await db.from("endlume_devices").select("*").eq("license_id", license.id).eq("device_id", deviceId).maybeSingle();
  if (device?.status === "blocked") return json({ ok: false, code: "device_blocked" }, 403);
  if (!device || device.status === "detached") {
    const { count } = await db.from("endlume_devices").select("id", { count: "exact", head: true }).eq("license_id", license.id).in("status", ["active", "blocked"]);
    if ((count ?? 0) >= license.max_devices) return json({ ok: false, code: "device_limit", maxDevices: license.max_devices }, 409);
  }
  const stamp = iso();
  const { data: bound, error: bindError } = await db.from("endlume_devices").upsert({
    license_id: license.id,
    device_id: deviceId,
    status: "active",
    platform,
    architecture,
    app_version: appVersion,
    device_name: deviceName,
    last_seen_at: stamp,
    last_heartbeat_at: stamp,
    updated_at: stamp,
  }, { onConflict: "license_id,device_id" }).select("*").single();
  if (bindError || !bound) return json({ ok: false, code: "device_bind_failed" }, 500);
  device = bound;

  await db.from("endlume_sessions").update({ revoked_at: stamp }).eq("device_id", device.id).is("revoked_at", null);
  const token = randomToken();
  const tokenHash = await sha256Hex(token);
  const sessionExpires = new Date(Date.now() + 30 * 86400_000).toISOString();
  const { data: session, error: sessionError } = await db.from("endlume_sessions").insert({
    license_id: license.id,
    device_id: device.id,
    token_hash: tokenHash,
    expires_at: sessionExpires,
  }).select("id").single();
  if (sessionError || !session) return json({ ok: false, code: "session_create_failed" }, 500);
  await db.from("endlume_licenses").update({ last_seen_at: stamp, updated_at: stamp }).eq("id", license.id);
  return json({ ok: true, sessionToken: token, sessionExpiresAt: sessionExpires, ...publicState({ allowed: true, license, device, licenseStatus: "active" }) });
}
async function status(req: Request) {
  const a = await authSession(req);
  if (!a.ok) return json({ ok: false, allowed: false, code: a.code }, 401);
  return json({ ok: true, ...publicState(a) });
}
async function heartbeat(req: Request, body: any) {
  const a = await authSession(req);
  if (!a.ok) return json({ ok: false, allowed: false, code: a.code }, 401);
  const stamp = iso();
  const progress = body.progress == null ? null : clamp(body.progress, 0, 100);
  await Promise.all([
    db.from("endlume_sessions").update({ last_seen_at: stamp }).eq("id", a.session.id),
    db.from("endlume_licenses").update({ last_seen_at: stamp, updated_at: stamp }).eq("id", a.license.id),
    db.from("endlume_devices").update({
      app_version: String(body.app_version ?? a.device.app_version).slice(0, 64),
      current_screen: body.current_screen == null ? a.device.current_screen : String(body.current_screen).slice(0, 120),
      render_status: body.render_status == null ? a.device.render_status : String(body.render_status).slice(0, 80),
      current_job_id: body.current_job_id == null ? a.device.current_job_id : String(body.current_job_id).slice(0, 180),
      render_progress: progress,
      last_seen_at: stamp,
      last_heartbeat_at: stamp,
      updated_at: stamp,
    }).eq("id", a.device.id),
  ]);
  return json({ ok: true, ...publicState(a) });
}
async function renderEvent(req: Request, body: any) {
  const a = await authSession(req);
  if (!a.ok) return json({ ok: false, allowed: false, code: a.code }, 401);
  const eventType = String(body.event_type ?? "").trim();
  if (!["render_started", "render_progress", "render_stage", "render_completed", "render_failed", "render_cancelled"].includes(eventType)) return json({ ok: false, code: "event_type" }, 400);
  const jobId = String(body.job_id ?? "").trim().slice(0, 180);
  if (!jobId) return json({ ok: false, code: "job_id" }, 400);
  if (!a.allowed) {
    const canCloseExisting = eventType === "render_cancelled" || eventType === "render_failed";
    if (!canCloseExisting) return json({ ok: false, allowed: false, code: a.device.status !== "active" ? `device_${a.device.status}` : `license_${a.licenseStatus}` }, 403);
    const { data: existing } = await db.from("endlume_renders").select("id,status").eq("license_id", a.license.id).eq("device_id", a.device.id).eq("job_id", jobId).maybeSingle();
    if (!existing || existing.status !== "rendering") return json({ ok: false, allowed: false, code: "blocked_terminal_without_running_job" }, 403);
  }
  const terminal: Record<string, string> = { render_completed: "completed", render_failed: "failed", render_cancelled: "cancelled" };
  const renderStatus = terminal[eventType] ?? "rendering";
  const progress = eventType === "render_completed" ? 100 : clamp(body.progress, 0, 100);
  const stamp = iso();
  const row: Record<string, unknown> = {
    license_id: a.license.id,
    device_id: a.device.id,
    job_id: jobId,
    project_id: body.project_id == null ? null : String(body.project_id).slice(0, 180),
    project_name: body.project_name == null ? null : String(body.project_name).slice(0, 300),
    status: renderStatus,
    progress,
    eta_seconds: body.eta_seconds == null ? null : Math.max(0, Number(body.eta_seconds) || 0),
    stage: body.stage == null ? null : String(body.stage).slice(0, 240),
    encoder: body.encoder == null ? null : String(body.encoder).slice(0, 80),
    width: body.width == null ? null : Number(body.width) || null,
    height: body.height == null ? null : Number(body.height) || null,
    fps: body.fps == null ? null : Number(body.fps) || null,
    codec: body.codec == null ? null : String(body.codec).slice(0, 80),
    audio_count: body.audio_count == null ? null : Number(body.audio_count) || 0,
    effects_count: body.effects_count == null ? null : Number(body.effects_count) || 0,
    subscribe_enabled: body.subscribe_enabled == null ? null : !!body.subscribe_enabled,
    output_filename: body.output_filename == null ? null : String(body.output_filename).slice(0, 400),
    output_bytes: body.output_bytes == null ? null : Math.max(0, Number(body.output_bytes) || 0),
    error: body.error == null ? null : String(body.error).slice(0, 4000),
    app_version: body.app_version == null ? a.device.app_version : String(body.app_version).slice(0, 64),
    duration_seconds: body.duration_seconds == null ? null : Math.max(0, Number(body.duration_seconds) || 0),
    settings: body.settings && typeof body.settings === "object" ? body.settings : {},
    updated_at: stamp,
  };
  if (terminal[eventType]) row.finished_at = stamp;
  const { data: render, error } = await db.from("endlume_renders").upsert(row, { onConflict: "license_id,device_id,job_id" }).select("id").single();
  if (error || !render) { console.error("ENDLUME render_upsert_failed", error); return json({ ok: false, code: "render_upsert_failed" }, 500); }
  const payload = body.payload && typeof body.payload === "object" ? body.payload : {};
  await db.from("endlume_render_events").insert({
    render_id: render.id,
    license_id: a.license.id,
    device_id: a.device.id,
    job_id: jobId,
    event_type: eventType,
    progress,
    eta_seconds: row.eta_seconds,
    stage: row.stage,
    payload,
  });
  await db.from("endlume_devices").update({
    render_status: renderStatus,
    current_job_id: terminal[eventType] ? null : jobId,
    render_progress: progress,
    last_seen_at: stamp,
    last_heartbeat_at: stamp,
    updated_at: stamp,
  }).eq("id", a.device.id);
  return json({ ok: true, allowed: a.allowed, renderId: render.id, status: renderStatus });
}
async function thumbnailTicket(req: Request, body: any) {
  const a = await authSession(req);
  if (!a.ok) return json({ ok: false, allowed: false, code: a.code }, 401);
  if (!a.allowed) return json({ ok: false, allowed: false, code: "license_blocked" }, 403);
  const jobId = String(body.job_id ?? "").trim().slice(0, 180);
  const ext = String(body.ext ?? "webp").toLowerCase() === "jpg" ? "jpg" : "webp";
  if (!jobId) return json({ ok: false, code: "job_id" }, 400);
  const path = `${a.license.id}/${a.device.id}/${jobId}.${ext}`;
  const { data, error } = await db.storage.from("endlume-thumbnails").createSignedUploadUrl(path);
  if (error || !data) return json({ ok: false, code: "thumbnail_ticket_failed" }, 500);
  return json({ ok: true, path, token: data.token, signedUrl: data.signedUrl });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, code: "method" }, 405);
  const contentLength = Number(req.headers.get("content-length") ?? 0);
  if (contentLength > 65536) return json({ ok: false, code: "payload_too_large" }, 413);
  let body: any;
  try { body = await req.json(); } catch { return json({ ok: false, code: "json" }, 400); }
  const action = String(body?.action ?? "");
  try {
    if (action === "activate") return await activate(body);
    if (action === "status") return await status(req);
    if (action === "heartbeat") return await heartbeat(req, body);
    if (action === "render_event") return await renderEvent(req, body);
    if (action === "thumbnail_ticket") return await thumbnailTicket(req, body);
    return json({ ok: false, code: "action" }, 400);
  } catch (e) {
    console.error("ENDLUME client API error", e);
    return json({ ok: false, code: "internal" }, 500);
  }
});
