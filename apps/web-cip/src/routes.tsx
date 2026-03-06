import { createBrowserRouter, Navigate, useParams } from "react-router-dom";
import { LoginCallback } from "@okta/okta-react";
import { AppLayout } from "./App.tsx";
import { ErrorFallback } from "./components/ErrorFallback.tsx";
import { DashboardPage } from "./pages/DashboardPage.tsx";
import { TransactionsPage } from "./pages/TransactionsPage.tsx";
import { TransactionDetailPage } from "./pages/TransactionDetailPage.tsx";
import { RegistryPage } from "./pages/RegistryPage.tsx";
import { VendorDetailPage } from "./pages/VendorDetailPage.tsx";
import { AIPage } from "./pages/AIPage.tsx";
import { JourneyModePage } from "./pages/JourneyModePage.tsx";
import { PolicyDecisionViewerPage } from "./pages/PolicyDecisionViewerPage.tsx";
import { PolicySimulatorPage } from "./pages/PolicySimulatorPage.tsx";
import { MissionControlPage } from "./pages/MissionControlPage.tsx";
import { FeatureRoute } from "./features/FeatureFlagContext.tsx";

function LegacyTransactionRedirect() {
  const { transactionId } = useParams<{ transactionId: string }>();
  return (
    <Navigate
      to={
        transactionId
          ? `/admin/transactions/${transactionId}`
          : "/admin/transactions"
      }
      replace
    />
  );
}

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] p-8 text-center">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Page Not Found</h1>
      <p className="text-gray-600 mb-6">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <a
        href="/admin/dashboard"
        className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
      >
        Go to Dashboard
      </a>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: <ErrorFallback />,
    children: [
      { path: "/", element: <Navigate to="/admin/dashboard" replace /> },
      { path: "/admin", element: <Navigate to="/admin/dashboard" replace /> },
      { path: "/callback", element: <LoginCallback /> },
      { path: "/admin/dashboard", element: <FeatureRoute featureCode="home_welcome"><DashboardPage /></FeatureRoute> },
      { path: "/admin/journey-mode", element: <JourneyModePage /> },
      { path: "/admin/policy-decisions", element: <PolicyDecisionViewerPage /> },
      { path: "/admin/policy-simulator", element: <PolicySimulatorPage /> },
      { path: "/admin/mission-control", element: <FeatureRoute featureCode="registry_basic"><MissionControlPage /></FeatureRoute> },
      { path: "/admin/transactions", element: <FeatureRoute featureCode="audit_view"><TransactionsPage /></FeatureRoute> },
      {
        path: "/admin/transactions/:transactionId",
        element: <FeatureRoute featureCode="audit_view"><TransactionDetailPage /></FeatureRoute>,
      },
      { path: "/admin/registry", element: <FeatureRoute featureCode="registry_basic"><RegistryPage /></FeatureRoute> },
      { path: "/admin/approvals", element: <FeatureRoute featureCode="approvals"><Navigate to="/admin/registry?tab=access-requests" replace /></FeatureRoute> },
      {
        path: "/admin/registry/vendors/:vendorCode",
        element: <FeatureRoute featureCode="registry_basic"><VendorDetailPage /></FeatureRoute>,
      },
      { path: "/ai", element: <FeatureRoute featureCode="ai_formatter_ui"><AIPage /></FeatureRoute> },
      { path: "/dashboard", element: <Navigate to="/admin/dashboard" replace /> },
      { path: "/transactions", element: <Navigate to="/admin/transactions" replace /> },
      {
        path: "/transactions/:transactionId",
        element: <LegacyTransactionRedirect />,
      },
      { path: "/registry", element: <Navigate to="/admin/registry" replace /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
