"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import styles from "./auth-screen.module.css";

export type AuthMode = "login" | "register";

type AuthScreenProps = {
  mode: AuthMode;
  busy: boolean;
  error: string;
  onModeChange: (mode: AuthMode) => void;
  onSubmit: (values: { name: string; email: string; password: string }) => Promise<void>;
};

export function AuthLoading() {
  return (
    <main className={styles.page} aria-busy="true" aria-label="Checking your session">
      <section className={styles.formSide}>
        <div className={styles.loadingState}>
          <span className={styles.brandMark} aria-hidden="true">✳</span>
          <span className={styles.spinner} />
          <span>Preparing your space…</span>
        </div>
      </section>
    </main>
  );
}

export function AuthScreen({
  mode,
  busy,
  error,
  onModeChange,
  onSubmit,
}: AuthScreenProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const isRegistering = mode === "register";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({ name, email, password });
    setPassword("");
  }

  return (
    <main className={styles.page}>
      <section className={styles.story} aria-label="Medha introduction">
        <Link className={styles.brand} href="/" aria-label="Medha home">
          <span className={styles.brandMark} aria-hidden="true">✳</span>
          <span>Medha</span>
        </Link>
        <div className={styles.storyContent}>
          <div className={styles.orbit} aria-hidden="true">
            <span className={styles.orbitRing} />
            <span className={styles.orbitRingAlt} />
            <span className={styles.orbitSpark}>✦</span>
          </div>
          <p className={styles.eyebrow}>A LITTLE MORE CLARITY, EVERY DAY</p>
          <h1>A calmer space<br />for your <em>big ideas.</em></h1>
          <p className={styles.storyCopy}>
            Thoughtful conversations begin with a single question. Pick up right
            where curiosity takes you.
          </p>
          <div className={styles.storyFootnote}><span /> Your space is ready when you are</div>
        </div>
        <span className={styles.decor} aria-hidden="true">✳</span>
      </section>

      <section className={styles.formSide}>
        <div className={styles.formWrap}>
          <div className={styles.mobileBrand}>
            <span className={styles.brandMark} aria-hidden="true">✳</span>
            <span>Medha</span>
          </div>
          <div className={styles.formHeader}>
            <div className={styles.formEyebrow}>{isRegistering ? "A FRESH START" : "WELCOME BACK"}</div>
            <h2>{isRegistering ? "Create your account" : "Good to see you."}</h2>
            <p>{isRegistering ? "Make a little room for what’s next." : "Sign in to continue your conversation."}</p>
          </div>

          <form className={styles.form} onSubmit={handleSubmit}>
            {isRegistering && (
              <label className={styles.field}>
                <span>Your name</span>
                <input
                  autoComplete="name"
                  maxLength={120}
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="How should we call you?"
                />
              </label>
            )}
            <label className={styles.field}>
              <span>Email address</span>
              <input
                autoComplete="email"
                inputMode="email"
                maxLength={320}
                required
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label className={styles.field}>
              <span>Password</span>
              <input
                autoComplete={isRegistering ? "new-password" : "current-password"}
                minLength={isRegistering ? 8 : 1}
                maxLength={128}
                required
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={isRegistering ? "At least 8 characters" : "Enter your password"}
              />
            </label>

            {error && <p className={styles.error} role="alert">{error}</p>}

            <button className={styles.submit} type="submit" disabled={busy}>
              {busy ? <><span className={styles.spinner} /> {isRegistering ? "Creating your account…" : "Signing you in…"}</> : <>{isRegistering ? "Create account" : "Sign in"} <span aria-hidden="true">→</span></>}
            </button>
          </form>

          <p className={styles.switchMode}>
            {isRegistering ? "Already have an account?" : "New to Medha?"}{" "}
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setPassword("");
                onModeChange(isRegistering ? "login" : "register");
              }}
            >
              {isRegistering ? "Sign in" : "Create an account"}
            </button>
          </p>
          <p className={styles.privacy}>Medha does not save your password in browser storage.</p>
        </div>
        <span className={styles.bottomNote}>A thoughtful AI, ready when you are.</span>
      </section>
    </main>
  );
}
