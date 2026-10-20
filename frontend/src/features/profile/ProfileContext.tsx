import { createContext, type ReactNode, useContext, useState } from 'react';

export type Profile = {
  id: string;
  name: string;
  doing75Hard: boolean;
};

// Placeholder profiles until sign-in and the profiles table exist (M1, steps 5–7).
const placeholderProfiles: Profile[] = [
  { id: 'amol', name: 'Amol', doing75Hard: true },
  { id: 'spouse', name: 'Spouse', doing75Hard: false },
];

type ProfileContextValue = {
  profiles: Profile[];
  activeProfile: Profile;
  setActiveProfileId: (id: string) => void;
};

// A React "context" lets any screen read the selected profile without
// passing it down through every component.
const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [activeId, setActiveProfileId] = useState(placeholderProfiles[0].id);
  const activeProfile = placeholderProfiles.find((p) => p.id === activeId) ?? placeholderProfiles[0];

  return (
    <ProfileContext.Provider
      value={{ profiles: placeholderProfiles, activeProfile, setActiveProfileId }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile(): ProfileContextValue {
  const value = useContext(ProfileContext);
  if (!value) {
    throw new Error('useProfile must be used inside ProfileProvider');
  }
  return value;
}
