"use client";

import { create } from "zustand";
import { authApi, UserOut } from "@/lib/api";

interface AuthState {
  user: UserOut | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string, totpCode?: string) => Promise<void>;
  logout: () => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: false,
  error: null,

  login: async (email, password, totpCode) => {
    set({ loading: true, error: null });
    try {
      const tokens = await authApi.login(email, password, totpCode);
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      const user = await authApi.me();
      set({ user, loading: false });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "login failed", loading: false });
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    set({ user: null });
  },

  hydrate: async () => {
    if (!localStorage.getItem("access_token")) return;
    set({ loading: true });
    try {
      const user = await authApi.me();
      set({ user, loading: false });
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      set({ user: null, loading: false });
    }
  },
}));
