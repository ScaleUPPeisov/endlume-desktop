-- ENDLUME 8.63 render performance telemetry only.
alter table public.endlume_renders
  add column if not exists media_count integer,
  add column if not exists image_count integer,
  add column if not exists video_count integer,
  add column if not exists fast_path boolean,
  add column if not exists fast_path_reason text,
  add column if not exists audio_mode text,
  add column if not exists render_wall_seconds double precision,
  add column if not exists final_video_duration_seconds double precision,
  add column if not exists video_codec text,
  add column if not exists audio_codec text;

alter table public.endlume_renders
  add constraint endlume_renders_media_count_nonnegative_chk check (media_count is null or media_count >= 0) not valid;
alter table public.endlume_renders validate constraint endlume_renders_media_count_nonnegative_chk;
alter table public.endlume_renders
  add constraint endlume_renders_image_count_nonnegative_chk check (image_count is null or image_count >= 0) not valid;
alter table public.endlume_renders validate constraint endlume_renders_image_count_nonnegative_chk;
alter table public.endlume_renders
  add constraint endlume_renders_video_count_nonnegative_chk check (video_count is null or video_count >= 0) not valid;
alter table public.endlume_renders validate constraint endlume_renders_video_count_nonnegative_chk;
alter table public.endlume_renders
  add constraint endlume_renders_wall_nonnegative_chk check (render_wall_seconds is null or render_wall_seconds >= 0) not valid;
alter table public.endlume_renders validate constraint endlume_renders_wall_nonnegative_chk;
alter table public.endlume_renders
  add constraint endlume_renders_final_duration_nonnegative_chk check (final_video_duration_seconds is null or final_video_duration_seconds >= 0) not valid;
alter table public.endlume_renders validate constraint endlume_renders_final_duration_nonnegative_chk;
