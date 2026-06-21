import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getProfile, type UserProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface ProfileContextValue {
  profile: UserProfile | null;
  setProfile: (p: UserProfile | null) => void;
}

const ProfileContext = createContext<ProfileContextValue>({
  profile: null,
  setProfile: () => {},
});

export function ProfileProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      getProfile().then(setProfile).catch(() => {});
    } else {
      setProfile(null);
    }
  }, [isAuthenticated]);

  return (
    <ProfileContext.Provider value={{ profile, setProfile }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  return useContext(ProfileContext);
}
