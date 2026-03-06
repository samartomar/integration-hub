import { createBrowserRouter, Navigate } from "react-router-dom";
import { LoginCallback } from "@okta/okta-react";
import { ErrorFallback } from "frontend-shared/ErrorFallback";
import { VendorAppLayout } from "./VendorAppLayout";
import { VendorDashboard } from "./pages/VendorDashboard";
import { VendorAllowlistPage } from "./pages/VendorAllowlistPage";
import { VendorConfigurationPage } from "./pages/VendorConfigurationPage";
import { VendorFlowsPage } from "./pages/VendorFlowsPage";
import { FlowDetailsPage } from "./pages/FlowDetailsPage";
import { VendorAuthProfilesPage } from "./pages/VendorAuthProfilesPage";
import { VendorEndpointsConfigPage } from "./pages/VendorEndpointsConfigPage";
import {
  RedirectAuthToProfiles,
  RedirectEndpointsToTab,
  RedirectContractsToConfiguration,
} from "./components/RedirectAuthEndpoints";
import { ExecutePage } from "./pages/ExecutePage";
import { VendorTransactionsPage } from "./pages/VendorTransactionsPage";
import { VendorFlowBuilderPage } from "./pages/VendorFlowBuilderPage";
import { PartnerCanonicalExplorerPage } from "./pages/PartnerCanonicalExplorerPage";
import { PartnerSandboxPage } from "./pages/PartnerSandboxPage";
import { PartnerAIDebuggerPage } from "./pages/PartnerAIDebuggerPage";
import { PartnerRuntimePreflightPage } from "./pages/PartnerRuntimePreflightPage";
import { PartnerCanonicalExecutePage } from "./pages/PartnerCanonicalExecutePage";
import { FlowJourneyPage } from "./pages/FlowJourneyPage";
import { FeatureRoute } from "./features/FeatureFlagContext";

export const router = createBrowserRouter([
  {
    element: <VendorAppLayout />,
    errorElement: <ErrorFallback homePath="/" homeLabel="Go to Vendor Home" />,
    children: [
      { path: "/", element: <Navigate to="/home" replace /> },
      { path: "/callback", element: <LoginCallback /> },
      { path: "/home", element: <FeatureRoute featureCode="home_welcome"><VendorDashboard /></FeatureRoute> },
      { path: "/flows", element: <FeatureRoute featureCode="flow_builder"><VendorFlowsPage /></FeatureRoute> },
      { path: "/flows/:operationCode", element: <FeatureRoute featureCode="flow_builder"><FlowDetailsPage /></FeatureRoute> },
      { path: "/configuration", element: <FeatureRoute featureCode="registry_basic"><VendorConfigurationPage /></FeatureRoute> },
      { path: "/configuration/access", element: <FeatureRoute featureCode="governance_allowlist"><VendorAllowlistPage /></FeatureRoute> },
      { path: "/configuration/allowlist", element: <Navigate to="/configuration/access" replace /> },
      { path: "/configuration/auth-profiles", element: <FeatureRoute featureCode="registry_basic"><VendorAuthProfilesPage /></FeatureRoute> },
      { path: "/configuration/endpoints", element: <FeatureRoute featureCode="registry_basic"><VendorEndpointsConfigPage /></FeatureRoute> },
      { path: "/configuration/my-operations", element: <FeatureRoute featureCode="registry_basic"><Navigate to="/configuration" replace /></FeatureRoute> },
      { path: "/operations", element: <FeatureRoute featureCode="registry_basic"><Navigate to="/configuration" replace /></FeatureRoute> },
      { path: "/allowlist", element: <FeatureRoute featureCode="governance_allowlist"><Navigate to="/configuration/access" replace /></FeatureRoute> },
      { path: "/auth-endpoints", element: <FeatureRoute featureCode="registry_basic"><Navigate to="/configuration/endpoints" replace /></FeatureRoute> },
      { path: "/auth", element: <RedirectAuthToProfiles /> },
      { path: "/auth-security", element: <RedirectAuthToProfiles /> },
      { path: "/endpoints", element: <RedirectEndpointsToTab /> },
      { path: "/contracts", element: <RedirectContractsToConfiguration /> },
      { path: "/builder", element: <Navigate to="/flow" replace /> },
      { path: "/builder/:operationCode/:canonicalVersion", element: <FeatureRoute featureCode="flow_builder"><VendorFlowBuilderPage /></FeatureRoute> },
      { path: "/flow", element: <FeatureRoute featureCode="flow_builder"><FlowJourneyPage /></FeatureRoute> },
      { path: "/canonical", element: <FeatureRoute featureCode="flow_builder"><PartnerCanonicalExplorerPage /></FeatureRoute> },
      { path: "/sandbox", element: <FeatureRoute featureCode="flow_builder"><PartnerSandboxPage /></FeatureRoute> },
      { path: "/ai-debugger", element: <FeatureRoute featureCode="flow_builder"><PartnerAIDebuggerPage /></FeatureRoute> },
      { path: "/runtime-preflight", element: <FeatureRoute featureCode="flow_builder"><PartnerRuntimePreflightPage /></FeatureRoute> },
      { path: "/canonical-execute", element: <FeatureRoute featureCode="flow_builder"><PartnerCanonicalExecutePage /></FeatureRoute> },
      { path: "/transactions", element: <FeatureRoute featureCode="audit_view"><VendorTransactionsPage /></FeatureRoute> },
      { path: "/debug", element: <Navigate to="/transactions" replace /> },
      { path: "/onboarding", element: <Navigate to="/" replace /> },
      { path: "/execute", element: <FeatureRoute featureCode="execute_test"><ExecutePage /></FeatureRoute> },
    ],
  },
]);
