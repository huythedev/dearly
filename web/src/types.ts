export type Support = 'listen' | 'relate' | 'brainstorm';
export type Audience = 'privateOnly' | 'companion' | 'community';
export type Role = 'user' | 'moderator' | 'admin';
export interface Profile {
  id: string; nickname: string; age: number; ageVerified: boolean; symbol: string;
  bio: string; interests: string[]; support: Support; pace: string;
}
export interface Journal {
  encrypted?: boolean; locked?: boolean;
  id: string; authorID: string; title: string; body: string; sharedText: string;
  audience: Audience; connectionID: string | null; anonymous: boolean;
  commentsEnabled: boolean; support: Support; date: number; listeners: string[];
  canInviteAuthor: boolean; moderationHidden: boolean;
}
export interface Comment { id: string; journalID: string; authorID: string; text: string; date: number }
export interface Invitation { id: string; senderID: string; recipientID: string; date: number }
export interface Message { id: string; connectionID: string; senderID: string; text: string; date: number; encrypted?: boolean; locked?: boolean }
export interface Connection {
  id: string; members: string[]; startedAt: number; endedAt: number | null; paused: boolean;
  checkIns: Record<string, string[]>; bestStreak: number; serverTotalDays: number; serverCurrentStreak: number;
}
export interface AppState {
  currentUserID: string; currentUserRole?: Role; permissions?: string[]; profiles: Profile[];
  journals: Journal[]; comments: Comment[]; invitations: Invitation[]; connections: Connection[];
  messages: Message[]; suggestedUserIDs: string[];
}
export interface Envelope { state: AppState; serverNow: number }
export interface Page<T, C = string> { items: T[]; nextCursor: C | null }
export interface GardenPage extends Page<Connection> { profiles: Profile[] }
export interface Command { requestID: string; kind: string; payload: Record<string, unknown> }
export interface StaffReport {
  id: string; reporterNickname: string; reportedNickname: string; reason: string; status: string;
  date: number; evidence: string; canHide: boolean; canRestore: boolean; reviewNote: string;
}
export interface StaffUser {
  id: string; username: string; nickname: string; role: Role;
  suspended: boolean; ageVerified: boolean; birthDate: string;
}
export interface AuditEntry {
  id: number; actorName: string; action: string; targetID: string;
  detail: Record<string, string>; date: number;
}

export const supportLabels: Record<Support, string> = {
  listen: 'Just listen', relate: 'Share experiences', brainstorm: 'Think it through together',
};
export const audienceLabels: Record<Audience, string> = {
  privateOnly: 'Only me', companion: 'Companion', community: 'Community',
};
export const SWIFT_EPOCH = 978307200;
export const fromSwift = (seconds: number) => new Date((seconds + SWIFT_EPOCH) * 1000);
export const utcDay = (seconds: number) => fromSwift(seconds).toISOString().slice(0, 10);
export const activeConnection = (state: AppState) => state.connections.find(c => c.endedAt === null && c.members.includes(state.currentUserID));
export function mergeByID<T extends { id: string | number }>(first: T[], second: T[]): T[] {
  return [...new Map([...first, ...second].map(item => [item.id, item])).values()];
}
export function gardenStage(connection: Connection): number {
  if (connection.serverTotalDays >= 30) return 5;
  if (connection.bestStreak >= 14) return 4;
  if (connection.bestStreak >= 7) return 3;
  if (connection.bestStreak >= 3) return 2;
  return connection.serverTotalDays > 0 ? 1 : 0;
}
