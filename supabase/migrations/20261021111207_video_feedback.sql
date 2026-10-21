-- "Is this the right video?" (M5 follow-up): people confirm or reject an
-- exercise's video, with a reason. Rejections are read by the video search job,
-- which avoids rejected videos and searches again with the reasons in mind.
-- Spec: context/pages/exercise-guide.md ("Video feedback").

create table public.video_feedback (
  id uuid primary key default gen_random_uuid(),
  exercise_id text not null references public.exercises (id) on delete cascade,
  profile_id uuid not null references public.profiles (id) on delete cascade,
  video_id text not null check (video_id ~ '^[A-Za-z0-9_-]{6,20}$'),
  -- The title at the time, so the reason still makes sense to the LLM later.
  video_title text check (char_length(video_title) <= 200),
  verdict text not null check (verdict in ('right', 'wrong')),
  -- Required when the video is wrong: why.
  reason text check (char_length(reason) between 3 and 300),
  created_at timestamptz not null default now(),
  check (verdict = 'right' or reason is not null)
);

create index video_feedback_exercise_idx on public.video_feedback (exercise_id, created_at desc);

alter table public.video_feedback enable row level security;
revoke all on public.video_feedback from anon, authenticated;

-- The library is shared, so feedback on it is too: everyone signed in reads it;
-- each person adds their own (no editing or deleting).
grant select on public.video_feedback to authenticated;
grant insert (exercise_id, profile_id, video_id, video_title, verdict, reason)
  on public.video_feedback to authenticated;

create policy "Read video feedback"
  on public.video_feedback for select to authenticated
  using (true);
create policy "Give own video feedback"
  on public.video_feedback for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
