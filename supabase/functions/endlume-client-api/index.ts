import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { isNonTerminalRenderEvent, isTerminalRenderStatus, shouldIgnoreRenderMutation } from "./render-state.ts";
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
function wantsEvent(s:any,eventType:string){
  if(eventType==="first_activation")return s?.notify_first_activation!==false;
  if(eventType==="render_started")return s?.notify_render_started!==false;
  if(eventType==="render_completed")return s?.notify_render_completed!==false;
  if(eventType==="render_failed"||eventType==="render_cancelled")return s?.notify_render_failed!==false;
  return true;
}
async function pushNotification(eventType:string,license:any,device:any,renderId:string|null,title:string,body:string,metadata:any={}) {
  try {
    const {data:created,error:createError}=await db.from("endlume_notifications").insert({
      event_type:eventType,
      license_id:license?.id ?? null,
      device_id:device?.id ?? null,
      render_id:renderId,
      title:title.slice(0,300),
      body:body.slice(0,2000),
      channel:"control",
      status:"created",
      metadata:metadata && typeof metadata==="object" ? metadata : {}
    }).select("id").single();
    if(createError||!created)return;

    const {data:settings}=await db.from("endlume_notification_settings").select("*").limit(1).maybeSingle();
    if(!settings||!wantsEvent(settings,eventType))return;

    const delivered:string[]=[];
    const telegramToken=Deno.env.get("ENDLUME_TELEGRAM_BOT_TOKEN")||"";
    if(settings.telegram_enabled&&settings.telegram_chat_id&&telegramToken){
      try{
        const rr=await fetch("https://api.telegram.org/bot"+telegramToken+"/sendMessage",{
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({chat_id:settings.telegram_chat_id,text:title+"\n"+body,disable_web_page_preview:true})
        });
        if(rr.ok)delivered.push("telegram")
      }catch(e){console.error("telegram notify",e)}
    }

    const resendKey=Deno.env.get("RESEND_API_KEY")||"";
    if(settings.email_enabled&&settings.email_to&&resendKey){
      try{
        const rr=await fetch("https://api.resend.com/emails",{
          method:"POST",
          headers:{"Authorization":"Bearer "+resendKey,"Content-Type":"application/json"},
          body:JSON.stringify({
            from:Deno.env.get("ENDLUME_FROM_EMAIL")||"ENDLUME <onboarding@resend.dev>",
            to:[settings.email_to],
            subject:title,
            text:body
          })
        });
        if(rr.ok)delivered.push("email")
      }catch(e){console.error("email notify",e)}
    }

    if(delivered.length){
      await db.from("endlume_notifications").update({
        channel:delivered.join(","),
        status:"delivered",
        delivered_at:iso(),
        metadata:{...(metadata||{}),delivered_channels:delivered}
      }).eq("id",created.id)
    }else if(settings.telegram_enabled||settings.email_enabled){
      await db.from("endlume_notifications").update({
        status:"transport_not_configured",
        metadata:{...(metadata||{}),transport_note:"Server credentials missing or delivery failed"}
      }).eq("id",created.id)
    }
  } catch (e) { console.error("ENDLUME notification", e); }
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
    cloudArtifactsEnabled: !!a.license.cloud_artifacts_enabled,
    cloudArtifactRetentionDays: a.license.cloud_artifact_retention_days || 3,
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
  if (!deviceId || deviceId.length > 160 || !platform || !architecture || !appVersion) return json({ ok: false, code: "device_metadata" }, 400);
  const keyHash = await sha256Hex(key);

  let license:any = null;
  const direct = await db.from("endlume_licenses").select("*").eq("key_hash", keyHash).maybeSingle();
  if (direct.error) return json({ ok: false, code: "db_error" }, 500);
  license = direct.data;

  let alias:any = null;
  if (!license) {
    const aliasResult = await db.from("endlume_license_keys").select("*").eq("key_hash", keyHash).eq("active", true).maybeSingle();
    if (aliasResult.error) return json({ ok: false, code: "db_error" }, 500);
    alias = aliasResult.data;
    if (alias) {
      const licenseResult = await db.from("endlume_licenses").select("*").eq("id", alias.license_id).maybeSingle();
      if (licenseResult.error) return json({ ok: false, code: "db_error" }, 500);
      license = licenseResult.data;
    }
  }

  if (!license) return json({ ok: false, code: validKey ? "key_invalid" : "key_format" }, validKey ? 401 : 400);
  if (alias) await db.from("endlume_license_keys").update({ last_used_at: iso() }).eq("id", alias.id);
  const licenseStatus = await expireIfNeeded(license);
  if (licenseStatus !== "active") return json({ ok: false, code: `license_${licenseStatus}`, licenseStatus }, 403);

  let { data: device } = await db.from("endlume_devices").select("*").eq("license_id", license.id).eq("device_id", deviceId).maybeSingle();
  const firstActivation = !device || device.status === "detached";
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
  if (firstActivation) {
    await pushNotification(
      "first_activation",
      license,
      device,
      null,
      "ENDLUME: первое подключение",
      (license.customer_name || "Клиент") + " активировал ENDLUME на " + (device.device_name || device.platform),
      { app_version: device.app_version, platform: device.platform, architecture: device.architecture }
    );
  }
  return json({ ok: true, sessionToken: token, sessionExpiresAt: sessionExpires, ...publicState({ allowed: true, license, device, licenseStatus: "active" }) });
}
async function legacyOwnerMigrate(body:any){
  const proofHash=String(body.proof_hash??"").trim().toLowerCase();
  const deviceId=String(body.device_id??"").trim();
  const platform=String(body.platform??"").trim().toLowerCase();
  const architecture=String(body.architecture??"").trim().toLowerCase();
  const appVersion=String(body.app_version??"").trim();
  const deviceName=String(body.device_name??"").trim().slice(0,160)||null;
  if(!/^[0-9a-f]{64}$/.test(proofHash)||!deviceId||deviceId.length>160||!platform||!architecture||!appVersion){
    return json({ok:false,code:"legacy_owner_metadata"},400);
  }

  let {data:migration}=await db.from("endlume_legacy_owner_migrations")
    .select("*")
    .eq("proof_hash",proofHash)
    .eq("allowed_platform",platform)
    .eq("allowed_version",appVersion)
    .maybeSingle();

  if(!migration)return json({ok:false,code:"legacy_owner_migration_unavailable"},403);

  if(migration.status==="open"){
    const stamp=iso();
    const claimed=await db.from("endlume_legacy_owner_migrations")
      .update({status:"claimed",claimed_device_id:deviceId,claimed_at:stamp,updated_at:stamp})
      .eq("id",migration.id)
      .eq("status","open")
      .select("*")
      .maybeSingle();
    migration=claimed.data;
    if(!migration)return json({ok:false,code:"legacy_owner_migration_claimed"},409);
  }else if(migration.status==="claimed"&&migration.claimed_device_id!==deviceId){
    return json({ok:false,code:"legacy_owner_migration_claimed"},409);
  }else if(migration.status!=="claimed"){
    return json({ok:false,code:"legacy_owner_migration_disabled"},403);
  }

  const {data:license,error:licenseError}=await db.from("endlume_licenses").select("*").eq("id",migration.license_id).maybeSingle();
  if(licenseError||!license||!license.owner||license.plan!=="owner")return json({ok:false,code:"owner_license_missing"},500);
  const licenseStatus=await expireIfNeeded(license);
  if(licenseStatus!=="active")return json({ok:false,code:`license_${licenseStatus}`},403);

  const stamp=iso();
  let {data:device}=await db.from("endlume_devices").select("*").eq("license_id",license.id).eq("device_id",deviceId).maybeSingle();
  if(device?.status==="blocked")return json({ok:false,code:"device_blocked"},403);

  const {data:bound,error:bindError}=await db.from("endlume_devices").upsert({
    license_id:license.id,
    device_id:deviceId,
    status:"active",
    platform,
    architecture,
    app_version:appVersion,
    device_name:deviceName,
    last_seen_at:stamp,
    last_heartbeat_at:stamp,
    updated_at:stamp
  },{onConflict:"license_id,device_id"}).select("*").single();
  if(bindError||!bound)return json({ok:false,code:"device_bind_failed"},500);
  device=bound;

  await db.from("endlume_sessions").update({revoked_at:stamp}).eq("device_id",device.id).is("revoked_at",null);
  const token=randomToken();
  const tokenHash=await sha256Hex(token);
  const sessionExpires=new Date(Date.now()+30*86400_000).toISOString();
  const {data:session,error:sessionError}=await db.from("endlume_sessions").insert({
    license_id:license.id,
    device_id:device.id,
    token_hash:tokenHash,
    expires_at:sessionExpires
  }).select("id").single();
  if(sessionError||!session)return json({ok:false,code:"session_create_failed"},500);

  await Promise.all([
    db.from("endlume_licenses").update({last_seen_at:stamp,updated_at:stamp}).eq("id",license.id),
    db.from("endlume_legacy_owner_migrations").update({updated_at:stamp}).eq("id",migration.id)
  ]);

  await pushNotification(
    "first_activation",
    license,
    device,
    null,
    "ENDLUME: Owner Mac подключён",
    (device.device_name||"Owner Mac")+" подключён к ENDLUME Control",
    {app_version:appVersion,platform,architecture,legacy_owner_migration:true}
  );

  return json({
    ok:true,
    migrated:true,
    sessionToken:token,
    sessionExpiresAt:sessionExpires,
    ...publicState({allowed:true,license,device,licenseStatus:"active"})
  });
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
      cpu_model: body.cpu_model == null ? a.device.cpu_model : String(body.cpu_model).slice(0,240),
      gpu_model: body.gpu_model == null ? a.device.gpu_model : String(body.gpu_model).slice(0,240),
      memory_total_bytes: body.memory_total_bytes == null ? a.device.memory_total_bytes : Math.max(0, Number(body.memory_total_bytes) || 0),
      memory_used_bytes: body.memory_used_bytes == null ? a.device.memory_used_bytes : Math.max(0, Number(body.memory_used_bytes) || 0),
      disk_free_bytes: body.disk_free_bytes == null ? a.device.disk_free_bytes : Math.max(0, Number(body.disk_free_bytes) || 0),
      ffmpeg_version: body.ffmpeg_version == null ? a.device.ffmpeg_version : String(body.ffmpeg_version).slice(0,240),
      encoder_caps: body.encoder_caps && typeof body.encoder_caps === "object" ? body.encoder_caps : (a.device.encoder_caps || {}),
      benchmark: body.benchmark && typeof body.benchmark === "object" ? body.benchmark : (a.device.benchmark || {}),
      cpu_percent: body.cpu_percent == null ? a.device.cpu_percent : clamp(body.cpu_percent,0,100),
      gpu_percent: body.gpu_percent == null ? a.device.gpu_percent : clamp(body.gpu_percent,0,100),
      queue_depth: body.queue_depth == null ? a.device.queue_depth : Math.max(0, Number(body.queue_depth) || 0),
      last_error: body.last_error == null ? a.device.last_error : String(body.last_error).slice(0,2000),
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
  const { data: existing, error: existingError } = await db.from("endlume_renders").select("id,status").eq("license_id", a.license.id).eq("device_id", a.device.id).eq("job_id", jobId).maybeSingle();
  if (existingError) { console.error("ENDLUME render_state_read_failed", existingError); return json({ ok: false, code: "render_state_read_failed" }, 500); }
  if (shouldIgnoreRenderMutation(existing?.status, eventType)) {
    return json({ ok: true, ignored: true, reason: "render_already_terminal", status: existing!.status });
  }
  if (!a.allowed) {
    const canCloseExisting = eventType === "render_cancelled" || eventType === "render_failed";
    if (!canCloseExisting) return json({ ok: false, allowed: false, code: a.device.status !== "active" ? `device_${a.device.status}` : `license_${a.licenseStatus}` }, 403);
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
    status: renderStatus,
    progress,
    updated_at: stamp,
  };
  const textField=(column:string,value:any,max:number)=>{if(value!=null)row[column]=String(value).slice(0,max)};
  const numberField=(column:string,value:any)=>{if(value!=null)row[column]=Math.max(0,Number(value)||0)};
  textField("project_id",body.project_id,180);
  textField("project_name",body.project_name,300);
  if(body.eta_seconds!=null)row.eta_seconds=Math.max(0,Number(body.eta_seconds)||0);
  textField("stage",body.stage,240);
  textField("encoder",body.encoder,80);
  if(body.width!=null)row.width=Number(body.width)||null;
  if(body.height!=null)row.height=Number(body.height)||null;
  if(body.fps!=null)row.fps=Number(body.fps)||null;
  textField("codec",body.codec,80);
  numberField("audio_count",body.audio_count);
  numberField("effects_count",body.effects_count);
  if(body.subscribe_enabled!=null)row.subscribe_enabled=!!body.subscribe_enabled;
  textField("output_filename",body.output_filename,400);
  numberField("output_bytes",body.output_bytes);
  textField("error",body.error,4000);
  row.app_version=body.app_version==null?a.device.app_version:String(body.app_version).slice(0,64);
  numberField("duration_seconds",body.duration_seconds);
  numberField("media_count",body.media_count);
  numberField("image_count",body.image_count);
  numberField("video_count",body.video_count);
  if(body.fast_path!=null)row.fast_path=!!body.fast_path;
  textField("fast_path_reason",body.fast_path_reason,120);
  textField("audio_mode",body.audio_mode,120);
  numberField("render_wall_seconds",body.render_wall_seconds);
  numberField("final_video_duration_seconds",body.final_video_duration_seconds);
  textField("video_codec",body.video_codec,80);
  textField("audio_codec",body.audio_codec,80);
  if(body.settings&&typeof body.settings==="object")row.settings=body.settings;
  if (terminal[eventType]) row.finished_at = stamp;
  let render:any=null;let error:any=null;
  if (isNonTerminalRenderEvent(eventType) && existing) {
    const updated = await db.from("endlume_renders").update(row).eq("id", existing.id).eq("status", "rendering").select("id,status").maybeSingle();
    render=updated.data;error=updated.error;
    if (!error && !render) {
      const current = await db.from("endlume_renders").select("id,status").eq("id", existing.id).maybeSingle();
      if (current.error) { console.error("ENDLUME render_state_reread_failed", current.error); return json({ ok: false, code: "render_state_reread_failed" }, 500); }
      if (current.data && isTerminalRenderStatus(current.data.status)) {
        return json({ ok: true, ignored: true, reason: "render_already_terminal", status: current.data.status });
      }
      return json({ ok: false, code: "render_state_conflict" }, 409);
    }
  } else {
    const upserted = await db.from("endlume_renders").upsert(row, { onConflict: "license_id,device_id,job_id" }).select("id,status").single();
    render=upserted.data;error=upserted.error;
  }
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
  // ENDLUME control notification hook
  if (eventType === "render_started") {
    await pushNotification("render_started",a.license,a.device,render.id,"ENDLUME: рендер запущен",(a.license.customer_name || "Клиент") + " — " + String(row.project_name || jobId),{job_id:jobId});
  } else if (eventType === "render_completed") {
    await pushNotification("render_completed",a.license,a.device,render.id,"ENDLUME: рендер готов",String(row.project_name || jobId) + " • " + String(row.output_filename || "готово"),{job_id:jobId,output_bytes:row.output_bytes});
  } else if (eventType === "render_failed" || eventType === "render_cancelled") {
    await pushNotification(eventType,a.license,a.device,render.id,"ENDLUME: проблема рендера",String(row.project_name || jobId) + " • " + String(row.error || eventType),{job_id:jobId});
  }
  return json({ ok: true, allowed: a.allowed, renderId: render.id, status: renderStatus });
}
async function artifactAuthorize(req:Request,body:any){
  const a=await authSession(req);
  if(!a.ok)return json({ok:false,allowed:false,code:a.code},401);
  if(!a.allowed)return json({ok:false,allowed:false,code:"license_blocked"},403);
  if(!a.license.cloud_artifacts_enabled)return json({ok:false,code:"cloud_artifacts_disabled"},403);
  const renderId=String(body.render_id??"").trim();
  const jobId=String(body.job_id??"").trim();
  if(!renderId&&!jobId)return json({ok:false,code:"render_id_or_job_id"},400);
  let rq=db.from("endlume_renders").select("*").eq("license_id",a.license.id).eq("device_id",a.device.id);
  rq=renderId?rq.eq("id",renderId):rq.eq("job_id",jobId);
  const {data:render}=await rq.maybeSingle();
  if(!render)return json({ok:false,code:"render_not_found"},404);
  if(render.status!=="completed")return json({ok:false,code:"render_not_completed"},409);
  const safeName=String(render.output_filename||"ENDLUME-render.mp4").replace(/[^A-Za-z0-9._-]+/g,"_").slice(-180);
  const objectKey="renders/endlume/"+a.license.id+"/"+a.device.id+"/"+render.id+"/"+safeName;
  const retention=Math.min(30,Math.max(1,Number(a.license.cloud_artifact_retention_days)||3));
  const expiresAt=new Date(Date.now()+retention*86400000).toISOString();
  const {data:serviceRow}=await db.from("endlume_system_settings").select("value").eq("key","artifact_service").maybeSingle();
  const serviceState=serviceRow?.value||{};
  if(!serviceState.enabled||!serviceState.base_url)return json({ok:false,code:"artifact_service_unavailable"},503);
  const {data:artifact,error}=await db.from("endlume_render_artifacts").upsert({
    render_id:render.id,provider:"r2",object_key:objectKey,status:"uploading",
    size_bytes:render.output_bytes||null,expires_at:expiresAt,updated_at:iso()
  },{onConflict:"render_id"}).select("*").single();
  if(error||!artifact)return json({ok:false,code:"artifact_prepare_failed"},500);
  return json({ok:true,renderId:render.id,objectKey,filename:render.output_filename||safeName,expiresAt,uploadBaseUrl:String(serviceState.base_url)})
}
async function artifactUploaded(req:Request,body:any){
  const a=await authSession(req);
  if(!a.ok)return json({ok:false,allowed:false,code:a.code},401);
  const renderId=String(body.render_id??"").trim();
  if(!renderId)return json({ok:false,code:"render_id"},400);
  const {data:render}=await db.from("endlume_renders").select("id,license_id,device_id").eq("id",renderId).eq("license_id",a.license.id).eq("device_id",a.device.id).maybeSingle();
  if(!render)return json({ok:false,code:"render_not_found"},404);
  const size=Math.max(0,Number(body.size_bytes)||0);
  const sha=String(body.sha256||"").toLowerCase();
  const patch:any={status:"ready",uploaded_at:iso(),updated_at:iso()};
  if(size>0)patch.size_bytes=size;
  if(/^[0-9a-f]{64}$/.test(sha))patch.sha256=sha;
  const {data,error}=await db.from("endlume_render_artifacts").update(patch).eq("render_id",renderId).select("*").single();
  if(error||!data)return json({ok:false,code:"artifact_finalize_failed"},500);
  await pushNotification("artifact_ready",a.license,a.device,renderId,"ENDLUME: файл доступен в Control",String(body.filename||"Готовый MP4 загружен"),{size_bytes:size});
  return json({ok:true,artifact:data})
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
    if (action === "legacy_owner_migrate") return await legacyOwnerMigrate(body);
    if (action === "status") return await status(req);
    if (action === "heartbeat") return await heartbeat(req, body);
    if (action === "render_event") return await renderEvent(req, body);
    if (action === "thumbnail_ticket") return await thumbnailTicket(req, body);
    if (action === "artifact_authorize") return await artifactAuthorize(req, body);
    if (action === "artifact_uploaded") return await artifactUploaded(req, body);
    return json({ ok: false, code: "action" }, 400);
  } catch (e) {
    console.error("ENDLUME client API error", e);
    return json({ ok: false, code: "internal" }, 500);
  }
});
