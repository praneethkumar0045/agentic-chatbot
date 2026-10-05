"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";
import { AuthLoading, AuthScreen, AuthMode } from "@/components/auth/auth-screen";
import { ApiError } from "@/lib/api/errors";
import {
  getCurrentUser,
  login,
  logout,
  register,
  refreshSession,
  subscribeToSession,
} from "@/lib/auth/client";
import type { User } from "@/lib/auth/types";

type AuthGateProps = {
  children: (user: User, signOut: () => Promise<void>) => ReactNode;
};

export function AuthGate({ children }: AuthGateProps) {
  const [user, setUser] = useState<User | null>(null);
  const [mode, setMode] = useState<AuthMode>("login");
  const [busy, setBusy] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [error, setError] = useState("");

  useEffect(
    () =>
      subscribeToSession((active) => {
        if (!active) setUser(null);
      }),
    [],
  );

  useEffect(() => {
    let mounted = true;
    void refreshSession()
      .then(() => getCurrentUser())
      .then((currentUser) => {
        if (mounted) setUser(currentUser);
      })
      .catch((caught: unknown) => {
        if (mounted && (!(caught instanceof ApiError) || caught.status !== 401)) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to check your session. Please try again.",
          );
        }
      })
      .finally(() => {
        if (mounted) setIsInitializing(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = useCallback(
    async (values: { name: string; email: string; password: string }) => {
      setBusy(true);
      setError("");
      try {
        if (mode === "register") {
          await register(values);
        }
        await login(values);
        const currentUser = await getCurrentUser();
        setUser(currentUser);
      } catch (caught) {
        setError(
          caught instanceof ApiError
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "Unable to sign in right now. Please try again.",
        );
      } finally {
        setBusy(false);
      }
    },
    [mode],
  );

  const signOut = useCallback(async () => {
    setUser(null);
    try {
      await logout();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? `You were signed out, but the server could not revoke this session: ${caught.message}`
          : "You were signed out, but the server could not revoke this session.",
      );
    }
  }, []);

  if (!user) {
    if (isInitializing) return <AuthLoading />;
    return (
      <AuthScreen
        mode={mode}
        busy={busy}
        error={error}
        onModeChange={(nextMode) => {
          setMode(nextMode);
          setError("");
        }}
        onSubmit={handleSubmit}
      />
    );
  }

  return <>{children(user, signOut)}</>;
}
