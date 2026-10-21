import { type ComponentRef, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { Overlay } from '@/components/Overlay';
import { ApiError, apiGet, apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import type { WeekMealPlan } from './meals';

type ChatMessage = Schemas['ChatMessage'];
type ChatReply = Schemas['ChatReply'];

const EXAMPLES = [
  'No paneer this week, more eggs please',
  'Aloo paratha for Sunday breakfast',
  'I’m eating out on Saturday night',
  'Lighter dinners on rest days',
];

// "Ask for a change": the week's chat about the meal plan. Each change comes
// back as a preview on the page, to use or keep.
export function ChatOverlay({
  open,
  onClose,
  onWeek,
  onAddDish,
}: {
  open: boolean;
  onClose: () => void;
  onWeek: (week: WeekMealPlan) => void;
  onAddDish: (name: string) => void;
}) {
  const { colors } = useTheme();
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);

  useEffect(() => {
    if (!open || messages) return;
    apiGet<ChatMessage[]>(`/api/me/meal-chat?today=${todayLocal()}`)
      .then(setMessages)
      .catch(() => setMessages([]));
  }, [open, messages]);

  useEffect(() => {
    scroll.current?.scrollToEnd({ animated: true });
  }, [messages, sending]);

  const send = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError(null);
    setMessages((m) => [
      ...(m ?? []),
      {
        id: 'pending',
        role: 'user',
        text: trimmed,
        created_at: new Date().toISOString(),
        add_dishes: [],
      },
    ]);
    setText('');
    try {
      const reply = await apiPost<ChatReply>('/api/me/meal-chat', {
        today: todayLocal(),
        text: trimmed,
      });
      setMessages(reply.messages);
      onWeek(reply.week);
    } catch (e) {
      setMessages((m) => (m ?? []).filter((x) => x.id !== 'pending'));
      setText(trimmed);
      setError(e instanceof ApiError ? e.message : 'Couldn’t send. Please try again.');
    } finally {
      setSending(false);
    }
  };

  const muted = { color: colors.textMuted };
  return (
    <Overlay
      title="Ask for a change"
      open={open}
      onClose={onClose}
      scroll={false}
      footer={
        <View style={styles.inputRow}>
          <TextInput
            value={text}
            onChangeText={setText}
            onSubmitEditing={() => send(text)}
            placeholder="e.g. no paneer this week"
            placeholderTextColor={colors.textMuted}
            accessibilityLabel="Your message"
            editable={!sending}
            style={[styles.input, { borderColor: colors.border, color: colors.text }]}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={() => send(text)}
            disabled={sending || !text.trim()}
            style={[styles.send, { backgroundColor: text.trim() ? colors.primary : colors.border }]}
          >
            <Text style={[styles.sendText, { color: colors.onPrimary }]}>Send</Text>
          </Pressable>
        </View>
      }
    >
      <ScrollView ref={scroll} contentContainerStyle={styles.messages}>
        {!messages && <ActivityIndicator color={colors.primary} />}
        {messages?.length === 0 && (
          <View style={styles.intro}>
            <Text style={[styles.body, { color: colors.text }]}>
              Tell me what you’d like to change this week. I’ll make a preview for you to check
              before anything changes.
            </Text>
            {EXAMPLES.map((example) => (
              <Pressable
                key={example}
                accessibilityRole="button"
                onPress={() => send(example)}
                style={[styles.example, { borderColor: colors.border }]}
              >
                <Text style={[styles.body, { color: colors.text }]}>{example}</Text>
              </Pressable>
            ))}
          </View>
        )}
        {messages?.map((m) => (
          <View
            key={m.id}
            style={[
              styles.bubble,
              m.role === 'user'
                ? [styles.mine, { backgroundColor: colors.primarySoft }]
                : [styles.theirs, { backgroundColor: colors.surface, borderColor: colors.border }],
            ]}
          >
            <Text style={[styles.body, { color: colors.text }]}>{m.text}</Text>
            {m.draft_plan_id && (
              <Pressable accessibilityRole="button" onPress={onClose}>
                <Text style={[styles.link, { color: colors.primary }]}>See the preview →</Text>
              </Pressable>
            )}
            {(m.add_dishes ?? []).map((dish) => (
              <Pressable key={dish} accessibilityRole="button" onPress={() => onAddDish(dish)}>
                <Text style={[styles.link, { color: colors.primary }]}>Add “{dish}” →</Text>
              </Pressable>
            ))}
          </View>
        ))}
        {sending && (
          <View style={[styles.bubble, styles.theirs, { borderColor: colors.border }]}>
            <ActivityIndicator color={colors.primary} />
          </View>
        )}
        {error && <Text style={{ color: colors.alert }}>{error}</Text>}
        {messages && messages.length > 0 && (
          <Text style={[styles.caption, muted]}>
            Changes are only made when you tap “Use this plan” on the preview.
          </Text>
        )}
      </ScrollView>
    </Overlay>
  );
}

const styles = StyleSheet.create({
  messages: {
    gap: spacing.sm,
    paddingBottom: spacing.md,
  },
  intro: {
    gap: spacing.sm,
  },
  example: {
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  bubble: {
    maxWidth: '88%',
    padding: spacing.sm,
    borderRadius: radius.md,
    gap: spacing.xs,
  },
  mine: {
    alignSelf: 'flex-end',
  },
  theirs: {
    alignSelf: 'flex-start',
    borderWidth: 1,
  },
  body: {
    fontSize: 15,
    lineHeight: 21,
  },
  caption: {
    fontSize: 12,
    textAlign: 'center',
  },
  link: {
    fontSize: 14,
    fontWeight: '700',
  },
  inputRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
  },
  send: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    justifyContent: 'center',
  },
  sendText: {
    fontSize: 15,
    fontWeight: '700',
  },
});
