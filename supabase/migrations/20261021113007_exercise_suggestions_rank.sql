-- Closest matches for a search that finds nothing: the top 5 are shown as the
-- results, so rank them better. Ties on "does the typed text appear in the
-- name" (word similarity) are broken by how close the whole name is
-- (similarity), then by the shortest name.

create or replace function public.suggest_exercises(
  p_query text,
  p_muscle text default null,
  p_equipment text default null,
  p_limit integer default 5
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
  order by similarity desc,
           extensions.similarity(lower(p_query), lower(e.name)) desc,
           char_length(e.name),
           e.name
  limit least(greatest(p_limit, 1), 20);
$$;
