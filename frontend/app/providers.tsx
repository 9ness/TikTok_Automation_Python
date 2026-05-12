"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";

import { QueueDrawer } from "@/components/queue/QueueDrawer";
import { QueueWebSocketBridge } from "@/components/queue/QueueWebSocketBridge";
import { ThemeProvider } from "@/lib/theme";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <QueueWebSocketBridge />
        {children}
        <QueueDrawer />
        <Toaster richColors position="top-right" theme="dark" />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
