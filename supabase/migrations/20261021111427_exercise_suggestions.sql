-- "Did you mean …?" for the exercise library: when a search finds nothing,
-- suggest exercises whose names are close to what was typed (typos, plurals,
-- different word order). Uses trigram similarity (pg_trgm).
-- Spec: context/pages/exercise-guide.md ("As built").

create extension if not exists pg_trgm with schema extensions;

create index exercises_name_trgm_idx
  on public.exercises using gin (lower(name) extensions.gin_trgm_ops);

-- Closest names first. Runs with the caller's rights, so the library's access
-- rules still apply (signed-in people only). Optional filters match the list's.
create function public.suggest_exercises(
  p_query text,
  p_muscle text default null,
  p_equipment text default null,
  p_limit integer default 8
)
returns table (
  id text,
  name text,
  category text,
  equipment text,
  level text,
  primary_muscles text[],
  images text[],
  similarity real
)
language sql
stable
set search_path = ''
as $$
  select e.id, e.name, e.category, e.equipment, e.level, e.primary_muscles, e.images,
         extensions.word_similarity(lower(p_query), lower(e.name)) as similarity
  from public.exercises e
  where char_length(trim(p_query)) between 2 and 60
    and extensions.word_similarity(lower(p_query), lower(e.name)) >= 0.3
    and (p_muscle is null or p_muscle = any (e.primary_muscles))
    and (p_equipment is null or e.equipment = p_equipment)
  order by similarity desc, e.name
  limit least(greatest(p_limit, 1), 20);
$$;

revoke execute on function public.suggest_exercises(text, text, text, integer) from public, anon;
grant execute on function public.suggest_exercises(text, text, text, integer) to authenticated;
