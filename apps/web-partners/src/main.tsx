import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { installConsoleCapture } from "frontend-shared";
import "./api/client";
import "./index.css";
import { router } from "./routes";
import { OktaProviderWithConfig } from "./components/OktaProviderWithConfig";
import { AuthGate } from "./components/AuthGate";
import { FeatureFlagProvider } from "./features/FeatureFlagContext";

installConsoleCapture();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      staleTime: 5 * 60_000,
      gcTime: 30 * 60_000,
      placeholderData: (prev: unknown) => prev,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OktaProviderWithConfig>
      <AuthGate>
        <QueryClientProvider client={queryClient}>
          <FeatureFlagProvider>
            <RouterProvider router={router} />
          </FeatureFlagProvider>
        </QueryClientProvider>
      </AuthGate>
    </OktaProviderWithConfig>
  </StrictMode>,
);
