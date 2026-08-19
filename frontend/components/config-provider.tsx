"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import { FALLBACK_CONFIG } from "@/lib/config";
import type { PublicConfig } from "@/lib/types";

const ConfigContext = createContext<PublicConfig>(FALLBACK_CONFIG);

/** Read the server's limits, bands, and disclaimers. Never duplicate them here. */
export function useConfig(): PublicConfig {
  return useContext(ConfigContext);
}

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<PublicConfig>(FALLBACK_CONFIG);

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<PublicConfig>("/api/v1/config", undefined, controller.signal)
      .then(setConfig)
      .catch(() => {
        // Keep the fallback: a config fetch failure must not blank the page.
      });
    return () => controller.abort();
  }, []);

  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}
