"use client";

import { AuthGate } from "@/components/auth/auth-gate";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export default function Home() {
  return (
    <AuthGate>
      {(user, signOut) => <ChatWorkspace user={user} onSignOut={signOut} />}
    </AuthGate>
  );
}
