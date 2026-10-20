import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { AppState, Platform } from 'react-native';

// The website uses Supabase only for signing in (and later, file uploads).
// All app data goes through our API; see context/architecture.md.

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabasePublishableKey = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

if (!supabaseUrl || !supabasePublishableKey) {
  throw new Error('Missing Supabase settings: copy frontend/.env.example to frontend/.env');
}

export const supabase = createClient(supabaseUrl, supabasePublishableKey, {
  auth: {
    // Keeps people signed in between visits. AsyncStorage works on the web
    // (browser storage) and in the future iPhone app.
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

// In the phone app, only refresh the sign-in token while the app is open.
if (Platform.OS !== 'web') {
  AppState.addEventListener('change', (state) => {
    if (state === 'active') {
      supabase.auth.startAutoRefresh();
    } else {
      supabase.auth.stopAutoRefresh();
    }
  });
}
