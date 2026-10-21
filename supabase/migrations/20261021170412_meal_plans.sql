-- Nutrition (M7 part 1): the food database, weekly meal plans and daily targets.
-- Spec: context/pages/nutrition-plan.md, context/data-model.md ("Nutrition").

-- ---------------------------------------------------------------------------
-- Foods (imported by backend/scripts/import_foods.py; read-only for everyone else)
-- ---------------------------------------------------------------------------

create table public.foods (
  -- 'usda-<fdc id>' or 'indb-<recipe code>'.
  id text primary key check (id ~ '^(usda|indb)-[A-Za-z0-9]{1,20}$'),
  name text not null check (char_length(name) between 1 and 200),
  -- A plain name for common foods, e.g. 'Boiled eggs' for 'Egg, whole, cooked, hard-boiled'.
  alias text check (char_length(alias) <= 80),
  source text not null check (source in ('usda', 'indb')),
  category text,
  -- How the meal planner may use it; empty: for logging only.
  role text check (role in ('breakfast', 'main', 'staple', 'salad', 'snack', 'fruit',
                            'protein', 'drink', 'soup', 'sweet')),
  diet text not null check (diet in ('vegetarian', 'eggetarian', 'non_vegetarian')),
  -- What the nutrient numbers are for: 100 g (ingredients) or one serving (dishes).
  basis text not null check (basis in ('100g', 'serving')),
  serving_label text check (char_length(serving_label) <= 40),
  serving_g numeric check (serving_g > 0),
  -- Countable servings (chapati, egg, idli) are planned in whole numbers.
  countable boolean not null default false,
  kcal numeric not null check (kcal >= 0),
  protein_g numeric not null default 0 check (protein_g >= 0),
  carbs_g numeric not null default 0 check (carbs_g >= 0),
  fat_g numeric not null default 0 check (fat_g >= 0),
  fibre_g numeric check (fibre_g >= 0),
  -- e.g. {"iron_mg": 2.1, "calcium_mg": 80, "vitamin_d_ug": 0.4}
  micros jsonb not null default '{}',
  -- Dishes: ingredients for one serving [{"name", "amount", "unit", "group"}],
  -- used for the grocery list and to check allergies.
  ingredients jsonb,
  updated_at timestamptz not null default now()
);

create index foods_role_idx on public.foods (role) where role is not null;
create index foods_name_trgm_idx on public.foods
  using gin ((lower(coalesce(alias, '') || ' ' || name)) extensions.gin_trgm_ops);

alter table public.foods enable row level security;
revoke all on public.foods from anon, authenticated;
grant select on public.foods to authenticated;
create policy "Signed-in users read foods" on public.foods for select to authenticated using (true);

-- ---------------------------------------------------------------------------
-- Meal plans, daily targets and planned meals
-- ---------------------------------------------------------------------------

-- One active plan per person per week (Monday to Sunday); a draft is a preview.
create table public.meal_plans (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  week_start date not null check (extract(isodow from week_start) = 1),
  status text not null check (status in ('draft', 'active', 'superseded')),
  rationale text check (char_length(rationale) <= 2000),
  -- e.g. 'groq:qwen/qwen3.8-27b', 'ollama:qwen3:8b' or 'rules'.
  made_by text,
  -- 'new_week', 'requested' or 'change'.
  reason text,
  -- For a change preview: what it is, e.g. 'Eating out: Sat dinner'.
  change_note text check (char_length(change_note) <= 200),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index meal_plans_one_active_per_week
  on public.meal_plans (profile_id, week_start) where status = 'active';
create index meal_plans_profile_week_idx on public.meal_plans (profile_id, week_start desc);

create table public.daily_targets (
  id uuid primary key default gen_random_uuid(),
  meal_plan_id uuid not null references public.meal_plans (id) on delete cascade,
  profile_id uuid not null references public.profiles (id) on delete cascade,
  day date not null,
  kcal integer not null check (kcal between 800 and 6000),
  protein_g integer not null check (protein_g between 0 and 400),
  carbs_g integer not null check (carbs_g between 0 and 900),
  fat_g integer not null check (fat_g between 0 and 300),
  fibre_g integer check (fibre_g between 0 and 100),
  -- e.g. {"iron_mg": 18, "calcium_mg": 1000, "sodium_mg_max": 2300}
  micros jsonb not null default '{}',
  -- One line per target, e.g. {"kcal": "Maintenance plus a 60-minute session, …"}
  reasons jsonb not null default '{}',
  -- Planned training that day (from the workout plan), in minutes.
  training_minutes integer not null default 0 check (training_minutes >= 0),
  unique (meal_plan_id, day)
);

create table public.planned_meals (
  id uuid primary key default gen_random_uuid(),
  meal_plan_id uuid not null references public.meal_plans (id) on delete cascade,
  profile_id uuid not null references public.profiles (id) on delete cascade,
  day date not null,
  slot text not null check (slot in ('breakfast', 'lunch', 'dinner', 'snack')),
  -- Order within the day (breakfast, snack, lunch, …).
  position integer not null check (position between 0 and 9),
  kind text not null default 'meal' check (kind in ('meal', 'eating_out')),
  name text not null check (char_length(name) between 1 and 200),
  -- [{"food_id", "name", "servings", "unit", "grams"}]
  items jsonb not null default '[]',
  -- Totals worked out from the foods table: {"kcal", "protein_g", "carbs_g", "fat_g",
  -- "fibre_g", "micros": {…}}
  nutrients jsonb not null default '{}',
  note text check (char_length(note) <= 300),
  unique (meal_plan_id, day, position)
);

create index daily_targets_plan_idx on public.daily_targets (meal_plan_id);
create index planned_meals_plan_idx on public.planned_meals (meal_plan_id);

create trigger set_updated_at before update on public.meal_plans
  for each row execute function private.set_updated_at();

-- Access rules: "view both, change your own".
alter table public.meal_plans enable row level security;
alter table public.daily_targets enable row level security;
alter table public.planned_meals enable row level security;

revoke all on public.meal_plans, public.daily_targets, public.planned_meals
  from anon, authenticated;
grant select on public.meal_plans, public.daily_targets, public.planned_meals to authenticated;
-- Plans are written through public.save_meal_plan; afterwards a person can apply
-- or discard their draft and swap meals.
grant update (status) on public.meal_plans to authenticated;
grant delete on public.meal_plans to authenticated;
grant update (name, items, nutrients, note) on public.planned_meals to authenticated;

do $$
declare
  t text;
begin
  foreach t in array array['meal_plans', 'daily_targets', 'planned_meals'] loop
    execute format(
      'create policy "Read household %1$s" on public.%1$I for select to authenticated
         using ((select private.in_my_household(profile_id)))', t);
  end loop;
end;
$$;

create policy "Apply or discard own meal plan"
  on public.meal_plans for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));
create policy "Delete own draft meal plan"
  on public.meal_plans for delete to authenticated
  using (profile_id = (select private.my_profile_id()) and status = 'draft');
create policy "Swap own meals"
  on public.planned_meals for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- Saving a whole plan at once
-- ---------------------------------------------------------------------------

-- Saves a plan with its targets and meals (all or nothing). Signed-in callers may
-- only save their own; the worker (secret key) saves for whoever the job is for.
-- 'active' supersedes the week's active plan; a new draft replaces the old draft.
--
-- p_plan: {"rationale", "made_by", "reason", "change_note", "days": [{"day",
--   "targets": {"kcal", "protein_g", "carbs_g", "fat_g", "fibre_g", "micros", "reasons",
--   "training_minutes"}, "meals": [{"slot", "position", "kind", "name", "items",
--   "nutrients", "note"}]}]}
create function public.save_meal_plan(
  p_profile_id uuid, p_week_start date, p_status text, p_plan jsonb
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_plan_id uuid;
  d jsonb;
  t jsonb;
  m jsonb;
begin
  if auth.role() <> 'service_role' and p_profile_id is distinct from private.my_profile_id() then
    raise exception 'You can only save your own plan' using errcode = '42501';
  end if;
  if p_status not in ('draft', 'active') then
    raise exception 'status must be draft or active' using errcode = '22023';
  end if;

  if p_status = 'active' then
    update public.meal_plans set status = 'superseded'
    where profile_id = p_profile_id and week_start = p_week_start and status = 'active';
  else
    delete from public.meal_plans
    where profile_id = p_profile_id and week_start = p_week_start and status = 'draft';
  end if;

  insert into public.meal_plans (profile_id, week_start, status, rationale, made_by, reason,
                                 change_note)
  values (p_profile_id, p_week_start, p_status, p_plan ->> 'rationale', p_plan ->> 'made_by',
          p_plan ->> 'reason', p_plan ->> 'change_note')
  returning id into new_plan_id;

  for d in select * from jsonb_array_elements(coalesce(p_plan -> 'days', '[]')) loop
    t := d -> 'targets';
    insert into public.daily_targets (meal_plan_id, profile_id, day, kcal, protein_g, carbs_g,
                                      fat_g, fibre_g, micros, reasons, training_minutes)
    values (new_plan_id, p_profile_id, (d ->> 'day')::date, (t ->> 'kcal')::integer,
            (t ->> 'protein_g')::integer, (t ->> 'carbs_g')::integer, (t ->> 'fat_g')::integer,
            (t ->> 'fibre_g')::integer, coalesce(t -> 'micros', '{}'),
            coalesce(t -> 'reasons', '{}'), coalesce((t ->> 'training_minutes')::integer, 0));

    for m in select * from jsonb_array_elements(coalesce(d -> 'meals', '[]')) loop
      insert into public.planned_meals (meal_plan_id, profile_id, day, slot, position, kind,
                                        name, items, nutrients, note)
      values (new_plan_id, p_profile_id, (d ->> 'day')::date, m ->> 'slot',
              (m ->> 'position')::integer, coalesce(m ->> 'kind', 'meal'), m ->> 'name',
              coalesce(m -> 'items', '[]'), coalesce(m -> 'nutrients', '{}'), m ->> 'note');
    end loop;
  end loop;

  return new_plan_id;
end;
$$;

-- Applying a draft: it becomes active and the old active plan is superseded.
create function public.apply_meal_plan(p_plan_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  draft public.meal_plans;
begin
  select * into draft from public.meal_plans
  where id = p_plan_id and status = 'draft' and profile_id = private.my_profile_id();
  if draft.id is null then
    raise exception 'No draft plan of yours with that id' using errcode = 'P0002';
  end if;
  update public.meal_plans set status = 'superseded'
  where profile_id = draft.profile_id and week_start = draft.week_start and status = 'active';
  update public.meal_plans set status = 'active' where id = draft.id;
end;
$$;

revoke execute on function public.save_meal_plan(uuid, date, text, jsonb) from public, anon;
revoke execute on function public.apply_meal_plan(uuid) from public, anon;
grant execute on function public.save_meal_plan(uuid, date, text, jsonb) to authenticated, service_role;
grant execute on function public.apply_meal_plan(uuid) to authenticated;
