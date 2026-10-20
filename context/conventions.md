# Conventions

← [Hub: skills.md](skills.md) · Related: [Architecture](architecture.md) · [Data model](data-model.md) · [Roadmap](roadmap.md)

How code and docs are written in this project, so everything reads as if one person wrote it.

## General

- **Keep it simple.** Two users; no premature scaling, caching or abstraction.
- **Logic in the backend, screens in the frontend** (see [Architecture](architecture.md#components)).
- **Comments explain *why*,** not what. Amol is new to TypeScript, so frontend code gets a short comment wherever a pattern isn't obvious.
- **No secrets in code.** Keys go in `.env` (ignored by git); `.env.example` lists the names.

## Python (`backend/`)

- Python 3.12, managed with **uv**.
- **ruff** for formatting and linting.
- Type hints everywhere; **Pydantic v2** models for every request, response and job payload (in `backend/core/`).
- **FastAPI** for the API. Routes are thin: validate, call `core`, return.
- Names: `snake_case` for files, functions and variables; `PascalCase` for classes.
- **pytest** for tests in `backend/tests/`, mirroring the `core/` layout.
- Packages `api`, `core` and `worker` are top-level inside `backend/`, so imports read `from core.models.health import HealthResponse`.
- Commands (run inside `backend/`):
  - `uv run pytest`: run the tests
  - `uv run ruff check .` and `uv run ruff format .`: lint and format
  - `uv run uvicorn api.main:app --reload`: run the API locally at http://localhost:8000 (interactive docs at `/docs`)

## TypeScript (`frontend/`)

- **Expo SDK 58** with **Expo Router**; TypeScript in strict mode. The website is built as a single-page app (`web.output: "single"`).
- **Expo changes a lot between versions:** before using an Expo or React Native API, check the docs for the installed version (https://docs.expo.dev/llms.txt is the index) rather than relying on memory.
- Folder layout inside `frontend/src/`:
  - `app/`: one thin route file per page (`app/today.tsx` is the URL `/today`); `_layout.tsx` is the frame around every page.
  - `features/<page>/`: that page's components and data hooks; `features/navigation/pages.ts` is the single list of pages.
  - `components/`: shared pieces (`NavBar`, `ProfileSwitcher`, `PagePlaceholder`).
  - `theme/`: colours, spacing, sizes.
- Imports use the `@/` alias for `src/` (`import { colors } from '@/theme'`).
- Names: `PascalCase` for components and their files (`MetricCard.tsx`); `camelCase` for functions and variables; route files in `kebab-case` (`plan-for-today.tsx`).
- Add libraries with `npx expo install <package>` (not `npm install`), so versions match the Expo SDK.
- `Link asChild` needs a single style object on its child: wrap style lists in `StyleSheet.flatten([...])`.
- API types are **generated** from the backend; never hand-written. Regenerate after any backend model change.
- Linting with ESLint (Expo's config); type checking with `tsc`.
- Commands (run inside `frontend/`):
  - `npm run web`: run the website locally at http://localhost:8081, reloading on save (if changes stop showing, restart with `npx expo start --web --clear`)
  - `npm run lint` and `npm run typecheck`: run both before calling anything done
  - `npm run build:web`: build the production site into `dist/` (what Vercel runs)
  - `npx expo-doctor`: check dependency and config problems

## Theme

- Colours live in `frontend/src/theme/colors.ts` (`darkColors`, `lightColors`); components read them with `useTheme()`. **Never hard-code a colour in a component**, or it will break in one of the two modes.
- Dark is the default; the header toggle switches mode and the choice is saved per device.
- `primary` (green) is for actions, active states and progress. `good` / `caution` / `alert` are for health signals only (e.g. a recovery score), never decoration.
- Any new text colour must pass WCAG AA contrast (4.5:1) on `background` and `surface` in both themes; check it before adding.
- Styles that don't depend on the theme stay in `StyleSheet.create`; theme colours are added inline (`[styles.title, { color: colors.text }]`).

## Database

- Tables `snake_case` and plural (`food_logs`); columns `snake_case`.
- Every table has `id`, `created_at`, `updated_at`; person-owned tables have `profile_id` and access rules.
- **Access rules (row level security) are switched on for every table**, with no exceptions.
- Every change is a new migration in `supabase/migrations/`, named `YYYYMMDDHHMMSS_short_description.sql`. Never edit a migration that's already been applied.
- [Data model](data-model.md) is updated in the same change as the migration.

## LLM usage

- Prompts live in `backend/core/prompts/`, one file per job type.
- LLM output is always requested as JSON and **validated with a Pydantic model**; invalid output is a failed attempt, not data.
- **Numbers from data, words from the LLM:** nutrients from the food database, forecasts from calculations.
- Each job type declares whether it's local-only (see [Architecture: Privacy routing](architecture.md#privacy-routing)).

## Testing

- Unit tests for core logic: nutrient calculation, forecasts, job queue (claiming, retries, stuck jobs), 75 Hard reset rule, video scoring.
- LLM calls are mocked in tests.
- A check that the generated frontend types are up to date.

## Development workflow

Every piece of work (usually one roadmap item) follows the same steps:

1. **Pick** the next item from the [roadmap](roadmap.md) and re-read its page spec and the relevant [data model](data-model.md) / [architecture](architecture.md) sections.
2. **Clarify** anything unclear or missing in the spec before writing code; record the answer in the docs.
3. **Branch:** `feature/<short-name>` off `main`.
4. **Plan:** a short outline of the files and tables to change; agreed before building anything large.
5. **Build:** database migration first, then backend (models → core logic → API), then frontend.
6. **Test:** unit tests for the logic, then run it locally and check it works in the browser.
7. **Update docs:** spec changes, data model, architecture, hub change log; tick the roadmap item.
8. **Review:** Amol looks at the result; fixes are made on the same branch.
9. **Commit and merge** to `main` (Claude asks first).
10. **Deploy:** Vercel deploys `main`; check the live site.

## Git

- `main` is always deployable. Work happens on short branches named `feature/<short-name>` or `fix/<short-name>`.
- Commit messages: short imperative summary ("Add water quick-add buttons"), body if the *why* isn't obvious.
- Claude asks before committing or pushing.

## Docs

- All Markdown files live in `context/` (only exception: the root `CLAUDE.md`).
- **Functionality, structure or technical changes** → update the [hub](skills.md) and add a dated line to its change log.
- **Page-specific changes** → the page's file in [pages/](pages/).
- **Table changes** → [data-model.md](data-model.md). **Flow or component changes** → [architecture.md](architecture.md). **Milestone progress** → [roadmap.md](roadmap.md).
- Every file starts with a link back to the hub and ends with related links; new files follow the same pattern so the docs stay a connected graph.

## Related

- [Architecture](architecture.md): where each kind of code lives.
- [Data model](data-model.md): the tables these rules apply to.
- [Roadmap](roadmap.md): what's being built next.
