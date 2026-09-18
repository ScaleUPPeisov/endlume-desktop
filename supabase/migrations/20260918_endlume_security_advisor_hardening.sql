-- Applied during ENDLUME 8.62 production QA.
-- Removes a duplicate client-callable admin RPC, pins trigger search_path,
-- and adds covering indexes for ENDLUME device/license foreign keys.

alter function public.endlume_touch_updated_at()
  set search_path = pg_catalog, pg_temp;

revoke execute on function public.endlume_admin_device_action(uuid, text) from public;
revoke execute on function public.endlume_admin_device_action(uuid, text) from anon;
revoke execute on function public.endlume_admin_device_action(uuid, text) from authenticated;

create index if not exists endlume_sessions_device_license_idx
  on public.endlume_sessions(device_id, license_id);
create index if not exists endlume_sessions_license_idx
  on public.endlume_sessions(license_id);

create index if not exists endlume_renders_device_license_idx
  on public.endlume_renders(device_id, license_id);
create index if not exists endlume_renders_license_idx
  on public.endlume_renders(license_id);

create index if not exists endlume_render_events_device_license_idx
  on public.endlume_render_events(device_id, license_id);
create index if not exists endlume_render_events_license_idx
  on public.endlume_render_events(license_id);
