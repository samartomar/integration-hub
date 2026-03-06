import { useState } from "react";
import { Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ConnectionBanner, DebugPanel } from "frontend-shared";
import { OktaTokenSetup } from "./components/OktaTokenSetup";
import { SettingsModal } from "./components/SettingsModal";
import { FeaturesModal } from "./components/FeaturesModal";
import { TopBar } from "./components/TopBar";
import { PhiAccessBanner } from "./components/PhiAccessBanner";
import { PhiAccessProvider } from "./security/PhiAccessContext";

export function AppLayout() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [featuresOpen, setFeaturesOpen] = useState(false);
  const queryClient = useQueryClient();

  return (
    <PhiAccessProvider>
      <div className="min-h-screen flex flex-col bg-gray-50">
      <OktaTokenSetup />
      <div className="flex-1 flex flex-col min-h-screen min-w-0">
        <TopBar
          onSettingsClick={() => setSettingsOpen(true)}
          onFeaturesClick={() => setFeaturesOpen(true)}
        />
        <ConnectionBanner onRetry={() => queryClient.invalidateQueries()} />
          <PhiAccessBanner />

          <SettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
        <FeaturesModal isOpen={featuresOpen} onClose={() => setFeaturesOpen(false)} />

        <DebugPanel />

        <main className="flex-1 min-w-0 overflow-auto bg-slate-50">
          <div className="w-full max-w-[1600px] mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-5 lg:py-6 border-l-4 border-l-slate-600">
            <Outlet />
          </div>
        </main>
        </div>
      </div>
    </PhiAccessProvider>
  );
}
