-- Nutrition Plan, round two: dishes a household adds itself (recipe drafted by the
-- AI, nutrients worked out from USDA ingredients), food search, and the week's
-- chat about the meal plan. Spec: context/pages/nutrition-plan.md.

-- ---------------------------------------------------------------------------
-- Custom dishes: rows in foods that belong to one household
-- ---------------------------------------------------------------------------

alter table public.foods
  drop constraint foods_id_check,
  add constraint foods_id_check check (id ~ '^(usda|indb|custom)-[A-Za-z0-9]{1,40}$'),
  drop constraint foods_source_check,
  add constraint foods_source_check check (source in ('usda', 'indb', 'custom')),
  -- Empty for the shared databases; set for a household's own dishes.
  add column household_id uuid references public.households (id) on delete cascade,
  add column created_by uuid references public.profiles (id) on delete set null,
  add constraint foods_custom_owner check ((source = 'custom') = (household_id is not null));

create index foods_household_idx on public.foods (household_id) where household_id is not null;

drop policy "Signed-in users read foods" on public.foods;
create policy "Read shared foods and your household's dishes"
  on public.foods for select to authenticated
  using (household_id is null or household_id = (select private.my_household_id()));

-- Either person in the household can add a dish; only whoever added it removes it.
grant insert (id, name, source, category, role, diet, basis, serving_label, countable, kcal,
              protein_g, carbs_g, fat_g, fibre_g, micros, ingredients, household_id,
              created_by)
  on public.foods to authenticated;
grant delete on public.foods to authenticated;
create policy "Add dishes for your household"
  on public.foods for insert to authenticated
  with check (
    source = 'custom'
    and household_id = (select private.my_household_id())
    and created_by = (select private.my_profile_id())
  );
create policy "Remove dishes you added"
  on public.foods for delete to authenticated
  using (source = 'custom' and created_by = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- Searching foods by name (dishes for swaps, ingredients for new dishes)
-- ---------------------------------------------------------------------------

-- p_kind: 'dish' (anything the planner can use) or 'ingredient' (USDA foods,
-- nutrients per 100 g). Every word must appear, in any order; ranked by how
-- close the name is, shorter names first. Runs with the caller's access, so a
-- household only finds its own dishes.
create function public.search_foods(
  p_query text,
  p_kind text default 'dish',
  p_roles text[] default null,
  p_limit integer default 12
)
returns setof public.foods
language sql
stable
set search_path = ''
as $$
  select f.*
  from public.foods f
  where char_length(trim(p_query)) between 2 and 60
    and (
      (p_kind = 'dish' and f.role is not null and (p_roles is null or f.role = any (p_roles)))
      or (p_kind = 'ingredient' and f.source = 'usda')
    )
    and not exists (
      select 1
      from unnest(regexp_split_to_array(lower(trim(p_query)), '\s+')) as word
      where word <> '' and position(word in lower(coalesce(f.alias, '') || ' ' || f.name)) = 0
    )
  order by extensions.similarity(lower(p_query), lower(coalesce(f.alias, f.name))) desc,
           char_length(f.name),
           f.name
  limit least(greatest(p_limit, 1), 30);
$$;

-- Closest names when a word-for-word search finds nothing (trigram similarity).
create function public.suggest_foods(
  p_query text,
  p_kind text default 'dish',
  p_limit integer default 8
)
returns setof public.foods
language sql
stable
set search_path = ''
as $$
  select f.*
  from public.foods f
  where char_length(trim(p_query)) between 2 and 60
    and ((p_kind = 'dish' and f.role is not null) or (p_kind = 'ingredient' and f.source = 'usda'))
    and extensions.word_similarity(lower(p_query), lower(coalesce(f.alias, '') || ' ' || f.name))
        >= 0.3
  order by extensions.word_similarity(lower(p_query),
                                      lower(coalesce(f.alias, '') || ' ' || f.name)) desc,
           char_length(f.name)
  limit least(greatest(p_limit, 1), 30);
$$;

revoke execute on function public.search_foods(text, text, text[], integer) from public, anon;
revoke execute on function public.suggest_foods(text, text, integer) from public, anon;
grant execute on function public.search_foods(text, text, text[], integer)
  to authenticated, service_role;
grant execute on function public.suggest_foods(text, text, integer) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- The week's chat about the meal plan (your own only)
-- ---------------------------------------------------------------------------

create table public.meal_chat_messages (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  week_start date not null check (extract(isodow from week_start) = 1),
  role text not null check (role in ('user', 'assistant')),
  text text not null check (char_length(text) between 1 and 2000),
  -- The preview this reply made, if any.
  draft_plan_id uuid references public.meal_plans (id) on delete set null,
  -- Dishes the reply suggests adding, e.g. {"add_dishes": ["Aloo paratha"]}.
  details jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index meal_chat_messages_week_idx
  on public.meal_chat_messages (profile_id, week_start, created_at);

alter table public.meal_chat_messages enable row level security;
revoke all on public.meal_chat_messages from anon, authenticated;
grant select, insert (profile_id, week_start, role, text, draft_plan_id, details)
  on public.meal_chat_messages to authenticated;
create policy "Read own meal chat"
  on public.meal_chat_messages for select to authenticated
  using (profile_id = (select private.my_profile_id()));
create policy "Write own meal chat"
  on public.meal_chat_messages for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
