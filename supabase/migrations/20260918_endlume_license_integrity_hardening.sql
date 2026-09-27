-- Applied to production Supabase project odlseljmogaguyqdlkyv during 8.61 QA.
-- Existing schema already had UNIQUE(key_hash), UNIQUE(token_hash), RLS and admin-only SELECT policies.
-- This migration hardens owner-plan invariants and cross-license device binding.

alter table public.endlume_licenses
  add constraint endlume_licenses_owner_plan_consistency_chk
  check (
    (owner = true and plan = 'owner' and expires_at is null)
    or
    (owner = false and plan = 'managed' and expires_at is not null)
  ) not valid;

alter table public.endlume_licenses
  validate constraint endlume_licenses_owner_plan_consistency_chk;

alter table public.endlume_licenses
  add constraint endlume_licenses_key_hash_hex_chk
  check (key_hash ~ '^[0-9a-f]{64}$') not valid;

alter table public.endlume_licenses
  validate constraint endlume_licenses_key_hash_hex_chk;

alter table public.endlume_sessions
  add constraint endlume_sessions_token_hash_hex_chk
  check (token_hash ~ '^[0-9a-f]{64}$') not valid;

alter table public.endlume_sessions
  validate constraint endlume_sessions_token_hash_hex_chk;

alter table public.endlume_devices
  add constraint endlume_devices_id_license_key unique (id, license_id);

alter table public.endlume_sessions
  add constraint endlume_sessions_device_license_fkey
  foreign key (device_id, license_id)
  references public.endlume_devices(id, license_id)
  on delete cascade
  not valid;

alter table public.endlume_sessions
  validate constraint endlume_sessions_device_license_fkey;

alter table public.endlume_renders
  add constraint endlume_renders_device_license_fkey
  foreign key (device_id, license_id)
  references public.endlume_devices(id, license_id)
  on delete cascade
  not valid;

alter table public.endlume_renders
  validate constraint endlume_renders_device_license_fkey;

alter table public.endlume_render_events
  add constraint endlume_render_events_device_license_fkey
  foreign key (device_id, license_id)
  references public.endlume_devices(id, license_id)
  on delete cascade
  not valid;

alter table public.endlume_render_events
  validate constraint endlume_render_events_device_license_fkey;
