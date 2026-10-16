export type GuideRoute = 'journal' | 'community' | 'companion' | 'garden';
export const guideSteps = [
  { target: 'compose', route: 'journal', title: 'A page of your own',
    body: 'Start a journal entry here. It begins private. In the editor, you choose whether to share a passage with your companion or the community.' },
  { target: 'pages', route: 'journal', title: 'Find your pages',
    body: 'Your pages stay in your journal. Open an entry to edit it, or browse earlier pages whenever you need them.' },
  { target: 'community', route: 'community', title: 'Listen with kindness',
    body: 'Explore shared passages and the kind of support each writer wants. Anonymous stories hide the nickname; the rest of a private entry stays private.' },
  { target: 'companion', route: 'companion', title: 'A connection takes two',
    body: 'Companion matching requires verified ages and an accepted invitation. Both people choose to connect before their private chat opens.' },
  { target: 'garden', route: 'garden', title: 'Grow a little together',
    body: 'Once you have a companion, check in on the same UTC day to grow your garden. You can pause when you need a break and keep your earned rewards.' },
  { target: 'settings', route: 'garden', title: 'Make Dearly feel like you',
    body: 'Open account settings for your profile, language and appearance. Choose Take a guided tour there whenever you want another look.' },
] satisfies { target: string; route: GuideRoute; title: string; body: string }[];

export const guideStorageKey = (userID: string) => `dearly.guide.v1:${userID}`;
export function hasSeenGuide(userID: string): boolean {
  try { return localStorage.getItem(guideStorageKey(userID)) === 'seen'; }
  catch { return false; }
}
export function rememberGuide(userID: string) {
  try { localStorage.setItem(guideStorageKey(userID), 'seen'); }
  catch { /* The guide still closes if this browser cannot save preferences. */ }
}
