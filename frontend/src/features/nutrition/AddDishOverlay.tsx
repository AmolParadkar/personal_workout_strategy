import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, ChipSelect, Field, TextField } from '@/components/form';
import { Overlay } from '@/components/Overlay';
import { ApiError, apiGet, apiPost, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import type { FoodOption } from './meals';

type Draft = Schemas['DishDraft'];
type Ingredient = Schemas['DishIngredient'];
type Role = Schemas['DishInput']['role'];
type IngredientOption = Schemas['IngredientOption'];

const ROLES: { value: Role; label: string }[] = [
  { value: 'breakfast', label: 'Breakfast' },
  { value: 'main', label: 'Curry, dal or sabzi' },
  { value: 'staple', label: 'Roti or rice' },
  { value: 'salad', label: 'Salad or raita' },
  { value: 'snack', label: 'Snack' },
];
const PREVIEW_DELAY_MS = 400;
const NEW_INGREDIENT = 'New ingredient';

// "Add a dish": the AI drafts the recipe from its name, you check the ingredients
// and grams (and what each is matched to), and the nutrients are worked out from
// the ingredient database. Saved for the household. Opened afresh each time
// (the page gives it a new key).
export function AddDishOverlay({
  open,
  initialName,
  onClose,
  onSaved,
}: {
  open: boolean;
  initialName: string;
  onClose: () => void;
  onSaved?: (dish: FoodOption) => void;
}) {
  const { colors } = useTheme();
  const [name, setName] = useState(initialName);
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<FoodOption | null>(null);
  const [matching, setMatching] = useState<number | null>(null);

  const input = (d: Draft) => ({
    name: d.name,
    role: d.role,
    serves: d.serves,
    ingredients: d.ingredients.map((i) => ({
      name: i.name,
      grams: i.grams,
      food_id: i.food_id,
      approximate: i.approximate,
    })),
  });

  // Edits: numbers worked out again after a short pause.
  const [edited, setEdited] = useState<Draft | null>(null);
  useEffect(() => {
    if (!edited) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      apiPost<Draft>('/api/me/dishes/preview', input(edited))
        .then((next) => {
          if (!cancelled) setDraft(next);
        })
        .catch(() => {});
    }, PREVIEW_DELAY_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [edited]);

  const edit = (change: Partial<Draft>) => {
    if (!draft) return;
    const next = { ...draft, ...change };
    setDraft(next);
    setEdited(next);
  };
  const editIngredient = (n: number, change: Partial<Ingredient>) =>
    edit({ ingredients: draft!.ingredients.map((i, k) => (k === n ? { ...i, ...change } : i)) });

  const makeDraft = async () => {
    setBusy(true);
    setError(null);
    try {
      setDraft(
        await apiPost<Draft>('/api/me/dishes/draft', { name: name.trim(), note: note || null }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t draft the recipe. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const dish = await apiPost<FoodOption>('/api/me/dishes', input(draft));
      setSaved(dish);
      onSaved?.(dish);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t save. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const text = { color: colors.text };
  const muted = { color: colors.textMuted };

  return (
    <Overlay title="Add a dish" open={open} onClose={onClose}>
      {saved ? (
        <View style={styles.section}>
          <Text style={[styles.heading, text]}>Saved: {saved.name}</Text>
          <Text style={[styles.body, muted]}>
            {Math.round(saved.kcal)} kcal and {saved.protein_g} g protein a serving. It’s now in
            your household’s dishes: new plans can use it, and you can swap it in or ask for it in
            the chat.
          </Text>
          <Button label="Done" onPress={onClose} />
        </View>
      ) : !draft ? (
        <View style={styles.section}>
          <Field label="Dish name">
            <TextField
              label="Dish name"
              value={name}
              onChange={setName}
              placeholder="e.g. Aloo paratha, Thai green curry"
            />
          </Field>
          <Field label="Anything special about it? (optional)">
            <TextField
              label="Anything special about it"
              value={note}
              onChange={setNote}
              placeholder="e.g. no onion or garlic, made with ghee"
            />
          </Field>
          <Text style={[styles.caption, muted]}>
            The AI writes a typical recipe with raw ingredient weights. You check it, and the
            nutrients are worked out from the ingredient database.
          </Text>
          <Button
            label={busy ? 'Drafting…' : 'Draft the recipe'}
            onPress={makeDraft}
            disabled={busy || name.trim().length < 2}
          />
          {busy && <ActivityIndicator color={colors.primary} />}
        </View>
      ) : (
        <View style={styles.section}>
          <Field label="Name">
            <TextField label="Name" value={draft.name} onChange={(v) => edit({ name: v })} />
          </Field>
          <Field label="What kind of dish?">
            <ChipSelect
              options={ROLES}
              selected={[draft.role]}
              onChange={(r) => r[0] && edit({ role: r[0] })}
            />
          </Field>
          <Field label="The recipe makes (servings)">
            <TextField
              label="Servings"
              value={String(draft.serves)}
              inputMode="numeric"
              onChange={(v) => {
                const n = Math.round(Number(v));
                if (n >= 1 && n <= 20) edit({ serves: n });
              }}
            />
          </Field>

          <View style={[styles.numbers, { borderColor: colors.border }]}>
            <Text style={[styles.heading, text]}>One serving</Text>
            <Text style={[styles.body, text]}>
              {Math.round(draft.per_serving.kcal)} kcal · {Math.round(draft.per_serving.protein_g)}{' '}
              g protein · {Math.round(draft.per_serving.carbs_g)} g carbs ·{' '}
              {Math.round(draft.per_serving.fat_g)} g fat
            </Text>
            {draft.unmatched.length > 0 && (
              <Text style={[styles.caption, { color: colors.caution }]}>
                Not counted (no match): {draft.unmatched.join(', ')}
              </Text>
            )}
          </View>

          <Text style={[styles.heading, text]}>Ingredients (whole recipe, raw)</Text>
          {draft.ingredients.map((ingredient, n) => (
            <View key={n} style={[styles.ingredient, { borderColor: colors.border }]}>
              <View style={styles.ingredientLine}>
                <Text style={[styles.body, text, styles.grow]}>{ingredient.name}</Text>
                <TextInput
                  value={String(ingredient.grams)}
                  onChangeText={(v) => {
                    const g = Number(v.replace(',', '.'));
                    if (g > 0) editIngredient(n, { grams: g });
                  }}
                  inputMode="decimal"
                  accessibilityLabel={`${ingredient.name} grams`}
                  style={[styles.grams, { borderColor: colors.border, color: colors.text }]}
                />
                <Text style={[styles.caption, muted]}>g</Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Remove ${ingredient.name}`}
                  onPress={() => edit({ ingredients: draft.ingredients.filter((_, k) => k !== n) })}
                >
                  <Text style={[styles.body, muted]}>✕</Text>
                </Pressable>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Change the match for ${ingredient.name}`}
                onPress={() => setMatching(matching === n ? null : n)}
              >
                <Text
                  style={[
                    styles.caption,
                    { color: ingredient.food_id ? colors.textMuted : colors.caution },
                  ]}
                >
                  {ingredient.food_id
                    ? `= ${ingredient.food_name}${ingredient.approximate ? ' (closest match)' : ''} · ${Math.round(ingredient.kcal)} kcal`
                    : 'No match: not counted'}
                  <Text style={{ color: colors.primary }}> · change</Text>
                </Text>
              </Pressable>
              {matching === n && (
                <IngredientSearch
                  initial={ingredient.name === NEW_INGREDIENT ? '' : ingredient.name}
                  onPick={(option) => {
                    editIngredient(n, {
                      // A new ingredient takes the name of what it was matched to.
                      name:
                        ingredient.name === NEW_INGREDIENT
                          ? option.name.split(',')[0]
                          : ingredient.name,
                      food_id: option.id,
                      food_name: option.name,
                      approximate: false,
                    });
                    setMatching(null);
                  }}
                />
              )}
            </View>
          ))}
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              edit({
                ingredients: [
                  ...draft.ingredients,
                  { name: NEW_INGREDIENT, grams: 50, approximate: false, kcal: 0, protein_g: 0 },
                ],
              });
              setMatching(draft.ingredients.length);
            }}
          >
            <Text style={[styles.link, { color: colors.primary }]}>+ Add an ingredient</Text>
          </Pressable>
          <View style={styles.row}>
            <Button label={busy ? 'Saving…' : 'Save dish'} onPress={save} disabled={busy} />
            <Button label="Start again" variant="secondary" onPress={() => setDraft(null)} />
          </View>
        </View>
      )}
      {error && <Text style={{ color: colors.alert }}>{error}</Text>}
    </Overlay>
  );
}

// Find an ingredient in the database (USDA, per 100 g) by name.
function IngredientSearch({
  initial,
  onPick,
}: {
  initial: string;
  onPick: (option: IngredientOption) => void;
}) {
  const { colors } = useTheme();
  const [search, setSearch] = useState(initial);
  const [found, setFound] = useState<IngredientOption[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      if (search.trim().length < 2) return;
      apiGet<IngredientOption[]>(`/api/ingredients?search=${encodeURIComponent(search.trim())}`)
        .then((rows) => {
          if (!cancelled) setFound(rows);
        })
        .catch(() => {
          if (!cancelled) setFound([]);
        });
    }, PREVIEW_DELAY_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [search]);

  return (
    <View style={styles.searchBox}>
      <TextInput
        value={search}
        onChangeText={setSearch}
        accessibilityLabel="Search ingredients"
        placeholder="e.g. chickpea flour"
        placeholderTextColor={colors.textMuted}
        style={[styles.searchInput, { borderColor: colors.border, color: colors.text }]}
      />
      {found?.map((option) => (
        <Pressable
          key={option.id}
          accessibilityRole="button"
          accessibilityLabel={`Use ${option.name}`}
          onPress={() => onPick(option)}
          style={[styles.option, { borderColor: colors.border }]}
        >
          <Text style={[styles.caption, { color: colors.text }]}>{option.name}</Text>
          <Text style={[styles.caption, { color: colors.textMuted }]}>
            {option.kcal} kcal · {option.protein_g} g protein per 100 g
          </Text>
        </Pressable>
      ))}
      {found?.length === 0 && (
        <Text style={[styles.caption, { color: colors.textMuted }]}>
          Nothing found. Try a simpler name, e.g. “lentils”.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: spacing.md,
  },
  heading: {
    fontSize: 16,
    fontWeight: '700',
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
  },
  caption: {
    fontSize: 12,
    lineHeight: 17,
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
  numbers: {
    gap: 4,
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  ingredient: {
    gap: 4,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
  },
  ingredientLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  grow: {
    flex: 1,
  },
  grams: {
    width: 64,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.xs,
    paddingVertical: 4,
    textAlign: 'right',
    fontSize: 14,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  searchBox: {
    gap: spacing.xs,
  },
  searchInput: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    fontSize: 14,
  },
  option: {
    padding: spacing.xs,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
});
