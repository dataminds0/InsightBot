import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiClientError } from "../lib/api";
import type { User } from "../types/api";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, email?: string) => Promise<string>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function initAuth() {
      if (!api.getToken()) {
        setIsLoading(false);
        return;
      }
      try {
        const currentUser = await api.getMe();
        setUser(currentUser);
      } catch (err) {
        if (err instanceof ApiClientError && err.status === 401) {
          api.setToken(null);
          setUser(null);
        }
      } finally {
        setIsLoading(false);
      }
    }
    initAuth();
  }, []);

  const login = async (username: string, password: string) => {
    setError(null);
    try {
      const res = await api.login(username, password);
      setUser(res.user);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تسجيل الدخول. يرجى التحقق من الاتصال بالخادم.");
      }
      throw err;
    }
  };

  const register = async (username: string, password: string, email?: string) => {
    setError(null);
    try {
      const res = await api.register(username, password, email);
      return res.message;
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تسجيل الحساب الجديد. يرجى المحاولة لاحقاً.");
      }
      throw err;
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  };

  const clearError = () => setError(null);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        error,
        login,
        register,
        logout,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
