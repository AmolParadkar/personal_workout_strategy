-- Job queue and worker (M4): slow or LLM work waits here for the Mac worker.
-- Spec: context/architecture.md ("Job queue and worker safeguards"),
-- context/data-model.md ("Jobs and worker").

-- ---------------------------------------------------------------------------
-- Jobs
-- ---------------------------------------------------------------------------

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  -- Who the job is for (empty for household-wide jobs, e.g. exercise videos).
  profile_id uuid references public.profiles (id) on delete cascade,
  type text not null check (type in (
    'test_echo',
    'analyse_food_photo', 'generate_workout_plan', 'generate_meal_plan',
    'extract_document_facts', 'analyse_progress_photo', 'find_exercise_video',
    'write_exercise_guide', 'compute_forecast'
  )),
  payload jsonb not null default '{}',
  result jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'done', 'failed')),
  -- Health documents: only the Mac (local Ollama) may process them...
  local_only boolean not null default false,
  -- ...unless the person chose "Process in cloud now" for this item.
  allow_cloud boolean not null default false,
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 10),
  -- Not before this time (retries wait longer each time).
  run_after timestamptz not null default now(),
  locked_by text,
  locked_at timestamptz,
  last_error text check (char_length(last_error) <= 1000),
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index jobs_waiting_idx on public.jobs (run_after) where status = 'pending';
create index jobs_profile_idx on public.jobs (profile_id, created_at desc);

create trigger set_updated_at before update on public.jobs
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- Worker heartbeats
-- ---------------------------------------------------------------------------

-- Each worker records it's alive every minute. If it stops, the app shows
-- "offline since …" and, after ~12 hours with jobs waiting, an alert is sent.
create table public.worker_heartbeats (
  worker_id text primary key check (char_length(worker_id) between 1 and 100),
  mode text not null check (mode in ('local', 'cloud')),
  version text,
  -- Whether the local AI (Ollama) answered at the last check.
  ollama_ok boolean,
  started_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Access rules
-- ---------------------------------------------------------------------------

alter table public.jobs enable row level security;
alter table public.worker_heartbeats enable row level security;
revoke all on public.jobs, public.worker_heartbeats from anon, authenticated;

-- Jobs: the household can see job status (view both); each person adds jobs
-- for themselves. Only the worker (secret key) changes a job after that.
grant select on public.jobs to authenticated;
grant insert (profile_id, type, payload, local_only, allow_cloud, max_attempts)
  on public.jobs to authenticated;

create policy "Read household jobs"
  on public.jobs for select to authenticated
  using (profile_id is null or (select private.in_my_household(profile_id)));
create policy "Add own jobs"
  on public.jobs for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));

-- Heartbeats: anyone signed in can see whether the worker is online.
grant select on public.worker_heartbeats to authenticated;
create policy "Read worker status"
  on public.worker_heartbeats for select to authenticated
  using (true);

-- Retry: put your own failed job back in the queue, with fresh attempts.
create function public.retry_job(p_job_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.jobs
  set status = 'pending', attempts = 0, run_after = now(), last_error = null,
      locked_by = null, locked_at = null, finished_at = null
  where id = p_job_id
    and status = 'failed'
    and profile_id = private.my_profile_id();
  if not found then
    raise exception 'No failed job of yours with that id' using errcode = 'P0002';
  end if;
end;
$$;

revoke execute on function public.retry_job(uuid) from public;
grant execute on function public.retry_job(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Worker functions (secret key only)
-- ---------------------------------------------------------------------------

-- Hand the next waiting job to a worker. `skip locked` makes this safe with
-- several workers: two can never claim the same job. A cloud worker never gets
-- a local-only job unless the person allowed it for that item.
create function public.claim_job(p_worker_id text, p_mode text)
returns setof public.jobs
language plpgsql
set search_path = ''
as $$
begin
  return query
  update public.jobs
  set status = 'processing', locked_by = p_worker_id, locked_at = now(),
      attempts = attempts + 1
  where id = (
    select id from public.jobs
    where status = 'pending'
      and run_after <= now()
      and (p_mode = 'local' or not local_only or allow_cloud)
    order by run_after, created_at
    for update skip locked
    limit 1
  )
  returning *;
end;
$$;

-- Jobs stuck in `processing` (e.g. the Mac slept or crashed mid-job) go back
-- to the queue, or fail if they've used all their attempts.
create function public.requeue_stuck_jobs(p_stuck_after interval)
returns integer
language plpgsql
set search_path = ''
as $$
declare
  changed integer;
begin
  update public.jobs
  set status = case when attempts >= max_attempts then 'failed' else 'pending' end,
      last_error = case when attempts >= max_attempts
        then 'Stopped without finishing too many times.' else last_error end,
      finished_at = case when attempts >= max_attempts then now() else null end,
      locked_by = null, locked_at = null, run_after = now()
  where status = 'processing' and locked_at < now() - p_stuck_after;
  get diagnostics changed = row_count;
  return changed;
end;
$$;

revoke execute on function public.claim_job(text, text) from public, anon, authenticated;
revoke execute on function public.requeue_stuck_jobs(interval) from public, anon, authenticated;
grant execute on function public.claim_job(text, text) to service_role;
grant execute on function public.requeue_stuck_jobs(interval) to service_role;

-- ---------------------------------------------------------------------------
-- Offline alert (runs inside Supabase, so it works while the Mac is off)
-- ---------------------------------------------------------------------------

create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

create table private.alert_state (
  name text primary key,
  last_sent_at timestamptz
);

-- Hourly: if no worker has been seen for 12 hours and jobs have been waiting
-- for 12 hours, send one ntfy push (at most once every 12 hours). The ntfy
-- topic is a Vault secret named 'ntfy_topic' (context/setup.md); without it,
-- nothing is sent.
create function private.check_worker_offline()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  topic text;
  last_seen timestamptz;
  waiting integer;
  sent timestamptz;
  since text;
begin
  select decrypted_secret into topic from vault.decrypted_secrets where name = 'ntfy_topic';
  if topic is null then
    return;
  end if;

  select max(last_seen_at) into last_seen from public.worker_heartbeats where mode = 'local';
  select count(*) into waiting from public.jobs
    where status = 'pending' and created_at < now() - interval '12 hours';
  select last_sent_at into sent from private.alert_state where name = 'worker_offline';

  if waiting = 0
    or (last_seen is not null and last_seen > now() - interval '12 hours')
    or (sent is not null and sent > now() - interval '12 hours') then
    return;
  end if;

  since := case
    when last_seen is null then 'has never checked in'
    else 'has been offline for ' || round(extract(epoch from now() - last_seen) / 3600) || ' hours'
  end;
  -- JSON publishing goes to ntfy's root address, with the topic in the body.
  perform net.http_post(
    url := 'https://ntfy.sh',
    body := jsonb_build_object(
      'topic', topic,
      'title', 'Workout Strategy: Mac worker offline',
      'message', format(
        'The Mac worker %s and %s job(s) are waiting. '
        'Wake the Mac and sign in; the worker restarts by itself.',
        since, waiting
      ),
      'priority', 4
    ),
    headers := '{"Content-Type": "application/json"}'::jsonb
  );
  insert into private.alert_state (name, last_sent_at) values ('worker_offline', now())
    on conflict (name) do update set last_sent_at = excluded.last_sent_at;
end;
$$;

revoke execute on function private.check_worker_offline() from public;

select cron.schedule(
  'worker-offline-alert',
  '0 * * * *',
  $$select private.check_worker_offline();$$
);
