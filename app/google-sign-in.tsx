'use client';

import {useEffect, useRef, useState} from 'react';
import {googleAuthMessage, googleButtonLabel, type GoogleAuthLang} from './google-auth';

type GoogleCredential = {credential?: string};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredential) => void;
            ux_mode?: 'popup';
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, string | number>) => void;
        };
      };
    };
  }
}

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '';

function loadGoogleScript(lang: GoogleAuthLang) {
  const hl = lang === 'en' ? 'en' : 'ar';
  const src = `https://accounts.google.com/gsi/client?hl=${hl}`;
  const existing = document.querySelector<HTMLScriptElement>('script[data-google-identity]');
  if (existing?.dataset.hl === hl) {
    if (window.google?.accounts?.id) return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      existing.addEventListener('load', () => resolve(), {once: true});
      existing.addEventListener('error', () => reject(new Error('google')), {once: true});
    });
  }
  existing?.remove();
  try {
    delete window.google;
  } catch {
    /* The previous GIS script may keep its global until the new one loads. */
  }
  return new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.dataset.googleIdentity = 'true';
    script.dataset.hl = hl;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('google'));
    document.head.appendChild(script);
  });
}

export function GoogleSignInButton({lang, disabled, busy, onCredential, onFailure}: {
  lang: GoogleAuthLang;
  disabled?: boolean;
  busy?: boolean;
  onCredential: (credential: string) => void;
  onFailure: (message: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const credentialRef = useRef(onCredential);
  const failureRef = useRef(onFailure);
  const [failed, setFailed] = useState(false);
  credentialRef.current = onCredential;
  failureRef.current = onFailure;
  const label = busy
    ? (lang === 'en' ? 'Signing in…' : 'جارٍ تسجيل الدخول…')
    : googleButtonLabel(lang);

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;
    loadGoogleScript(lang).then(() => {
      if (cancelled || !host.current || !window.google?.accounts?.id) return;
      host.current.replaceChildren();
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        ux_mode: 'popup',
        auto_select: false,
        cancel_on_tap_outside: true,
        callback: response => {
          if (response.credential) credentialRef.current(response.credential);
          else failureRef.current(googleAuthMessage('invalid', lang));
        },
      });
      const width = Math.max(240, Math.min(400, Math.floor(host.current.getBoundingClientRect().width) || 360));
      window.google.accounts.id.renderButton(host.current, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        width,
      });
    }).catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [lang]);

  if (!CLIENT_ID || failed) {
    return (
      <button
        type="button"
        className="google-sign-in-face"
        disabled={disabled || busy}
        onClick={() => onFailure(googleAuthMessage(CLIENT_ID ? 'invalid' : 'not_configured', lang))}
      >
        <GoogleMark />
        <span>{label}</span>
      </button>
    );
  }

  return (
    <div className={`google-sign-in${disabled || busy ? ' is-busy' : ''}`}>
      <div className="google-sign-in-face" aria-hidden="true"><GoogleMark /><span>{label}</span></div>
      <div ref={host} className="google-sign-in-official" />
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.6 9.2c0-.6-.1-1.2-.2-1.8H9v3.4h4.8a4.1 4.1 0 0 1-1.8 2.7v2.2h2.9c1.7-1.6 2.7-3.9 2.7-6.5z"/>
      <path fill="#34A853" d="M9 18c2.4 0 4.5-.8 6-2.2l-2.9-2.2c-.8.6-1.9.9-3.1.9-2.4 0-4.4-1.6-5.1-3.8H.9v2.3A9 9 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.9 10.7A5.4 5.4 0 0 1 3.6 9c0-.6.1-1.2.3-1.7V5H.9a9 9 0 0 0 0 8l3-2.3z"/>
      <path fill="#EA4335" d="M9 3.6c1.3 0 2.5.5 3.4 1.3l2.6-2.6A9 9 0 0 0 .9 5l3 2.3C4.6 5.2 6.6 3.6 9 3.6z"/>
    </svg>
  );
}
