import { createContext, useContext, useState } from 'react';

const AuthContext = createContext();
const API_BASE = `http://${window.location.hostname}:8000`;
const ADMIN_API_KEY = "devkey-123";
const AUTH_STORAGE_KEY = "ecg_auth";

const readStoredAuth = () => {
  try {
    return JSON.parse(window.localStorage.getItem(AUTH_STORAGE_KEY) || "null");
  } catch {
    return null;
  }
};

export const AuthProvider = ({ children }) => {
  const [auth, setAuth] = useState(readStoredAuth);

  const persistAuth = (nextAuth) => {
    setAuth(nextAuth);
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(nextAuth));
  };

  const login = async (username, password) => {
    if (username === 'admin' && password === 'admin123') {
      persistAuth({
        user: { username: "admin", role: "admin", can_record_ecg: true },
        credentials: { apiKey: ADMIN_API_KEY },
      });
      return true;
    }

    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) return false;

      const user = await response.json();
      persistAuth({
        user,
        credentials: { username, password },
      });
      return true;
    } catch (error) {
      console.error("login error:", error);
      return false;
    }
  };

  const logout = () => {
    setAuth(null);
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  };

  const authHeaders = () => {
    if (auth?.credentials?.apiKey) {
      return { "x-api-key": auth.credentials.apiKey };
    }

    if (auth?.credentials?.username && auth?.credentials?.password) {
      return {
        "x-username": auth.credentials.username,
        "x-password": auth.credentials.password,
      };
    }

    return {};
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: Boolean(auth?.user),
        user: auth?.user ?? null,
        credentials: auth?.credentials ?? null,
        login,
        logout,
        authHeaders,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
