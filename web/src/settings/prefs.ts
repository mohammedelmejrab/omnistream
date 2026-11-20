import { usePreference } from '@/hooks/usePreference';

export const BACKGROUND_KEY = 'omnistream.backgroundEffects';

/** Settings > Display toggle for the home dot background (spec 9, decision 24). */
export function useBackgroundEffects(): [boolean, (on: boolean) => void] {
  return usePreference<boolean>(BACKGROUND_KEY, true);
}
