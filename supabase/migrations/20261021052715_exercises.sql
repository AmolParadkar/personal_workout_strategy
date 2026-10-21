-- Exercise library (M5): the shared list of exercises, with the guide text and
-- video added by the Mac worker. Not per person: everyone signed in reads it.
-- Spec: context/pages/exercise-guide.md, context/data-model.md ("Workouts").

create table public.exercises (
  -- The source's own id, e.g. 'Barbell_Squat' (free-exercise-db), used in page addresses.
  id text primary key check (id ~ '^[A-Za-z0-9_-]{1,100}$'),
  name text not null check (char_length(name) between 1 and 120),
  source text not null default 'free-exercise-db' check (source in ('free-exercise-db', 'wger', 'custom')),
  category text,
  level text check (level in ('beginner', 'intermediate', 'expert')),
  force text check (force in ('push', 'pull', 'static')),
  mechanic text check (mechanic in ('compound', 'isolation')),
  equipment text,
  primary_muscles text[] not null default '{}',
  secondary_muscles text[] not null default '{}',
  -- Step-by-step instructions from the source.
  instructions text[] not null default '{}',
  -- Full image addresses: start and end position.
  images text[] not null default '{}',

  -- Written once by the LLM (write_exercise_guide job), then reused.
  about text check (char_length(about) <= 1000),
  form_cues text[],
  precautions text[],
  guide_model text,
  guide_written_at timestamptz,

  -- Chosen by the video scoring job (find_exercise_video); refreshed monthly.
  video_id text check (video_id ~ '^[A-Za-z0-9_-]{6,20}$'),
  video_title text,
  video_channel text,
  video_duration_seconds integer check (video_duration_seconds > 0),
  video_views bigint check (video_views >= 0),
  video_score numeric,
  -- When we last looked (set even when no suitable video was found).
  video_checked_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index exercises_name_idx on public.exercises (lower(name));
create index exercises_primary_muscles_idx on public.exercises using gin (primary_muscles);

create trigger set_updated_at before update on public.exercises
  for each row execute function private.set_updated_at();

alter table public.exercises enable row level security;
revoke all on public.exercises from anon, authenticated;

-- Everyone signed in reads the library. Only the importer and the worker
-- (secret keys) write to it, so guide text can't be changed from the website.
grant select on public.exercises to authenticated;
create policy "Read the exercise library"
  on public.exercises for select to authenticated
  using (true);
